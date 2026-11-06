"""Proste migracje istniejącej bazy, uruchamiane przy starcie aplikacji.

create_all() tworzy tylko brakujące tabele, nie dodaje kolumn do istniejących.
Tu dodajemy nowe kolumny i uzupełniamy dane. Każdy krok jest bezpieczny
do wielokrotnego uruchomienia.
"""
from __future__ import annotations

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .models import User, split_full_name


def _add_column(engine: Engine, table: str, column: str, ddl: str) -> None:
    cols = {c["name"] for c in inspect(engine).get_columns(table)}
    if column not in cols:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def run(engine: Engine) -> None:
    if not inspect(engine).has_table("users"):
        return
    _add_column(engine, "users", "first_name", "VARCHAR(100) NOT NULL DEFAULT ''")
    _add_column(engine, "users", "last_name", "VARCHAR(100) NOT NULL DEFAULT ''")
    # Konta sprzed podziału: rozdziel dotychczasowe „name”.
    with Session(engine) as db:
        changed = False
        for u in db.scalars(select(User).where(User.first_name == "", User.last_name == "")):
            first, last = split_full_name(u.name)
            u.first_name, u.last_name = first, last
            changed = True
        if changed:
            db.commit()
