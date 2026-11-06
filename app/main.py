"""Platforma brokerska — aplikacja webowa (FastAPI, strony renderowane na serwerze).

Strony działają bez JavaScriptu i są budowane pod czytnik ekranu oraz telefon.
"""
from __future__ import annotations

import os
import secrets
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from . import engine as eng
from . import services as svc
from .db import Base, engine, get_db
from .models import (
    CONTRACT_STATUSES,
    MEDIA,
    STATUSES_REQUIRING_NOTE,
    ROLE_MANAGER,
    ROLE_OWNER,
    ROLE_TRADER,
    ROLES,
    TRIGGERS,
    Company,
    Contract,
    Supplier,
    SupplierRuleSet,
    User,
    UserRate,
    split_full_name,
)
from . import migrate
from .security import hash_password, new_csrf_token, verify_password

BASE_DIR = Path(__file__).resolve().parent

SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_urlsafe(48)
SECURE_COOKIES = os.environ.get("SECURE_COOKIES", "0") == "1"

app = FastAPI(title="Platforma brokerska", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax",
    https_only=SECURE_COOKIES,
    max_age=60 * 60 * 12,
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.on_event("startup")
def _startup() -> None:
    Base.metadata.create_all(bind=engine)
    migrate.run(engine)
    _bootstrap_owner_from_env()


def _bootstrap_owner_from_env() -> None:
    email = os.environ.get("OWNER_EMAIL")
    password = os.environ.get("OWNER_PASSWORD")
    if not email or not password:
        return
    from .db import SessionLocal

    with SessionLocal() as db:
        if db.scalar(select(func.count(User.id))) == 0:
            # Brak nazwiska lub nazwy firmy w zmiennych = właściciel uzupełni je po pierwszym logowaniu.
            u = User(email=email.lower().strip(), password_hash=hash_password(password), role=ROLE_OWNER)
            u.set_names(*split_full_name(os.environ.get("OWNER_NAME", "")))
            db.add(u)
            if os.environ.get("COMPANY_NAME", "").strip():
                db.add(Company(name=os.environ["COMPANY_NAME"].strip()))
            db.commit()


# --------------------------------------------------------------------------
# Formatowanie (filtry szablonów)
# --------------------------------------------------------------------------

def _group(int_part: str) -> str:
    out = []
    while len(int_part) > 3:
        out.insert(0, int_part[-3:])
        int_part = int_part[:-3]
    out.insert(0, int_part)
    return " ".join(out)


def fmt_num(value, places: int = 2) -> str:
    if value is None or value == "":
        return "—"
    d = eng.D(value).quantize(Decimal(1).scaleb(-places)) if places else eng.D(value).quantize(Decimal(1))
    sign = "-" if d < 0 else ""
    s = f"{abs(d):f}"
    if "." in s:
        i, f = s.split(".")
        return f"{sign}{_group(i)},{f}"
    return f"{sign}{_group(s)}"


def fmt_zl(value) -> str:
    if value is None:
        return "—"
    return f"{fmt_num(value)} zł"


def fmt_pct(value) -> str:
    if value is None:
        return "—"
    d = eng.D(value).normalize()
    s = f"{d:f}".replace(".", ",")
    return f"{s}%"


def fmt_mwh(value) -> str:
    if value is None:
        return "—"
    d = eng.D(value)
    places = 0 if d == d.to_integral_value() else 3
    return f"{fmt_num(d, places)} MWh"


def fmt_date(value) -> str:
    if not value:
        return "—"
    return value.strftime("%d.%m.%Y")


templates.env.filters.update(zip=lambda a, b: list(zip(a, b)), zl=fmt_zl, pct=fmt_pct, mwh=fmt_mwh, data=fmt_date, num=fmt_num)
templates.env.globals.update(
    ROLES=ROLES,
    TRIGGERS=TRIGGERS,
    MEDIA=MEDIA,
    STATUSES=CONTRACT_STATUSES,
    STATUSES_REQUIRING_NOTE=STATUSES_REQUIRING_NOTE,
    ROLE_OWNER=ROLE_OWNER,
    ROLE_MANAGER=ROLE_MANAGER,
    ROLE_TRADER=ROLE_TRADER,
    OVERRIDE_BASES={
        eng.OVERRIDE_OD_NARZUTU: "od całej masy narzutu",
        eng.OVERRIDE_OD_HANDLOWCA: "od prowizji handlowca",
    },
    CLAWBACK_MODES={
        eng.KOREKTA_PROPORCJONALNA: "Proporcjonalna do niezrealizowanej części umowy",
        eng.KOREKTA_BRAK: "Brak korekty",
    },
)


# --------------------------------------------------------------------------
# Nawigacja: zakładki główne i podsekcje
# --------------------------------------------------------------------------

# (klucz, podpis, adres, prefiksy adresów należących do zakładki, tylko właściciel)
TABS = [
    ("portfel", "Portfel", "/pulpit", ("/pulpit", "/umowy"), False),
    ("spolki", "Spółki", "/spolki", ("/spolki",), True),
    ("zespol", "Zespół", "/zespol", ("/zespol",), True),
    ("raporty", "Raporty", "/raporty", ("/raporty",), False),
    ("konto", "Konto", "/konto", ("/konto", "/haslo"), False),
]

SUBTABS = {
    "portfel": [("Podsumowanie", "/pulpit"), ("Umowy", "/umowy"), ("Nowa umowa", "/umowy/nowa")],
    "spolki": [("Lista spółek", "/spolki"), ("Dodaj spółkę", "/spolki/nowa")],
    "zespol": [("Lista osób", "/zespol"), ("Dodaj osobę", "/zespol/nowa")],
    "konto": [("Moje konto", "/konto"), ("Moje dane", "/konto/dane"), ("Zmiana hasła", "/haslo")],
}


def _belongs(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def navigation(user: Optional[User], path: str) -> dict:
    """Zakładki widoczne dla roli oraz podsekcje bieżącej zakładki."""
    if not user:
        return {"tabs": [], "sub": [], "section": None}
    tabs, active = [], None
    for key, label, url, prefixes, owner_only_tab in TABS:
        if owner_only_tab and user.role != ROLE_OWNER:
            continue
        is_active = any(_belongs(path, pre) for pre in prefixes)
        if is_active:
            active = key
        tabs.append({"key": key, "label": label, "url": url, "active": is_active})
    sub = []
    if active in SUBTABS:
        # najdłuższe pasujące dopasowanie wygrywa, np. /umowy/nowa przed /umowy
        urls = [u for _, u in SUBTABS[active]]
        match = max((u for u in urls if _belongs(path, u)), key=len, default=None)
        sub = [{"label": lab, "url": u, "active": u == match} for lab, u in SUBTABS[active]]
    section = next((t["label"] for t in tabs if t["active"]), None)
    return {"tabs": tabs, "sub": sub, "section": section}


# --------------------------------------------------------------------------
# Sesja, CSRF, komunikaty
# --------------------------------------------------------------------------

def csrf_token(request: Request) -> str:
    tok = request.session.get("csrf")
    if not tok:
        tok = new_csrf_token()
        request.session["csrf"] = tok
    return tok


async def form_data(request: Request) -> dict:
    form = await request.form()
    sent = form.get("csrf", "")
    expected = request.session.get("csrf", "")
    if not expected or not secrets.compare_digest(str(sent), str(expected)):
        raise HTTPException(status_code=400, detail="Sesja wygasła. Odśwież stronę i spróbuj ponownie.")
    return {k: (v.strip() if isinstance(v, str) else v) for k, v in form.items()}


def flash(request: Request, message: str) -> None:
    request.session.setdefault("flash", []).append(message)


def render(request: Request, name: str, ctx: Optional[dict] = None, status_code: int = 200):
    ctx = dict(ctx or {})
    ctx["request"] = request
    ctx["csrf"] = csrf_token(request)
    ctx["flashes"] = request.session.pop("flash", [])
    ctx.setdefault("user", None)
    ctx["nav"] = navigation(ctx["user"], request.url.path)
    ctx["brand"] = getattr(request.state, "company_name", None) or "Platforma brokerska"
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


class LoginRequired(Exception):
    pass


class ProfileIncomplete(Exception):
    pass


COMPLETION_URL = "/konto/dane"
COMPLETION_ALLOWED = {COMPLETION_URL, "/wyloguj"}


def company_of(db: Session) -> Optional[Company]:
    return db.scalar(select(Company).order_by(Company.id))


def needs_completion(user: User, company: Optional[Company]) -> bool:
    if user.needs_last_name or len(user.first_name or "") < 2:
        return True
    return user.role == ROLE_OWNER and company is None


@app.exception_handler(ProfileIncomplete)
async def _profile_incomplete(request: Request, exc: ProfileIncomplete):
    return redirect(COMPLETION_URL)


@app.exception_handler(LoginRequired)
async def _login_required(request: Request, exc: LoginRequired):
    return redirect("/logowanie")


@app.exception_handler(HTTPException)
async def _http_error(request: Request, exc: HTTPException):
    messages = {403: "Brak dostępu do tej strony.", 404: "Nie znaleziono strony."}
    return render(
        request,
        "blad.html",
        {"message": exc.detail if exc.status_code == 400 else messages.get(exc.status_code, exc.detail)},
        status_code=exc.status_code,
    )


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("uid")
    if not uid:
        raise LoginRequired()
    user = db.get(User, uid)
    if not user or not user.active:
        request.session.clear()
        raise LoginRequired()
    company = company_of(db)
    request.state.company_name = company.name if company else None
    if request.url.path not in COMPLETION_ALLOWED and needs_completion(user, company):
        raise ProfileIncomplete()
    return user


def owner_only(user: User = Depends(current_user)) -> User:
    if user.role != ROLE_OWNER:
        raise HTTPException(status_code=403)
    return user


# --------------------------------------------------------------------------
# Parsowanie pól formularzy
# --------------------------------------------------------------------------

class FormError(ValueError):
    pass


def p_dec(form: dict, key: str, label: str, *, required: bool = True, minimum=None, maximum=None) -> Optional[Decimal]:
    raw = form.get(key, "")
    if raw == "":
        if required:
            raise FormError(f"Pole „{label}” jest wymagane.")
        return None
    try:
        val = eng.D(raw)
    except (InvalidOperation, ValueError):
        raise FormError(f"Pole „{label}”: podaj liczbę, np. 75 albo 75,5.")
    if not val.is_finite():
        raise FormError(f"Pole „{label}”: podaj liczbę.")
    if minimum is not None and val < minimum:
        raise FormError(f"Pole „{label}”: wartość nie może być mniejsza niż {fmt_num(minimum, 0)}.")
    if maximum is not None and val > maximum:
        raise FormError(f"Pole „{label}”: wartość nie może być większa niż {fmt_num(maximum, 0)}.")
    return val


def p_int(form: dict, key: str, label: str, *, minimum: int = 0, maximum: int = 10_000) -> int:
    raw = form.get(key, "")
    try:
        val = int(raw)
    except (TypeError, ValueError):
        raise FormError(f"Pole „{label}”: podaj liczbę całkowitą.")
    if val < minimum or val > maximum:
        raise FormError(f"Pole „{label}”: dozwolony zakres {minimum}–{maximum}.")
    return val


def p_date(form: dict, key: str, label: str, *, required: bool = True) -> Optional[date]:
    raw = form.get(key, "")
    if raw == "":
        if required:
            raise FormError(f"Pole „{label}” jest wymagane.")
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise FormError(f"Pole „{label}”: niepoprawna data.")


# --------------------------------------------------------------------------
# Logowanie i pierwsza konfiguracja
# --------------------------------------------------------------------------

def _no_users(db: Session) -> bool:
    return db.scalar(select(func.count(User.id))) == 0


@app.get("/", include_in_schema=False)
def index(request: Request):
    return redirect("/pulpit" if request.session.get("uid") else "/logowanie")


@app.get("/logowanie", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    if _no_users(db):
        return redirect("/start")
    return render(request, "logowanie.html")


@app.post("/logowanie")
async def login(request: Request, db: Session = Depends(get_db)):
    form = await form_data(request)
    email = form.get("email", "").lower()
    user = db.scalar(select(User).where(User.email == email))
    if not user or not user.active or not verify_password(form.get("haslo", ""), user.password_hash):
        return render(
            request, "logowanie.html", {"error": "Nieprawidłowy e-mail lub hasło.", "email": email}, 401
        )
    request.session.clear()
    request.session["uid"] = user.id
    return redirect("/pulpit")


@app.post("/wyloguj")
async def logout(request: Request):
    await form_data(request)
    request.session.clear()
    return redirect("/logowanie")


@app.get("/start", response_class=HTMLResponse)
def setup_page(request: Request, db: Session = Depends(get_db)):
    if not _no_users(db):
        return redirect("/logowanie")
    return render(request, "start.html")


@app.post("/start")
async def setup(request: Request, db: Session = Depends(get_db)):
    form = await form_data(request)
    if not _no_users(db):
        return redirect("/logowanie")
    err = company_error(form) or _validate_new_user(form, db, require_role=False)
    if err:
        return render(request, "start.html", {"error": err, "form": form}, 400)
    u = User(email=form["email"].lower(), password_hash=hash_password(form["haslo"]), role=ROLE_OWNER)
    u.set_names(form["imie"], form["nazwisko"])
    db.add(u)
    if not company_of(db):
        db.add(Company(name=form["firma"]))
    db.commit()
    request.session.clear()
    request.session["uid"] = u.id
    flash(request, "Konto właściciela utworzone. Zacznij od dodania spółki obrotu i jej reguł.")
    return redirect("/spolki")


def names_error(form: dict) -> Optional[str]:
    first, last = form.get("imie", ""), form.get("nazwisko", "")
    if len(first) < 2:
        return "Podaj imię (co najmniej 2 znaki)."
    if len(last) < 2:
        return "Podaj nazwisko (co najmniej 2 znaki)."
    if len(first) > 100 or len(last) > 100:
        return "Imię i nazwisko mogą mieć najwyżej 100 znaków każde."
    return None


COMPANY_MIN, COMPANY_MAX = 3, 300


def company_error(form: dict) -> Optional[str]:
    n = len(form.get("firma", ""))
    if n < COMPANY_MIN or n > COMPANY_MAX:
        return f"Podaj pełną nazwę firmy ({COMPANY_MIN}–{COMPANY_MAX} znaków), np. „Energia Lublin sp. z o.o.”."
    return None


def _validate_new_user(form: dict, db: Session, require_role: bool = True) -> Optional[str]:
    err = names_error(form)
    if err:
        return err
    email = form.get("email", "").lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        return "Podaj poprawny adres e-mail."
    if db.scalar(select(User).where(User.email == email)):
        return "Użytkownik z tym adresem e-mail już istnieje."
    if len(form.get("haslo", "")) < 10:
        return "Hasło musi mieć co najmniej 10 znaków."
    if require_role and form.get("rola") not in ROLES:
        return "Wybierz rolę."
    return None


@app.get("/konto", response_class=HTMLResponse)
def account_page(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return render(request, "konto.html", {"user": user, "company": company_of(db)})


def _account_data_ctx(user: User, db: Session, form: Optional[dict] = None, error: Optional[str] = None) -> dict:
    company = company_of(db)
    return {
        "user": user,
        "company": company,
        "incomplete": needs_completion(user, company),
        "form": form or {"imie": user.first_name, "nazwisko": user.last_name, "firma": company.name if company else ""},
        "error": error,
    }


@app.get("/konto/dane", response_class=HTMLResponse)
def account_data_page(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return render(request, "konto_dane.html", _account_data_ctx(user, db))


@app.post("/konto/dane")
async def account_data_save(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    form = await form_data(request)
    err = names_error(form) or (company_error(form) if user.role == ROLE_OWNER else None)
    if err:
        return render(request, "konto_dane.html", _account_data_ctx(user, db, form, err), 400)
    user.set_names(form["imie"], form["nazwisko"])
    if user.role == ROLE_OWNER:
        company = company_of(db)
        if company:
            company.name = form["firma"]
        else:
            db.add(Company(name=form["firma"]))
    db.commit()
    flash(request, "Zapisano dane.")
    return redirect("/konto")


@app.get("/raporty", response_class=HTMLResponse)
def reports_page(request: Request, user: User = Depends(current_user)):
    return render(request, "raporty.html", {"user": user})


@app.get("/haslo", response_class=HTMLResponse)
def password_page(request: Request, user: User = Depends(current_user)):
    return render(request, "haslo.html", {"user": user})


@app.post("/haslo")
async def password_change(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    form = await form_data(request)
    if not verify_password(form.get("obecne", ""), user.password_hash):
        return render(request, "haslo.html", {"user": user, "error": "Obecne hasło jest nieprawidłowe."}, 400)
    if len(form.get("nowe", "")) < 10:
        return render(request, "haslo.html", {"user": user, "error": "Nowe hasło musi mieć co najmniej 10 znaków."}, 400)
    if form.get("nowe") != form.get("powtorz"):
        return render(request, "haslo.html", {"user": user, "error": "Nowe hasła nie są takie same."}, 400)
    user.password_hash = hash_password(form["nowe"])
    db.commit()
    flash(request, "Hasło zmienione.")
    return redirect("/konto")


# --------------------------------------------------------------------------
# Pulpit
# --------------------------------------------------------------------------

@app.get("/pulpit", response_class=HTMLResponse)
def dashboard(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    contracts = list(db.scalars(svc.visible_contracts_query(user)))
    summary = svc.summary_for(user, contracts)
    ctx = {"user": user, "summary": summary, "recent": [svc.contract_view(user, c) for c in contracts[:5]]}
    if user.role == ROLE_OWNER:
        suppliers = list(db.scalars(select(Supplier).order_by(Supplier.name)))
        ctx["suppliers_without_rules"] = [s.name for s in suppliers if not s.rule_sets]
        ctx["supplier_count"] = len(suppliers)
    return render(request, "pulpit.html", ctx)


# --------------------------------------------------------------------------
# Spółki obrotu i ich reguły (tylko właściciel)
# --------------------------------------------------------------------------

@app.get("/spolki", response_class=HTMLResponse)
def suppliers_page(request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    suppliers = list(db.scalars(select(Supplier).order_by(Supplier.name)))
    rows = [(s, svc.current_rule_set(s)) for s in suppliers]
    return render(request, "spolki.html", {"user": user, "rows": rows})


@app.get("/spolki/nowa", response_class=HTMLResponse)
def supplier_new_page(request: Request, user: User = Depends(owner_only)):
    return render(request, "spolka_nowa.html", {"user": user, "form": {}})


@app.post("/spolki")
async def supplier_add(request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    form = await form_data(request)
    name = form.get("nazwa", "")
    if not name:
        return render(request, "spolka_nowa.html", {"user": user, "form": form, "error": "Podaj nazwę spółki."}, 400)
    if db.scalar(select(Supplier).where(Supplier.name == name)):
        return render(
            request, "spolka_nowa.html", {"user": user, "form": form, "error": f"Spółka {name} już istnieje."}, 400
        )
    s = Supplier(name=name)
    db.add(s)
    db.commit()
    flash(request, f"Dodano spółkę {name}. Ustaw teraz jej reguły prowizji.")
    return redirect(f"/spolki/{s.id}")


def _get_supplier(db: Session, sid: int) -> Supplier:
    s = db.get(Supplier, sid)
    if not s:
        raise HTTPException(status_code=404)
    return s


@app.get("/spolki/{sid}", response_class=HTMLResponse)
def supplier_page(sid: int, request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    s = _get_supplier(db, sid)
    return render(
        request,
        "spolka.html",
        {"user": user, "s": s, "current": svc.current_rule_set(s), "today": date.today(), "form": {}},
    )


@app.post("/spolki/{sid}/reguly")
async def supplier_rules_add(sid: int, request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    s = _get_supplier(db, sid)
    form = await form_data(request)
    try:
        rs = SupplierRuleSet(
            supplier_id=s.id,
            valid_from=p_date(form, "od", "Obowiązuje od"),
            broker_share_pct=p_dec(form, "udzial", "Udział brokera w narzucie", minimum=0, maximum=100),
            first_tranche_pct=p_dec(form, "transza", "Pierwsza transza", minimum=0, maximum=100),
            first_tranche_trigger=form.get("wyzwalacz") if form.get("wyzwalacz") in TRIGGERS else "weryfikacja",
            max_markup_pln_mwh=p_dec(form, "limit", "Limit narzutu", required=False, minimum=0),
            new_connection_months=p_int(form, "nowe_msc", "Okres rozliczeń z faktur dla nowych przyłączy", maximum=60),
            clawback_mode=form.get("korekta") if form.get("korekta") in eng.CLAWBACK_MODES else eng.KOREKTA_PROPORCJONALNA,
            note=form.get("uwagi", "")[:2000],
        )
    except FormError as e:
        return render(
            request,
            "spolka.html",
            {"user": user, "s": s, "current": svc.current_rule_set(s), "today": date.today(), "error": str(e), "form": form},
            400,
        )
    db.add(rs)
    db.commit()
    flash(
        request,
        f"Zapisano reguły {s.name} od {fmt_date(rs.valid_from)}: udział brokera {fmt_pct(rs.broker_share_pct)}, "
        f"pierwsza transza {fmt_pct(rs.first_tranche_pct)}. Umowy już zapisane zachowują swoje dotychczasowe reguły.",
    )
    return redirect(f"/spolki/{s.id}")


@app.post("/spolki/{sid}/aktywna")
async def supplier_toggle(sid: int, request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    s = _get_supplier(db, sid)
    await form_data(request)
    s.active = not s.active
    db.commit()
    flash(request, f"Spółka {s.name} jest teraz {'aktywna' if s.active else 'nieaktywna'}.")
    return redirect(f"/spolki/{s.id}")


# --------------------------------------------------------------------------
# Zespół i stawki (tylko właściciel)
# --------------------------------------------------------------------------

def _managers(db: Session) -> list[User]:
    return list(db.scalars(select(User).where(User.role == ROLE_MANAGER, User.active.is_(True)).order_by(User.last_name, User.first_name)))


@app.get("/zespol", response_class=HTMLResponse)
def team_page(request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    people = list(db.scalars(select(User).order_by(User.role, User.last_name, User.first_name)))
    rows = [(p, svc.current_rate(p)) for p in people]
    return render(request, "zespol.html", {"user": user, "rows": rows})


@app.get("/zespol/nowa", response_class=HTMLResponse)
def team_new_page(request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    return render(request, "zespol_nowa.html", {"user": user, "managers": _managers(db), "form": {}})


@app.post("/zespol")
async def team_add(request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    form = await form_data(request)
    err = _validate_new_user(form, db)
    manager_id = None
    if not err and form.get("menedzer"):
        m = db.get(User, int(form["menedzer"])) if form["menedzer"].isdigit() else None
        if not m or m.role != ROLE_MANAGER:
            err = "Wybrany menedżer nie istnieje."
        else:
            manager_id = m.id
    rate = None
    if not err:
        try:
            share = p_dec(form, "udzial", "Udział w narzucie", minimum=0, maximum=100)
            override = p_dec(form, "override", "Override", required=False, minimum=0, maximum=100) or Decimal(0)
            rate = (share, override)
        except FormError as e:
            err = str(e)
    if err:
        return render(
            request, "zespol_nowa.html", {"user": user, "managers": _managers(db), "error": err, "form": form}, 400
        )
    u = User(
        email=form["email"].lower(),
        password_hash=hash_password(form["haslo"]),
        role=form["rola"],
        manager_id=manager_id if form["rola"] != ROLE_OWNER else None,
    )
    u.set_names(form["imie"], form["nazwisko"])
    db.add(u)
    db.flush()
    db.add(
        UserRate(
            user_id=u.id,
            valid_from=date(2000, 1, 1),
            trader_share_pct=rate[0],
            override_pct=rate[1] if u.role == ROLE_MANAGER else Decimal(0),
            override_base=form.get("baza") if form.get("baza") in eng.OVERRIDE_BASES else eng.OVERRIDE_OD_NARZUTU,
        )
    )
    db.commit()
    flash(request, f"Dodano osobę {u.name} ({u.role_label}). Przekaż jej e-mail i hasło startowe.")
    return redirect("/zespol")


def _get_user(db: Session, uid: int) -> User:
    u = db.get(User, uid)
    if not u:
        raise HTTPException(status_code=404)
    return u


@app.get("/zespol/{uid}", response_class=HTMLResponse)
def person_page(uid: int, request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    p = _get_user(db, uid)
    return render(
        request,
        "osoba.html",
        {"user": user, "p": p, "current": svc.current_rate(p), "managers": _managers(db), "today": date.today(), "form": {}},
    )


@app.post("/zespol/{uid}/stawki")
async def person_rate_add(uid: int, request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    p = _get_user(db, uid)
    form = await form_data(request)
    try:
        r = UserRate(
            user_id=p.id,
            valid_from=p_date(form, "od", "Obowiązuje od"),
            trader_share_pct=p_dec(form, "udzial", "Udział w narzucie", minimum=0, maximum=100),
            override_pct=(p_dec(form, "override", "Override", required=False, minimum=0, maximum=100) or Decimal(0))
            if p.role == ROLE_MANAGER
            else Decimal(0),
            override_base=form.get("baza") if form.get("baza") in eng.OVERRIDE_BASES else eng.OVERRIDE_OD_NARZUTU,
        )
    except FormError as e:
        return render(
            request,
            "osoba.html",
            {"user": user, "p": p, "current": svc.current_rate(p), "managers": _managers(db), "today": date.today(), "error": str(e), "form": form},
            400,
        )
    db.add(r)
    db.commit()
    flash(request, f"Zapisano nowe stawki dla {p.name} od {fmt_date(r.valid_from)}.")
    return redirect(f"/zespol/{p.id}")


@app.post("/zespol/{uid}")
async def person_update(uid: int, request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    p = _get_user(db, uid)
    form = await form_data(request)
    if "imie" in form or "nazwisko" in form:
        err = names_error(form)
        if err:
            return render(
                request,
                "osoba.html",
                {"user": user, "p": p, "current": svc.current_rate(p), "managers": _managers(db), "today": date.today(), "error": err, "form": {}},
                400,
            )
        p.set_names(form["imie"], form["nazwisko"])
    if p.role != ROLE_OWNER:
        mid = form.get("menedzer", "")
        if mid == "":
            p.manager_id = None
        elif mid.isdigit():
            m = db.get(User, int(mid))
            if m and m.role == ROLE_MANAGER and m.id != p.id:
                p.manager_id = m.id
        if p.id != user.id:
            p.active = form.get("aktywny") == "1"
    if form.get("nowe_haslo"):
        if len(form["nowe_haslo"]) < 10:
            flash(request, "Błąd: hasło musi mieć co najmniej 10 znaków. Pozostałe zmiany zapisano.")
        else:
            p.password_hash = hash_password(form["nowe_haslo"])
    db.commit()
    flash(request, f"Zapisano zmiany: {p.name}.")
    return redirect(f"/zespol/{p.id}")


# --------------------------------------------------------------------------
# Umowy
# --------------------------------------------------------------------------

@app.get("/umowy", response_class=HTMLResponse)
def contracts_page(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    contracts = list(db.scalars(svc.visible_contracts_query(user)))
    views = [svc.contract_view(user, c) for c in contracts]
    return render(request, "umowy.html", {"user": user, "contracts": views, "summary": svc.summary_for(user, contracts)})


def _new_contract_ctx(db: Session, user: User, **extra) -> dict:
    ctx = {
        "user": user,
        "suppliers": list(db.scalars(select(Supplier).where(Supplier.active.is_(True)).order_by(Supplier.name))),
        "traders": svc.assignable_traders(db, user),
        "today": date.today(),
        "form": {},
    }
    ctx.update(extra)
    return ctx


@app.get("/umowy/nowa", response_class=HTMLResponse)
def contract_new_page(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return render(request, "umowa_nowa.html", _new_contract_ctx(db, user))


@app.post("/umowy/nowa")
async def contract_create(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    form = await form_data(request)
    try:
        supplier = db.get(Supplier, int(form.get("spolka", "0") or 0))
        if not supplier or not supplier.active:
            raise FormError("Wybierz spółkę obrotu.")
        tid = form.get("handlowiec") or str(user.id)
        trader = db.get(User, int(tid)) if tid.isdigit() else None
        if not trader:
            raise FormError("Wybierz handlowca.")
        if not form.get("klient"):
            raise FormError("Pole „Nazwa klienta” jest wymagane.")
        nip = "".join(ch for ch in form.get("nip", "") if ch.isdigit())
        if nip and not valid_nip(nip):
            raise FormError("NIP ma niepoprawną sumę kontrolną.")
        c = svc.create_contract(
            db,
            actor=user,
            trader=trader,
            supplier=supplier,
            client_name=form["klient"],
            client_nip=nip,
            medium=form.get("medium") if form.get("medium") in MEDIA else "energia",
            signed_date=p_date(form, "podpisana", "Data podpisania"),
            start_date=p_date(form, "start", "Start dostaw", required=False),
            term_months=p_int(form, "okres", "Okres umowy w miesiącach", minimum=1, maximum=120),
            annual_volume_mwh=p_dec(form, "wolumen", "Wolumen roczny", minimum=Decimal("0.001")),
            markup_pln_mwh=p_dec(form, "narzut", "Narzut", minimum=0),
            base_price_pln_mwh=p_dec(form, "cena_bazowa", "Cena bazowa spółki", required=False, minimum=0),
            new_connection=form.get("nowe_przylacze") == "1",
            status=form.get("status") if form.get("status") in CONTRACT_STATUSES else "Umowa podpisana",
        )
    except (FormError, svc.BusinessError, eng.EngineError) as e:
        return render(request, "umowa_nowa.html", _new_contract_ctx(db, user, error=str(e), form=form), 400)
    flash(request, f"Zapisano umowę z klientem {c.client_name}.")
    return redirect(f"/umowy/{c.id}")


def _get_visible_contract(db: Session, user: User, cid: int) -> Contract:
    c = db.get(Contract, cid)
    # 404 zamiast 403: nie zdradzamy, że umowa istnieje.
    if not c or not svc.can_view_contract(user, c):
        raise HTTPException(status_code=404)
    return c


def _contract_ctx(user: User, c: Contract, form: Optional[dict] = None, error: Optional[str] = None) -> dict:
    return {
        "user": user,
        "c": svc.contract_view(user, c),
        "history": c.events,
        "since": svc.status_since(c),
        "today": date.today(),
        "form": form or {},
        "error": error,
    }


@app.get("/umowy/{cid}", response_class=HTMLResponse)
def contract_page(cid: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _get_visible_contract(db, user, cid)
    return render(request, "umowa.html", _contract_ctx(user, c))


@app.post("/umowy/{cid}/status")
async def contract_status(cid: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _get_visible_contract(db, user, cid)
    form = await form_data(request)
    try:
        when = p_date(form, "data", "Data zdarzenia", required=False) or date.today()
        svc.change_status(db, actor=user, c=c, new_status=form.get("status", ""), effective_date=when, note=form.get("notatka", ""))
    except (FormError, svc.BusinessError) as e:
        db.rollback()
        return render(request, "umowa.html", _contract_ctx(user, c, form, str(e)), 400)
    flash(request, f"Status umowy: {c.status}, od {fmt_date(when)}. Zmiana zapisana w historii.")
    return redirect(f"/umowy/{c.id}")


def valid_nip(nip: str) -> bool:
    if len(nip) != 10 or not nip.isdigit():
        return False
    weights = [6, 5, 7, 2, 3, 4, 5, 6, 7]
    check = sum(int(d) * w for d, w in zip(nip, weights)) % 11
    return check != 10 and check == int(nip[9])
