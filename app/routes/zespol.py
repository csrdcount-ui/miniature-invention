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
    ROLE_TRADER,
    SELLING_ROLES,
    ROLE_MANAGER,
    ROLE_OWNER,
    User,
    UserRate,
)
from ..security import hash_password
from ..web.auth import owner_only
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
    form_data,
    redirect,
    render,
)

router = APIRouter()

def _managers(db: Session) -> list[User]:
    return list(db.scalars(select(User).where(User.role == ROLE_MANAGER, User.active.is_(True)).order_by(User.last_name, User.first_name)))


@router.get("/zespol", response_class=HTMLResponse)
def team_page(request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    people = list(db.scalars(select(User).order_by(User.role, User.last_name, User.first_name)))
    rows = [(p, svc.current_rate(p)) for p in people]
    return render(request, "zespol.html", {"user": user, "rows": rows})


@router.get("/zespol/nowa", response_class=HTMLResponse)
def team_new_page(request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    return render(request, "zespol_nowa.html", {"user": user, "managers": _managers(db), "form": {}})


@router.post("/zespol")
async def team_add(request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    form = await form_data(request)
    err = validate_new_user(form, db)
    manager_id = None
    if not err and form.get("menedzer"):
        m = db.get(User, int(form["menedzer"])) if form["menedzer"].isdigit() else None
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


@router.get("/zespol/{uid}", response_class=HTMLResponse)
def person_page(uid: int, request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    p = _get_user(db, uid)
    return render(
        request,
        "osoba.html",
        {"user": user, "p": p, "current": svc.current_rate(p), "managers": _managers(db), "today": date.today(), "form": {}},
    )


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
            {"user": user, "p": p, "current": svc.current_rate(p), "managers": _managers(db), "today": date.today(), "error": str(e), "form": form},
            400,
        )
    db.add(r)
    db.commit()
    flash(request, f"Zapisano nowe stawki dla {p.name} od {fmt_date(r.valid_from)}.")
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
                {"user": user, "p": p, "current": svc.current_rate(p), "managers": _managers(db), "today": date.today(), "error": err, "form": {}},
                400,
            )
        p.set_names(form["imie"], form["nazwisko"])
    if p.role in (ROLE_MANAGER, ROLE_TRADER):
        mid = form.get("menedzer", "")
        if mid == "":
            p.manager_id = None
        elif mid.isdigit():
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
