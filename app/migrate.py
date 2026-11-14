"""Proste migracje istniejącej bazy, uruchamiane przy starcie aplikacji.

create_all() tworzy tylko brakujące tabele, nie dodaje kolumn do istniejących.
Tu dodajemy nowe kolumny i uzupełniamy dane. Każdy krok jest bezpieczny
do wielokrotnego uruchomienia.
"""
from __future__ import annotations

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .models import BOK_PERMISSIONS, POLICY_SETTINGS, Contract, ContractStatusEvent, User, split_full_name


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
    _offer_followup_text(engine)


def _schema(engine: Engine) -> None:
    # 13.11.2026: archiwizacja zdjęć faktur (tabele powstały w tej samej porcji zmian; na wszelki wypadek)
    if inspect(engine).has_table("invoice_photos"):
        _add_column(engine, "invoice_photos", "downloaded_at", "TIMESTAMP")
        _add_column(engine, "invoice_photos", "downloaded_by_id", "INTEGER REFERENCES users(id)")
    if inspect(engine).has_table("invoice_tasks"):
        _add_column(engine, "invoice_tasks", "archived_at", "TIMESTAMP")
        _add_column(engine, "invoice_tasks", "archived_by_id", "INTEGER REFERENCES users(id)")
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


OLD_FOLLOWUP = "Zadzwoń w sprawie oferty: jak się podoba, czy coś poprawić"
NEW_FOLLOWUP = "Zadzwoń i sprawdź, co ze złożoną ofertą"


def _offer_followup_text(engine: Engine) -> None:
    """14.11.2026: nowe brzmienie następnego kroku po ofercie (prośba właścicielki). Podmienia tylko
    dokładnie stary tekst wpisany przez platformę; tekstów wpisanych ręcznie nie rusza."""
    if not inspect(engine).has_table("clients"):
        return
    with engine.begin() as conn:
        conn.execute(text("UPDATE clients SET next_step = :new WHERE next_step = :old"),
                     {"new": NEW_FOLLOWUP, "old": OLD_FOLLOWUP})


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
