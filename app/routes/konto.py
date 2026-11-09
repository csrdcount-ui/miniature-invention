"""Logowanie, pierwsze uruchomienie, konto, dane osobowe i firmy, hasło."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from datetime import datetime

from ..db import get_db
from ..models import (
    BOK_PERMISSIONS,
    POLICY_SETTINGS,
    PermissionChange,
    ROLE_OWNER,
    Company,
    User,
)
from ..security import hash_password, verify_password
from ..web.auth import company_of, current_user, needs_completion, owner_only
from ..web.forms import company_error, names_error, validate_new_user
from ..web.ui import (
    flash,
    form_data,
    redirect,
    render,
)

router = APIRouter()

def _no_users(db: Session) -> bool:
    return db.scalar(select(func.count(User.id))) == 0


@router.get("/", include_in_schema=False)
def index(request: Request):
    return redirect("/pulpit" if request.session.get("uid") else "/logowanie")


@router.get("/logowanie", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    if _no_users(db):
        return redirect("/start")
    return render(request, "logowanie.html")


@router.post("/logowanie")
async def login(request: Request, db: Session = Depends(get_db)):
    form = await form_data(request)
    email = form.get("email", "").lower()
    user = db.scalar(select(User).where(User.email == email))
    if not user or not user.active or not verify_password(form.get("haslo", ""), user.password_hash):
        return render(
            request, "logowanie.html", {"error": "Nieprawidłowy e-mail lub hasło.", "email": email}, 401
        )
    user.last_login_at = datetime.utcnow()
    db.commit()
    request.session.clear()
    request.session["uid"] = user.id
    request.session["sv"] = user.session_version
    return redirect("/pulpit")


@router.post("/wyloguj")
async def logout(request: Request):
    await form_data(request)
    request.session.clear()
    return redirect("/logowanie")


@router.post("/konto/wyloguj-wszystkie")
async def logout_everywhere(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Unieważnia wszystkie inne sesje tej osoby (nie tylko na tym urządzeniu)."""
    await form_data(request)
    user.session_version += 1
    db.commit()
    request.session["sv"] = user.session_version  # ta sesja zostaje zalogowana
    flash(request, "Wylogowano wszystkie inne urządzenia i przeglądarki. To urządzenie zostaje zalogowane.")
    return redirect("/konto")


@router.get("/start", response_class=HTMLResponse)
def setup_page(request: Request, db: Session = Depends(get_db)):
    if not _no_users(db):
        return redirect("/logowanie")
    return render(request, "start.html")


@router.post("/start")
async def setup(request: Request, db: Session = Depends(get_db)):
    form = await form_data(request)
    if not _no_users(db):
        return redirect("/logowanie")
    err = company_error(form) or validate_new_user(form, db, require_role=False)
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


@router.get("/konto", response_class=HTMLResponse)
def account_page(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    company = company_of(db)
    ctx = {"user": user, "company": company}
    if user.role == ROLE_OWNER and company:
        ctx["bok_settings"] = [
            {"key": k, "label": lab, "desc": desc, "on": bool(getattr(company, k)), "works": works}
            for k, (lab, desc, _, works) in BOK_PERMISSIONS.items()
        ]
        ctx["policy_settings"] = [
            {"key": k, "label": lab, "desc": desc, "on": bool(getattr(company, k))}
            for k, (lab, desc, _) in POLICY_SETTINGS.items()
        ]
        ctx["bok_history"] = list(
            db.scalars(select(PermissionChange).order_by(PermissionChange.changed_at.desc(), PermissionChange.id.desc()).limit(20))
        )
    return render(request, "konto.html", ctx)


@router.post("/konto/polityka")
async def policy_save(request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    form = await form_data(request)
    company = company_of(db)
    if not company:
        return redirect("/konto/dane")
    changes = []
    for key, (label, _, _) in POLICY_SETTINGS.items():
        new, old = form.get(key) == "1", bool(getattr(company, key))
        if new != old:
            setattr(company, key, new)
            db.add(PermissionChange(setting=key, old_value=old, new_value=new, changed_by_id=user.id))
            changes.append(f"{label}: {'włączone' if new else 'wyłączone'}")
    db.commit()
    flash(request, "Zapisano politykę biura. " + ("; ".join(changes) + "." if changes else "Bez zmian."))
    return redirect("/konto#polityka")


@router.post("/konto/uprawnienia-bok")
async def bok_permissions_save(request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    form = await form_data(request)
    company = company_of(db)
    if not company:
        return redirect("/konto/dane")
    changes = []
    for key, (label, _, _, _) in BOK_PERMISSIONS.items():
        new = form.get(key) == "1"
        old = bool(getattr(company, key))
        if new != old:
            setattr(company, key, new)
            db.add(PermissionChange(setting=key, old_value=old, new_value=new, changed_by_id=user.id))
            changes.append(f"{label}: {'włączone' if new else 'wyłączone'}")
    db.commit()
    flash(request, "Zapisano uprawnienia BOK. " + ("; ".join(changes) + "." if changes else "Bez zmian."))
    return redirect("/konto#uprawnienia-bok")


def _account_data_ctx(user: User, db: Session, form: Optional[dict] = None, error: Optional[str] = None) -> dict:
    company = company_of(db)
    return {
        "user": user,
        "company": company,
        "incomplete": needs_completion(user, company),
        "form": form or {"imie": user.first_name, "nazwisko": user.last_name, "firma": company.name if company else ""},
        "error": error,
    }


@router.get("/konto/dane", response_class=HTMLResponse)
def account_data_page(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return render(request, "konto_dane.html", _account_data_ctx(user, db))


@router.post("/konto/dane")
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


@router.get("/haslo", response_class=HTMLResponse)
def password_page(request: Request, user: User = Depends(current_user)):
    return render(request, "haslo.html", {"user": user})


@router.post("/haslo")
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
