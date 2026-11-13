"""Platforma brokerska — aplikacja webowa (FastAPI, strony renderowane na serwerze).

Strony działają bez JavaScriptu i są budowane pod czytnik ekranu oraz telefon.

Budowa (modularny monolit, jedna baza):
- app/web/      szablony, sesja, uprawnienia, formularze, nawigacja,
- app/routes/   strony według modułów: konto, portfel, spółki, zespół, raporty,
- app/services.py, app/engine.py   logika biznesowa i silnik prowizji (bez HTTP).
"""
from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from . import migrate
from .db import Base, engine
from .models import ROLE_OWNER, Company, User, split_full_name
from .routes import cenniki, faktury, klienci, samouczek, konto, portfel, raporty, spolki, system, wymiana, zespol
from .security import hash_password
from .web.auth import LoginRequired, ProfileIncomplete, COMPLETION_URL
from .web.ui import BASE_DIR, redirect, render

SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_urlsafe(48)
SECURE_COOKIES = os.environ.get("SECURE_COOKIES", "0") == "1"

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Tabele, migracje i konto właściciela przed przyjęciem pierwszego żądania.
    # (Zamiast przestarzałego @app.on_event("startup").)
    _startup()
    yield


app = FastAPI(title="Platforma brokerska", docs_url=None, redoc_url=None, openapi_url=None, lifespan=_lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax",
    https_only=SECURE_COOKIES,
    max_age=60 * 60 * 12,
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

for module in (konto, wymiana, faktury, samouczek, klienci, cenniki, portfel, spolki, zespol, raporty, system):
    app.include_router(module.router)


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


@app.exception_handler(ProfileIncomplete)
async def _profile_incomplete(request: Request, exc: ProfileIncomplete):
    return redirect(COMPLETION_URL)


@app.exception_handler(LoginRequired)
async def _login_required(request: Request, exc: LoginRequired):
    return redirect("/logowanie")


@app.exception_handler(StarletteHTTPException)
@app.exception_handler(HTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    # Także nieistniejące adresy: polska strona zamiast {"detail":"Not Found"}.
    messages = {403: "Brak dostępu do tej strony.", 404: "Nie znaleziono strony."}
    return render(
        request,
        "blad.html",
        {"message": exc.detail if exc.status_code == 400 else messages.get(exc.status_code, exc.detail)},
        status_code=exc.status_code,
    )
