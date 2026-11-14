"""Zalogowany użytkownik, uprawnienia ról i wymuszenie uzupełnienia danych."""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ROLE_BOK, ROLE_MANAGER, ROLE_OWNER, Company, User


class LoginRequired(Exception):
    pass


class ProfileIncomplete(Exception):
    pass


COMPLETION_URL = "/konto/dane"
COMPLETION_ALLOWED = {COMPLETION_URL, "/wyloguj"}


def company_of(db: Session) -> Optional[Company]:
    return db.scalar(select(Company).order_by(Company.id))


def bok_perms(db: Session):
    """Uprawnienia BOK z ustawień firmy (import lokalny: auth nie zależy od usług przy imporcie)."""
    from ..services import BokPerms

    return BokPerms.of(company_of(db))


def needs_completion(user: User, company: Optional[Company]) -> bool:
    if user.needs_last_name or len(user.first_name or "") < 2:
        return True
    return user.role == ROLE_OWNER and company is None


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("uid")
    if not uid:
        raise LoginRequired()
    user = db.get(User, uid)
    if not user or not user.active:
        request.session.clear()
        raise LoginRequired()
    # „Wyloguj wszystkie inne urządzenia” podbija session_version: cookie z inną
    # wartością przestaje być ważne. Sesje sprzed wprowadzenia tej funkcji nie mają
    # jeszcze klucza "sv" — przyjmują bieżącą wartość, zamiast wylogowywać wszystkich
    # od razu po wdrożeniu.
    sv = request.session.get("sv")
    if sv is None:
        request.session["sv"] = user.session_version
    elif sv != user.session_version:
        request.session.clear()
        raise LoginRequired()
    company = company_of(db)
    request.state.company_name = company.name if company else None
    from ..services import BokPerms

    request.state.bok_sees_commissions = BokPerms.of(company).bok_sees_commissions
    from ..exchange.importer import demo_active

    request.state.demo_active = demo_active(db)
    from ..samouczek import invite_visible

    request.state.tutorial_invite = invite_visible(db, user) and not request.url.path.startswith(("/samouczek", "/haslo"))
    from ..powiadomienia import unseen_count

    request.state.unseen_notifications = unseen_count(db, user)
    if request.url.path not in COMPLETION_ALLOWED and needs_completion(user, company):
        raise ProfileIncomplete()
    return user


def owner_only(user: User = Depends(current_user)) -> User:
    if user.role != ROLE_OWNER:
        raise HTTPException(status_code=403)
    return user


def owner_or_bok_commissions(user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
    """Właściciel zawsze; BOK tylko gdy widzi prowizje handlowców (ta sama przesłanka:
    kto już widzi zarobki, temu można powierzyć też reset hasła tej osoby)."""
    if user.role == ROLE_OWNER:
        return user
    if user.role == ROLE_BOK and bok_perms(db).bok_sees_commissions:
        return user
    raise HTTPException(status_code=403)


def team_viewer(user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
    """Zakładka Zespół: właściciel, menedżer (tylko swoi ludzie) i BOK z wglądem w prowizje."""
    if user.role in (ROLE_OWNER, ROLE_MANAGER):
        return user
    if user.role == ROLE_BOK and bok_perms(db).bok_sees_commissions:
        return user
    raise HTTPException(status_code=403)
