"""Szablony, formatowanie liczb i dat, sesja (CSRF, komunikaty), odpowiedzi."""
from __future__ import annotations

import secrets
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import engine as eng
from ..models import (
    PRICING_PRODUCTS,
    BOK_PERMISSIONS,
    ROLE_BOK,
    SELLING_ROLES,
    CONTRACT_STATUSES,
    MEDIA,
    ROLE_MANAGER,
    ROLE_OWNER,
    ROLE_TRADER,
    ROLES,
    STATUSES_REQUIRING_NOTE,
    TRIGGERS,
)
from ..security import new_csrf_token
from .navigation import navigation

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")


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
    ROLE_BOK=ROLE_BOK,
    SELLING_ROLES=SELLING_ROLES,
    BOK_PERMISSIONS=BOK_PERMISSIONS,
    PRICING_PRODUCTS=PRICING_PRODUCTS,
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
# Sesja, CSRF, komunikaty, odpowiedzi
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
    ctx["nav"] = navigation(
        ctx["user"], request.url.path, bok_sees_commissions=bool(getattr(request.state, "bok_sees_commissions", False))
    )
    ctx["brand"] = getattr(request.state, "company_name", None) or "Platforma brokerska"
    ctx["demo_active"] = bool(getattr(request.state, "demo_active", False)) and ctx["user"] is not None
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)
