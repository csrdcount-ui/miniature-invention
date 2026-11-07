"""Zalogowany użytkownik, uprawnienia ról i wymuszenie uzupełnienia danych."""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ROLE_OWNER, Company, User


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
