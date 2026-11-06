"""Proste migracje istniejącej bazy, uruchamiane przy starcie aplikacji.

create_all() tworzy tylko brakujące tabele, nie dodaje kolumn do istniejących.
Tu dodajemy nowe kolumny i uzupełniamy dane. Każdy krok jest bezpieczny
do wielokrotnego uruchomienia.
"""
from __future__ import annotations

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .models import Contract, ContractStatusEvent, User, split_full_name


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
    _baseline_status_history(engine)


def _baseline_status_history(engine: Engine) -> None:
    """Umowy bez historii dostają jeden wiersz „stan w chwili włączenia historii”."""
    if not inspect(engine).has_table("contract_status_events"):
        return
    with Session(engine) as db:
        have = select(ContractStatusEvent.contract_id)
        missing = list(db.scalars(select(Contract).where(Contract.id.not_in(have))))
        for c in missing:
            db.add(
                ContractStatusEvent(
                    contract_id=c.id,
                    from_status=None,
                    to_status=c.status,
                    effective_date=(c.created_at.date() if c.created_at else c.signed_date),
                    changed_by_id=None,
                    note="Stan w chwili włączenia historii statusów. Wcześniejsze zmiany nie były zapisywane.",
                    baseline=True,
                )
            )
        if missing:
            db.commit()
