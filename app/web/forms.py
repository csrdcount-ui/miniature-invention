"""Odczyt i walidacja pól formularzy. Komunikaty błędów po polsku, z nazwą pola."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import engine as eng
from ..models import ROLES, User
from .ui import fmt_num

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


def validate_new_user(form: dict, db: Session, require_role: bool = True) -> Optional[str]:
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


def valid_nip(nip: str) -> bool:
    if len(nip) != 10 or not nip.isdigit():
        return False
    weights = [6, 5, 7, 2, 3, 4, 5, 6, 7]
    check = sum(int(d) * w for d, w in zip(nip, weights)) % 11
    return check != 10 and check == int(nip[9])
