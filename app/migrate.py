"""Proste migracje istniejącej bazy, uruchamiane przy starcie aplikacji.

create_all() tworzy tylko brakujące tabele, nie dodaje kolumn do istniejących.
Tu dodajemy nowe kolumny i uzupełniamy dane. Każdy krok jest bezpieczny
do wielokrotnego uruchomienia.
"""
from __future__ import annotations

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .models import BOK_PERMISSIONS, POLICY_SETTINGS, SystemFlag, Contract, ContractStatusEvent, User, split_full_name


def _add_column(engine: Engine, table: str, column: str, ddl: str) -> None:
    cols = {c["name"] for c in inspect(engine).get_columns(table)}
    if column not in cols:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def run(engine: Engine) -> None:
    """Najpierw WSZYSTKIE zmiany schematu, potem zmiany danych.

    Kroki danych używają modeli ORM, które odwołują się do każdej kolumny modelu.
    Gdyby którakolwiek kolumna jeszcze nie istniała, zapytanie by się wywróciło.
    """
    if not inspect(engine).has_table("users"):
        return
    _schema(engine)
    _split_names(engine)
    _baseline_status_history(engine)
    _one_time_clean_start(engine)


def _schema(engine: Engine) -> None:
    _add_column(engine, "users", "first_name", "VARCHAR(100) NOT NULL DEFAULT ''")
    _add_column(engine, "users", "last_name", "VARCHAR(100) NOT NULL DEFAULT ''")
    _add_column(engine, "users", "last_login_at", "TIMESTAMP")
    _add_column(engine, "users", "session_version", "INTEGER NOT NULL DEFAULT 0")
    _add_column(engine, "contracts", "pricing_product", "VARCHAR(10) NOT NULL DEFAULT 'fix'")
    # paczki importu: ext_id i import_batch_id w tabelach z importem
    if inspect(engine).has_table("import_batches"):
        for table in ("users", "suppliers", "supplier_rule_sets", "contracts"):
            if inspect(engine).has_table(table):
                _add_column(engine, table, "ext_id", "VARCHAR(100)")
                _add_column(engine, table, "import_batch_id", "INTEGER REFERENCES import_batches(id)")
    if inspect(engine).has_table("company"):
        for key, (_, _, default, _) in BOK_PERMISSIONS.items():
            _add_column(engine, "company", key, f"BOOLEAN NOT NULL DEFAULT {'TRUE' if default else 'FALSE'}")
        for key, (_, _, default) in POLICY_SETTINGS.items():
            _add_column(engine, "company", key, f"BOOLEAN NOT NULL DEFAULT {'TRUE' if default else 'FALSE'}")


def _split_names(engine: Engine) -> None:
    """Konta sprzed podziału: rozdziel dotychczasowe „name”."""
    with Session(engine) as db:
        changed = False
        for u in db.scalars(select(User).where(User.first_name == "", User.last_name == "")):
            first, last = split_full_name(u.name)
            u.first_name, u.last_name = first, last
            changed = True
        if changed:
            db.commit()


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


# Jednorazowy czysty start na życzenie właścicielki (10.11.2026): konto testowe Boss01 i dane
# demonstracyjne mają zniknąć, a po wdrożeniu aplikacja ma przejść pełne pierwsze uruchomienie.
# Kasowanie wykona się RAZ — znacznik w tabeli system_flags blokuje powtórzenie przy kolejnych
# wdrożeniach. Po potwierdzeniu, że poszło, ten kod można usunąć.
CLEAN_START_FLAG = "czysty-start-2026-11-10"


def _one_time_clean_start(engine: Engine) -> None:
    with Session(engine) as db:
        if db.get(SystemFlag, CLEAN_START_FLAG):
            return
    from .db import Base

    names = [t.name for t in Base.metadata.sorted_tables if t.name != SystemFlag.__tablename__]
    existing = set(inspect(engine).get_table_names())
    names = [n for n in names if n in existing]
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            if names:
                conn.execute(text("TRUNCATE TABLE " + ", ".join(f'"{n}"' for n in names) + " RESTART IDENTITY CASCADE"))
        else:
            for n in reversed(names):
                conn.execute(text(f'DELETE FROM "{n}"'))
    with Session(engine) as db:
        db.add(SystemFlag(key=CLEAN_START_FLAG))
        db.commit()
    print(f"[migrate] Czysty start wykonany ({CLEAN_START_FLAG}): wyczyszczono tabele {', '.join(names)}.", flush=True)
