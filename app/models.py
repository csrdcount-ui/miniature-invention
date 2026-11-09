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

# Produkt cenowy umowy. Kolor to tylko dodatek do etykiety tekstowej — nigdy
# jedyny nośnik informacji (dostępność).
PRICING_PRODUCTS = {
    "spot": "SPOT (RDN)",
    "fix": "FIX",
    "tranza": "Transza",
}
DEFAULT_PRICING_PRODUCT = "fix"  # silnik liczy stały narzut zł/MWh — strukturalnie odpowiada FIX

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
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # podbite przy „Wyloguj wszystkie inne urządzenia”; stare sesje (z inną wartością
    # zapisaną w cookie) przestają działać
    session_version: Mapped[int] = mapped_column(Integer, default=0)
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
    # polityka biura: czy handlowcy widzą prognozę transzy B (domyślnie tak, z zastrzeżeniem)
    traders_see_tranche_b: Mapped[bool] = mapped_column(Boolean, default=True)


# Ustawienia polityki biura (nie uprawnienia BOK), zapisywane w tej samej historii zmian.
POLICY_SETTINGS = {
    "traders_see_tranche_b": (
        "Handlowcy widzą prognozę transzy B",
        "Prognoza zawsze z zastrzeżeniem: korekty, zerwania, upadłość klienta, niższe zużycie. "
        "Wyłącz, jeśli handlowcy mają widzieć tylko transzę A i bieżącą sprzedaż.",
        True,
    ),
}


class SalesTarget(Base):
    """Miesięczny target masy marży dla osoby sprzedającej."""

    __tablename__ = "sales_targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    month: Mapped[date] = mapped_column(Date, index=True)  # zawsze 1. dzień miesiąca
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    set_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    set_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    set_by: Mapped[Optional["User"]] = relationship(foreign_keys=[set_by_id])


class SystemFlag(Base):
    """Znaczniki jednorazowych operacji technicznych (np. czysty start), żeby nie powtarzały się."""

    __tablename__ = "system_flags"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
    pricing_product: Mapped[str] = mapped_column(String(10), default=DEFAULT_PRICING_PRODUCT)
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


# --------------------------------------------------------------------------
# Lejek sprzedaży: klient, sprawdzenie NIP w BOK, oferta, oś zdarzeń
# --------------------------------------------------------------------------

# Etapy lejka (ustalone z właścicielką 10.11.2026). Sprawdzenie NIP w BOK jest
# osobnym procesem obok etapów: ofertę można złożyć tylko w spółce z wolnym NIP-em.
STAGES = {
    "lead": "Zimny lead",
    "kontakt": "Kontakt i osoba decyzyjna",
    "dane": "Zbieranie danych od klienta",
    "oferta": "Oferta złożona",
    "wygrana": "Umowa podpisana",
    "przegrana": "Przegrana",
}
OPEN_STAGES = ("lead", "kontakt", "dane", "oferta")
WORK_STAGES = ("kontakt", "dane", "oferta")  # „wątki, na których handlowiec pracuje”
LOST_REASONS = [
    "Cena",
    "Klient zostaje u obecnego sprzedawcy",
    "Wybrał innego brokera",
    "NIP zajęty we wszystkich spółkach",
    "Negatywny scoring",
    "Brak decyzji klienta",
    "Inny powód",
]
LEAD_SOURCES = ["Polecenie", "Zimny telefon", "Baza firm", "Kampania", "Strona internetowa", "Klient powracający", "Inne"]

# Wynik sprawdzenia NIP-u przez BOK w danej spółce.
NIP_CHECK_RESULTS = {
    "do_sprawdzenia": "Czeka na BOK",
    "zarezerwowany": "Wolny, zarezerwowany dla nas",
    "zajety": "Zajęty (inny agent albo sprzedaż spółki)",
    "scoring": "Negatywny scoring, nie ofertować",
}
OFFER_STATUSES = {"otwarta": "Czeka na decyzję klienta", "przyjeta": "Przyjęta", "odrzucona": "Odrzucona"}
OFFER_VALID_DAYS = 7  # oferta ważna zwykle do tygodnia (ceny giełdowe)
OFFER_FOLLOWUP_DAYS = 3  # po 3 dniach bez odpowiedzi: telefon do klienta
EVENT_KINDS = {
    "telefon": "Telefon",
    "spotkanie": "Spotkanie",
    "email": "E-mail",
    "notatka": "Notatka",
    "etap": "Zmiana etapu",
    "bok": "BOK",
    "oferta": "Oferta",
    "system": "System",
}
CONTACT_KINDS = ("telefon", "spotkanie", "email")


class Client(Base):
    """Karta klienta. Jeden NIP = jedna karta w biurze, jeden opiekun."""

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    nip: Mapped[Optional[str]] = mapped_column(String(10), unique=True, nullable=True)
    contact_person: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    source: Mapped[str] = mapped_column(String(50), default="")
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    stage: Mapped[str] = mapped_column(String(20), default="lead", index=True)
    stage_since: Mapped[date] = mapped_column(Date, default=date.today)
    next_step: Mapped[str] = mapped_column(String(300), default="")
    next_step_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    lost_reason: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ext_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    import_batch_id: Mapped[Optional[int]] = mapped_column(ForeignKey("import_batches.id"), nullable=True)

    owner: Mapped[User] = relationship(foreign_keys=[owner_id])
    checks: Mapped[list["NipCheck"]] = relationship(
        back_populates="client", cascade="all, delete-orphan", order_by="NipCheck.id"
    )
    offers: Mapped[list["ClientOffer"]] = relationship(
        back_populates="client", cascade="all, delete-orphan", order_by="ClientOffer.id.desc()"
    )
    events: Mapped[list["ClientEvent"]] = relationship(
        back_populates="client", cascade="all, delete-orphan", order_by="ClientEvent.id.desc()"
    )


class NipCheck(Base):
    """Zlecenie dla BOK: sprawdź NIP klienta w tej spółce (rezerwacja i scoring)."""

    __tablename__ = "nip_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    result: Mapped[str] = mapped_column(String(20), default="do_sprawdzenia", index=True)
    reserved_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    note: Mapped[str] = mapped_column(String(500), default="")
    requested_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    checked_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    client: Mapped[Client] = relationship(back_populates="checks")
    supplier: Mapped["Supplier"] = relationship()
    requested_by: Mapped[Optional[User]] = relationship(foreign_keys=[requested_by_id])
    checked_by: Mapped[Optional[User]] = relationship(foreign_keys=[checked_by_id])


class ClientOffer(Base):
    """Oferta złożona klientowi w jednej spółce. Ważna zwykle tydzień."""

    __tablename__ = "client_offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    pricing_product: Mapped[str] = mapped_column(String(10), default="fix")
    medium: Mapped[str] = mapped_column(String(10), default="energia")
    base_price_pln_mwh: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    markup_pln_mwh: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    annual_volume_mwh: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    term_months: Mapped[int] = mapped_column(Integer)
    sent_date: Mapped[date] = mapped_column(Date)
    valid_until: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="otwarta")
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    client: Mapped[Client] = relationship(back_populates="offers")
    supplier: Mapped["Supplier"] = relationship()


class ClientEvent(Base):
    """Oś zdarzeń na karcie klienta: kto, co, kiedy (handlowiec i BOK w jednym miejscu)."""

    __tablename__ = "client_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="notatka")
    text: Mapped[str] = mapped_column(Text, default="")
    day: Mapped[date] = mapped_column(Date, default=date.today)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    client: Mapped[Client] = relationship(back_populates="events")
    user: Mapped[Optional[User]] = relationship()


# Listy wymagań na dwóch etapach (edytuje właściciel). Wersja startowa z docs/WIEDZA-BRANZOWA.md.
CHECKLIST_KEYS = {
    "oferta": "Co jest potrzebne do złożenia oferty",
    "umowa": "Co jest potrzebne do przygotowania umowy",
}
CHECKLIST_DEFAULTS = {
    "oferta": "\n".join([
        "NIP wolny i zarezerwowany przez BOK w spółce, w której składasz ofertę",
        "Scoring klienta w tej spółce bez zastrzeżeń",
        "Roczne zużycie energii lub gazu",
        "Grupa taryfowa (B, C albo G dla wspólnot)",
        "Data końca obecnej umowy i okres wypowiedzenia",
        "Powyżej progu spółki (1, 2 lub 4 GWh): profil zużycia do wyceny indywidualnej",
    ]),
    "umowa": "\n".join([
        "Faktury dystrybucyjne (zawsze)",
        "Dokumenty wymagane przez wybraną spółkę",
        "Numery punktów poboru",
        "Sposób podpisu: Autenti, kod SMS albo papier (przy papierze: skan do spółki, oryginał pocztą)",
    ]),
}


class Checklist(Base):
    __tablename__ = "checklists"

    key: Mapped[str] = mapped_column(String(20), primary_key=True)
    body: Mapped[str] = mapped_column(Text, default="")
    updated_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
