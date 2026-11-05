"""Model danych.

Zasada wersjonowania: reguły spółek i stawki osób mają datę obowiązywania.
Umowa w chwili zapisu kopiuje (zamraża) obowiązujące wtedy procenty, więc
zmiana warunków przez właściciela nie przelicza wstecz historii prowizji.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

ROLE_OWNER = "wlasciciel"
ROLE_MANAGER = "menedzer"
ROLE_TRADER = "handlowiec"
ROLES = {
    ROLE_OWNER: "Właściciel",
    ROLE_MANAGER: "Menedżer",
    ROLE_TRADER: "Handlowiec",
}

TRIGGERS = {
    "weryfikacja": "Po weryfikacji umowy przez spółkę",
    "zmiana_sprzedawcy": "Po potwierdzeniu zmiany sprzedawcy (OSD)",
    "start_dostaw": "Po starcie dostaw",
}

MEDIA = {"energia": "Energia elektryczna", "gaz": "Paliwo gazowe"}

CONTRACT_STATUSES = [
    "Lead",
    "Kontakt",
    "Oferta",
    "Umowa podpisana",
    "Weryfikacja spółki",
    "Zmiana sprzedawcy (OSD)",
    "Start dostaw",
    "Transza 1 wypłacona",
    "Rozliczenia bieżące",
    "Zakończona",
    "Zerwana",
]

PCT = Numeric(7, 3)
MONEY = Numeric(16, 2)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20))
    manager_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    manager: Mapped[Optional["User"]] = relationship(remote_side="User.id")
    rates: Mapped[list["UserRate"]] = relationship(
        back_populates="user", order_by="UserRate.valid_from.desc()", cascade="all, delete-orphan"
    )

    @property
    def role_label(self) -> str:
        return ROLES.get(self.role, self.role)


class UserRate(Base):
    """Stawki osoby: udział w narzucie i (dla menedżera) override."""

    __tablename__ = "user_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    valid_from: Mapped[date] = mapped_column(Date)
    trader_share_pct: Mapped[Decimal] = mapped_column(PCT, default=0)
    override_pct: Mapped[Decimal] = mapped_column(PCT, default=0)
    override_base: Mapped[str] = mapped_column(String(30), default="narzut")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="rates")


class Supplier(Base):
    """Spółka obrotu."""

    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    rule_sets: Mapped[list["SupplierRuleSet"]] = relationship(
        back_populates="supplier",
        order_by="SupplierRuleSet.valid_from.desc()",
        cascade="all, delete-orphan",
    )


class SupplierRuleSet(Base):
    """Warunki umowy agencyjnej z daną spółką. Widoczne tylko dla właściciela."""

    __tablename__ = "supplier_rule_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    valid_from: Mapped[date] = mapped_column(Date)
    broker_share_pct: Mapped[Decimal] = mapped_column(PCT)
    first_tranche_pct: Mapped[Decimal] = mapped_column(PCT)
    first_tranche_trigger: Mapped[str] = mapped_column(String(40), default="weryfikacja")
    max_markup_pln_mwh: Mapped[Optional[Decimal]] = mapped_column(MONEY, nullable=True)
    new_connection_months: Mapped[int] = mapped_column(Integer, default=12)
    clawback_mode: Mapped[str] = mapped_column(String(30), default="proporcjonalna")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    supplier: Mapped[Supplier] = relationship(back_populates="rule_sets")


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_name: Mapped[str] = mapped_column(String(300))
    client_nip: Mapped[str] = mapped_column(String(20), default="")
    medium: Mapped[str] = mapped_column(String(20), default="energia")
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    trader_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    signed_date: Mapped[date] = mapped_column(Date)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    term_months: Mapped[int] = mapped_column(Integer)
    annual_volume_mwh: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    base_price_pln_mwh: Mapped[Optional[Decimal]] = mapped_column(MONEY, nullable=True)
    markup_pln_mwh: Mapped[Decimal] = mapped_column(MONEY)
    new_connection: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(40), default="Umowa podpisana")

    # --- reguły zamrożone w dniu zapisu umowy ---
    rule_set_id: Mapped[int] = mapped_column(ForeignKey("supplier_rule_sets.id"))
    broker_share_pct: Mapped[Decimal] = mapped_column(PCT)
    first_tranche_pct: Mapped[Decimal] = mapped_column(PCT)
    new_connection_months: Mapped[int] = mapped_column(Integer, default=12)
    clawback_mode: Mapped[str] = mapped_column(String(30), default="proporcjonalna")
    trader_share_pct: Mapped[Decimal] = mapped_column(PCT)
    manager_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    manager_override_pct: Mapped[Decimal] = mapped_column(PCT, default=0)
    manager_override_base: Mapped[str] = mapped_column(String(30), default="narzut")

    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    supplier: Mapped[Supplier] = relationship()
    trader: Mapped[User] = relationship(foreign_keys=[trader_id])
    manager: Mapped[Optional[User]] = relationship(foreign_keys=[manager_id])
