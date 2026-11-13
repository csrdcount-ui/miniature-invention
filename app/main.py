"""Platforma brokerska — aplikacja webowa (FastAPI, strony renderowane na serwerze).

Strony działają bez JavaScriptu i są budowane pod czytnik ekranu oraz telefon.
"""
from __future__ import annotations

import csv
import io
import os
import secrets
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from . import engine as eng
from . import services as svc
from . import settlements as st
from .db import Base, engine, get_db
from .models import (
    CONTRACT_STATUSES,
    ENTRY_KINDS,
    MEDIA,
    ROLE_MANAGER,
    ROLE_OWNER,
    ROLE_TRADER,
    ROLES,
    TRIGGERS,
    Contract,
    PayoutEntry,
    Supplier,
    SupplierRuleSet,
    User,
    UserRate,
)
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
    _bootstrap_owner_from_env()


def _bootstrap_owner_from_env() -> None:
    email = os.environ.get("OWNER_EMAIL")
    password = os.environ.get("OWNER_PASSWORD")
    if not email or not password:
        return
    from .db import SessionLocal

    with SessionLocal() as db:
        if db.scalar(select(func.count(User.id))) == 0:
            db.add(
                User(
                    email=email.lower().strip(),
                    name=os.environ.get("OWNER_NAME", "Właściciel"),
                    password_hash=hash_password(password),
                    role=ROLE_OWNER,
                )
            )
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
    ENTRY_KINDS=ENTRY_KINDS,
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
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


class LoginRequired(Exception):
    pass


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
    err = _validate_new_user(form, db, require_role=False)
    if err:
        return render(request, "start.html", {"error": err, "form": form}, 400)
    u = User(
        email=form["email"].lower(),
        name=form["imie"],
        password_hash=hash_password(form["haslo"]),
        role=ROLE_OWNER,
    )
    db.add(u)
    db.commit()
    request.session.clear()
    request.session["uid"] = u.id
    flash(request, "Konto właściciela utworzone. Zacznij od dodania spółki obrotu i jej reguł.")
    return redirect("/spolki")


def _validate_new_user(form: dict, db: Session, require_role: bool = True) -> Optional[str]:
    if not form.get("imie"):
        return "Podaj imię i nazwisko."
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
    return redirect("/pulpit")


# --------------------------------------------------------------------------
# Pulpit
# --------------------------------------------------------------------------

@app.get("/pulpit", response_class=HTMLResponse)
def dashboard(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    contracts = list(db.scalars(svc.visible_contracts_query(user)))
    summary = svc.summary_for(user, contracts)
    ctx = {
        "user": user,
        "summary": summary,
        "recent": [svc.contract_view(user, c) for c in contracts[:5]],
        "reg": st.register_view(user, contracts, date.today()),
    }
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


@app.post("/spolki")
async def supplier_add(request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    form = await form_data(request)
    name = form.get("nazwa", "")
    if not name:
        flash(request, "Błąd: podaj nazwę spółki.")
        return redirect("/spolki")
    if db.scalar(select(Supplier).where(Supplier.name == name)):
        flash(request, f"Błąd: spółka {name} już istnieje.")
        return redirect("/spolki")
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
    return list(db.scalars(select(User).where(User.role == ROLE_MANAGER, User.active.is_(True)).order_by(User.name)))


@app.get("/zespol", response_class=HTMLResponse)
def team_page(request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    people = list(db.scalars(select(User).order_by(User.role, User.name)))
    rows = [(p, svc.current_rate(p)) for p in people]
    return render(request, "zespol.html", {"user": user, "rows": rows, "managers": _managers(db), "form": {}})


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
        people = list(db.scalars(select(User).order_by(User.role, User.name)))
        rows = [(p, svc.current_rate(p)) for p in people]
        return render(
            request, "zespol.html", {"user": user, "rows": rows, "managers": _managers(db), "error": err, "form": form}, 400
        )
    u = User(
        email=form["email"].lower(),
        name=form["imie"],
        password_hash=hash_password(form["haslo"]),
        role=form["rola"],
        manager_id=manager_id if form["rola"] != ROLE_OWNER else None,
    )
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


@app.get("/umowy/{cid}", response_class=HTMLResponse)
def contract_page(cid: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _get_visible_contract(db, user, cid)
    return render(request, "umowa.html", _contract_ctx(user, c))


def _contract_ctx(user: User, c: Contract, **extra) -> dict:
    today = date.today()
    ctx = {
        "user": user,
        "c": svc.contract_view(user, c),
        "s": st.contract_settlement_view(user, c, today),
        "today": today,
        "form": {},
    }
    ctx.update(extra)
    return ctx


@app.post("/umowy/{cid}/status")
async def contract_status(cid: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _get_visible_contract(db, user, cid)
    form = await form_data(request)
    status = form.get("status")
    if status not in CONTRACT_STATUSES or not svc.can_edit_status(user, c):
        raise HTTPException(status_code=400, detail="Niepoprawny status.")
    c.status = status
    db.commit()
    flash(request, f"Status umowy: {status}.")
    return redirect(f"/umowy/{c.id}")


# --------------------------------------------------------------------------
# Rozliczenia: wpływy od spółek, korekty, wypłaty dla zespołu
# --------------------------------------------------------------------------

@app.post("/umowy/{cid}/rozliczenia")
async def contract_entry_add(cid: int, request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    c = _get_visible_contract(db, user, cid)
    form = await form_data(request)
    try:
        kind = form.get("rodzaj", "")
        entry = st.record_entry(
            db,
            actor=user,
            contract=c,
            kind=kind,
            booked_on=p_date(form, "data", "Data wpływu"),
            amount=p_dec(form, "kwota", "Kwota od spółki", minimum=Decimal("0.01")),
            note=form.get("uwagi", ""),
            mark_broken=form.get("zerwana") == "1",
        )
    except (FormError, svc.BusinessError, eng.EngineError) as e:
        db.rollback()
        return render(request, "umowa.html", _contract_ctx(user, c, error=str(e), form=form), 400)
    if entry.kind == st.KOREKTA:
        flash(
            request,
            f"Zapisano korektę {fmt_zl(-entry.broker_amount)}. Handlowiec oddaje {fmt_zl(-entry.trader_amount)}"
            + (f", menedżer {fmt_zl(-entry.override_amount)}" if c.manager_id else "")
            + f". Status umowy: {c.status}.",
        )
    else:
        flash(
            request,
            f"Zapisano wpływ {fmt_zl(entry.broker_amount)}. Należy się handlowcowi {fmt_zl(entry.trader_amount)}"
            + (f", menedżerowi {fmt_zl(entry.override_amount)}" if c.manager_id else "")
            + f". Status umowy: {c.status}.",
        )
    return redirect(f"/umowy/{c.id}#rozliczenia")


def _get_entry(db: Session, eid: int) -> PayoutEntry:
    e = db.get(PayoutEntry, eid)
    if not e:
        raise HTTPException(status_code=404)
    return e


def _back(form: dict, default: str) -> str:
    url = form.get("wroc", "")
    # tylko ścieżki wewnętrzne, bez przekierowań na zewnątrz
    return url if url.startswith("/") and not url.startswith("//") else default


@app.post("/rozliczenia/{eid}/wyplata")
async def entry_mark_paid(eid: int, request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    e = _get_entry(db, eid)
    form = await form_data(request)
    back = _back(form, f"/umowy/{e.contract_id}#rozliczenia")
    try:
        paid_on = p_date(form, "data", "Data wypłaty", required=False) or date.today()
        st.mark_paid(db, actor=user, entry=e, who=form.get("komu", ""), paid_on=paid_on)
    except (FormError, svc.BusinessError) as err:
        flash(request, f"Błąd: {err}")
        return redirect(back)
    who = e.contract.trader.name if form.get("komu") == "handlowiec" else (e.contract.manager.name if e.contract.manager else "")
    amount = e.trader_amount if form.get("komu") == "handlowiec" else e.override_amount
    verb = "potrącenie" if amount < 0 else "wypłatę"
    flash(request, f"Oznaczono {verb} {fmt_zl(abs(amount))} dla {who}, {e.contract.client_name}, z dnia {fmt_date(paid_on)}.")
    return redirect(back)


@app.post("/rozliczenia/{eid}/usun")
async def entry_delete(eid: int, request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    e = _get_entry(db, eid)
    form = await form_data(request)
    cid = e.contract_id
    try:
        st.delete_entry(db, actor=user, entry=e)
    except svc.BusinessError as err:
        flash(request, f"Błąd: {err}")
        return redirect(f"/umowy/{cid}#rozliczenia")
    flash(request, "Usunięto wpis z rejestru. Status umowy nie został zmieniony, popraw go ręcznie, jeśli trzeba.")
    return redirect(_back(form, f"/umowy/{cid}#rozliczenia"))


@app.get("/rozliczenia", response_class=HTMLResponse)
def register_page(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    contracts = list(db.scalars(svc.visible_contracts_query(user)))
    today = date.today()
    return render(request, "rozliczenia.html", {"user": user, "r": st.register_view(user, contracts, today), "today": today})


@app.get("/rozliczenia.csv")
def register_csv(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Eksport do Excela: średnik, przecinek dziesiętny, kodowanie z BOM."""
    contracts = list(db.scalars(svc.visible_contracts_query(user)))
    today = date.today()
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Umowa", "Klient", "Spółka", "Data", "Rodzaj", "Strona", "Kwota", "Wypłacono dnia"])

    def num(v):
        return f"{eng.D(v):f}".replace(".", ",")

    for c in contracts:
        view = st.contract_settlement_view(user, c, today)
        for e in view["entries"]:
            for label, amt in e["amounts"]:
                paid = ""
                if label.startswith(("Handlowiec", "Twoja prowizja", "Prowizja handlowca")):
                    paid = fmt_date(e.get("trader_paid_on")) if e.get("trader_paid_on") else ""
                elif "override" in label.lower():
                    paid = fmt_date(e.get("manager_paid_on")) if e.get("manager_paid_on") else ""
                w.writerow([c.id, c.client_name, c.supplier.name, e["booked_on"].isoformat(), e["kind_label"], label, num(amt), paid])
    data = "\ufeff" + buf.getvalue()
    return Response(
        content=data.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="rozliczenia-{today.isoformat()}.csv"'},
    )


def valid_nip(nip: str) -> bool:
    if len(nip) != 10 or not nip.isdigit():
        return False
    weights = [6, 5, 7, 2, 3, 4, 5, 6, 7]
    check = sum(int(d) * w for d, w in zip(nip, weights)) % 11
    return check != 10 and check == int(nip[9])
