"""Model danych.

Zasada wersjonowania: reguły spółek i stawki osób mają datę obowiązywania.
Umowa w chwili zapisu kopiuje (zamraża) obowiązujące wtedy procenty, więc
zmiana warunków przez właściciela nie przelicza wstecz historii prowizji.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

ROLE_OWNER = "wlasciciel"
ROLE_MANAGER = "menedzer"
ROLE_TRADER = "handlowiec"
ROLE_BOK = "bok"
ROLES = {
    ROLE_OWNER: "Właściciel",
    ROLE_MANAGER: "Menedżer",
    ROLE_TRADER: "Handlowiec",
    ROLE_BOK: "Biuro obsługi (BOK)",
}
# Role, które sprzedają i mogą mieć przypisane umowy oraz stawki prowizji.
SELLING_ROLES = (ROLE_OWNER, ROLE_MANAGER, ROLE_TRADER)

# Uprawnienia biura obsługi włączane przez właściciela.
# klucz: (nazwa, opis, wartość domyślna, działa już w aplikacji)
BOK_PERMISSIONS = {
    "bok_can_change_status": (
        "Zmienia statusy umów",
        "BOK może przesuwać umowy w lejku i wpisywać daty zdarzeń, np. start dostaw.",
        True, True,
    ),
    "bok_sees_commissions": (
        "Widzi prowizje handlowców i override menedżerów",
        "Np. do przygotowania wypłat. Udziału brokera u spółki i marży właściciela BOK nie widzi nigdy.",
        False, True,
    ),
    "bok_can_reserve_nip": (
        "Rezerwuje NIP-y w spółkach obrotu",
        "Zacznie działać razem z modułem rezerwacji NIP.",
        True, False,
    ),
    "bok_can_reassign_clients": (
        "Przepina klientów między handlowcami",
        "Zacznie działać razem z modułem klientów.",
        False, False,
    ),
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
    # name = „Imię Nazwisko”, utrzymywane przez set_names(); imię i nazwisko osobno do sortowania
    name: Mapped[str] = mapped_column(String(200))
    first_name: Mapped[str] = mapped_column(String(100), default="")
    last_name: Mapped[str] = mapped_column(String(100), default="")
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20))
    manager_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # import: identyfikator ze starego systemu i paczka, z której rekord pochodzi
    ext_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    import_batch_id: Mapped[Optional[int]] = mapped_column(ForeignKey("import_batches.id"), nullable=True, index=True)

    manager: Mapped[Optional["User"]] = relationship(remote_side="User.id")
    rates: Mapped[list["UserRate"]] = relationship(
        back_populates="user", order_by="UserRate.valid_from.desc()", cascade="all, delete-orphan"
    )

    @property
    def role_label(self) -> str:
        return ROLES.get(self.role, self.role)

    @property
    def needs_last_name(self) -> bool:
        return not (self.last_name or "").strip()

    def set_names(self, first: str, last: str) -> None:
        self.first_name = first.strip()
        self.last_name = last.strip()
        self.name = f"{self.first_name} {self.last_name}".strip()


def split_full_name(full: str) -> tuple[str, str]:
    """Rozdziela „Imię Drugie Nazwisko”: ostatnie słowo to nazwisko. Jedno słowo = brak nazwiska."""
    parts = (full or "").split()
    if len(parts) < 2:
        return (parts[0] if parts else ""), ""
    return " ".join(parts[:-1]), parts[-1]


class Company(Base):
    """Dane firmy brokerskiej (jeden wiersz na instalację)."""

    __tablename__ = "company"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # uprawnienia BOK (opis w BOK_PERMISSIONS)
    bok_can_change_status: Mapped[bool] = mapped_column(Boolean, default=True)
    bok_sees_commissions: Mapped[bool] = mapped_column(Boolean, default=False)
    bok_can_reserve_nip: Mapped[bool] = mapped_column(Boolean, default=True)
    bok_can_reassign_clients: Mapped[bool] = mapped_column(Boolean, default=False)


class PermissionChange(Base):
    """Kto, kiedy i jak zmienił uprawnienie BOK."""

    __tablename__ = "permission_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    setting: Mapped[str] = mapped_column(String(60))
    old_value: Mapped[bool] = mapped_column(Boolean)
    new_value: Mapped[bool] = mapped_column(Boolean)
    changed_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    changed_by: Mapped[Optional[User]] = relationship()


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
    # import: identyfikator ze starego systemu i paczka, z której rekord pochodzi
    ext_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    import_batch_id: Mapped[Optional[int]] = mapped_column(ForeignKey("import_batches.id"), nullable=True, index=True)

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
    # import: identyfikator ze starego systemu i paczka, z której rekord pochodzi
    ext_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    import_batch_id: Mapped[Optional[int]] = mapped_column(ForeignKey("import_batches.id"), nullable=True, index=True)

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
    # import: identyfikator ze starego systemu i paczka, z której rekord pochodzi
    ext_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    import_batch_id: Mapped[Optional[int]] = mapped_column(ForeignKey("import_batches.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    supplier: Mapped[Supplier] = relationship()
    trader: Mapped[User] = relationship(foreign_keys=[trader_id])
    manager: Mapped[Optional[User]] = relationship(foreign_keys=[manager_id])
    events: Mapped[list["ContractStatusEvent"]] = relationship(
        back_populates="contract",
        order_by="ContractStatusEvent.id",
        cascade="all, delete-orphan",
    )


# Statusy, przy których trzeba podać powód (do raportów zerwań).
STATUSES_REQUIRING_NOTE = {"Zerwana"}


class ContractStatusEvent(Base):
    """Historia statusów umowy. Każda zmiana to nowy wiersz, nic nie jest nadpisywane.

    effective_date: kiedy zdarzenie faktycznie nastąpiło (np. start dostaw 1.11),
    changed_at: kiedy wpisano je do systemu.
    baseline: wiersz utworzony przy włączeniu historii dla umów zapisanych wcześniej;
    pokazuje stan na ten dzień, a nie faktyczną datę wejścia w status.
    """

    __tablename__ = "contract_status_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), index=True)
    from_status: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    to_status: Mapped[str] = mapped_column(String(40), index=True)
    effective_date: Mapped[date] = mapped_column(Date, index=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    changed_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    baseline: Mapped[bool] = mapped_column(Boolean, default=False)

    contract: Mapped[Contract] = relationship(back_populates="events")
    changed_by: Mapped[Optional[User]] = relationship()


class ImportBatch(Base):
    """Jedna paczka importu z pliku Excela. Cofnięcie paczki usuwa wszystkie jej rekordy.

    status: podglad (sprawdzona, czeka na zatwierdzenie), zatwierdzony, cofniety, odrzucony.
    is_demo: dane demonstracyjne (na ekranie baner „warunki fikcyjne”).
    """

    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(20), default="podglad")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    # use_alter: users wskazują paczkę, paczka wskazuje autora (cykl kluczy obcych)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", use_alter=True, name="fk_import_batches_created_by"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reverted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    # treść pliku trzymana tylko do zatwierdzenia, potem kasowana
    content: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
