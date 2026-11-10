"""Zespół i stawki (tylko właściciel)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import engine as eng
from .. import services as svc
from ..db import get_db
from ..models import (
    ROLE_BOK,
    ROLE_TRADER,
    SELLING_ROLES,
    ROLE_MANAGER,
    ROLE_OWNER,
    Contract,
    User,
    UserRate,
)
from ..security import hash_password, new_password
from ..web.auth import owner_only, owner_or_bok_commissions, team_viewer
from ..web.forms import is_id
from ..web.forms import (
    FormError,
    names_error,
    p_date,
    p_dec,
    validate_new_user,
)
from ..web.ui import (
    flash,
    fmt_date,
    fmt_zl,
    form_data,
    redirect,
    render,
)

router = APIRouter()

def _managers(db: Session) -> list[User]:
    return list(db.scalars(select(User).where(User.role == ROLE_MANAGER, User.active.is_(True)).order_by(User.last_name, User.first_name)))


@router.get("/zespol", response_class=HTMLResponse)
def team_page(request: Request, user: User = Depends(team_viewer), db: Session = Depends(get_db)):
    q = select(User).order_by(User.role, User.last_name, User.first_name)
    if user.role == ROLE_BOK:
        q = q.where(User.role.in_((ROLE_MANAGER, ROLE_TRADER)))
    if user.role == ROLE_MANAGER:
        q = q.where(User.manager_id == user.id)
    people = list(db.scalars(q))
    month = svc.month_start()
    rows = [
        (p, svc.current_rate(p), svc.month_sales(db, [p.id], month) if p.role in SELLING_ROLES else None)
        for p in people
    ]
    start = svc.add_months(month, -5)
    rhythm = {
        p.id: svc.monthly_stats(list(db.scalars(select(Contract).where(Contract.trader_id == p.id))), start, month)["active"]
        for p, _, m in rows if m is not None
    }
    return render(request, "zespol.html", {
        "user": user, "rows": rows, "month_label": svc.month_label(month),
        "ranking": svc.team_ranking(rows), "rhythm": rhythm,
    })


@router.get("/zespol/nowa", response_class=HTMLResponse)
def team_new_page(request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    return render(request, "zespol_nowa.html", {"user": user, "managers": _managers(db), "form": {}})


@router.post("/zespol")
async def team_add(request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    form = await form_data(request)
    err = validate_new_user(form, db)
    manager_id = None
    if not err and form.get("menedzer"):
        m = db.get(User, int(form["menedzer"])) if is_id(form["menedzer"]) else None
        if not m or m.role != ROLE_MANAGER:
            err = "Wybrany menedżer nie istnieje."
        else:
            manager_id = m.id
    rate = None
    sells = form.get("rola") in SELLING_ROLES
    if not err and sells:
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
        manager_id=manager_id if form["rola"] in (ROLE_MANAGER, ROLE_TRADER) else None,
    )
    u.set_names(form["imie"], form["nazwisko"])
    db.add(u)
    db.flush()
    if sells:
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


def _get_user_for_viewer(db: Session, viewer: User, uid: int) -> User:
    """Właściciel: każdy. Menedżer: tylko jego ludzie. BOK: menedżerowie i handlowcy."""
    if viewer.role == ROLE_OWNER:
        return _get_user(db, uid)
    if viewer.role == ROLE_MANAGER:
        u = _get_user(db, uid)
        if u.manager_id != viewer.id:
            raise HTTPException(status_code=404)
        return u
    return _get_user_for_bok(db, uid)


def _get_user_for_bok(db: Session, uid: int) -> User:
    """BOK zarządza tylko menedżerami i handlowcami — nigdy właścicielem ani innym BOK
    (nawet gdy widzi prowizje, nie powinien móc zresetować hasła właściciela)."""
    u = _get_user(db, uid)
    if u.role not in (ROLE_MANAGER, ROLE_TRADER):
        raise HTTPException(status_code=404)
    return u


def _person_ctx(db: Session, user: User, p: User, qp=None, **extra) -> dict:
    month = svc.month_start()
    nxt = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
    ctx = {
        "user": user, "p": p, "current": svc.current_rate(p), "managers": _managers(db), "today": date.today(),
        "form": {}, "month_label": svc.month_label(month),
        "sales": svc.month_sales(db, [p.id], month) if p.role in SELLING_ROLES else None,
        "can_target": svc.can_set_target(user, p),
        "targets": [(svc.month_label(m), m.strftime("%Y-%m"), svc.target_of(db, p.id, m)) for m in (month, nxt)],
    }
    if p.role in SELLING_ROLES:
        qp = qp or {}
        start, end = svc.month_range(qp.get("od_mies", ""), qp.get("do_mies", ""), default_months=12)
        ctx["stats"] = svc.person_stats(db, p, start, end)
        ctx["stats_open"] = "od_mies" in qp or "do_mies" in qp
    ctx.update(extra)
    return ctx


@router.get("/zespol/{uid}", response_class=HTMLResponse)
def person_page(uid: int, request: Request, user: User = Depends(team_viewer), db: Session = Depends(get_db)):
    p = _get_user_for_viewer(db, user, uid)
    return render(request, "osoba.html", _person_ctx(db, user, p, request.query_params))


@router.post("/zespol/{uid}/target")
async def person_target(uid: int, request: Request, user: User = Depends(team_viewer), db: Session = Depends(get_db)):
    p = _get_user_for_viewer(db, user, uid)
    form = await form_data(request)
    if not svc.can_set_target(user, p):
        raise HTTPException(status_code=403)
    raw_month = form.get("miesiac", "")
    try:
        y, m = (int(x) for x in raw_month.split("-")[:2])
        month = date(y, m, 1)
        amount = p_dec(form, "kwota", "Target masy marży", minimum=0)
    except (ValueError, FormError) as e:
        msg = str(e) if isinstance(e, FormError) else "Podaj miesiąc w formacie RRRR-MM, np. 2026-11."
        return render(request, "osoba.html", _person_ctx(db, user, p, error=msg), 400)
    svc.set_target(db, actor=user, person=p, month=month, amount=amount)
    flash(request, f"Zapisano target. Osoba: {p.name}, {svc.month_label(month)}: {fmt_zl(amount)}.")
    return redirect(f"/zespol/{p.id}")


@router.post("/zespol/{uid}/stawki")
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
            _person_ctx(db, user, p, error=str(e), form=form),
            400,
        )
    db.add(r)
    db.commit()
    flash(request, f"Zapisano nowe stawki. Osoba: {p.name}, od {fmt_date(r.valid_from)}.")
    return redirect(f"/zespol/{p.id}")


@router.post("/zespol/{uid}")
async def person_update(uid: int, request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    p = _get_user(db, uid)
    form = await form_data(request)
    if "imie" in form or "nazwisko" in form:
        err = names_error(form)
        if err:
            return render(
                request,
                "osoba.html",
                _person_ctx(db, user, p, error=err),
                400,
            )
        p.set_names(form["imie"], form["nazwisko"])
    if p.role in (ROLE_MANAGER, ROLE_TRADER):
        mid = form.get("menedzer", "")
        if mid == "":
            p.manager_id = None
        elif is_id(mid):
            m = db.get(User, int(mid))
            if m and m.role == ROLE_MANAGER and m.id != p.id:
                p.manager_id = m.id
    if p.role != ROLE_OWNER:
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


@router.post("/zespol/{uid}/reset-hasla")
async def person_reset_password(uid: int, request: Request, user: User = Depends(owner_or_bok_commissions), db: Session = Depends(get_db)):
    """Nadaje osobie nowe, losowe hasło. Pokazuje je raz, w tej jednej odpowiedzi."""
    p = _get_user(db, uid) if user.role == ROLE_OWNER else _get_user_for_bok(db, uid)
    await form_data(request)
    if p.id == user.id:
        # Własne hasło zmieniasz na /haslo, podając stare. Losowe hasło pokazane raz na własnym
        # koncie łatwo zgubić i zostać bez dostępu (nie ma odzyskiwania e-mailem).
        flash(request, "Własne hasło zmienisz w zakładce Konto, „Zmień hasło”. Tu możesz nadawać hasła innym osobom.")
        return redirect(f"/zespol/{p.id}")
    password = new_password()
    p.password_hash = hash_password(password)
    db.commit()
    return render(request, "osoba_haslo.html", {"user": user, "p": p, "password": password})
