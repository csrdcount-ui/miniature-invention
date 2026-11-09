"""Logika biznesowa: reguły, tworzenie umów, uprawnienia i widoki per rola.

Kluczowa zasada poufności: szablony dostają wyłącznie słowniki zbudowane
tu, na serwerze, przycięte do roli oglądającego. Handlowiec i menedżer
nigdy nie dostają do przeglądarki udziału brokera ani marży właściciela.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from . import engine as eng
from .models import (
    CONTRACT_STATUSES,
    DEFAULT_PRICING_PRODUCT,
    PRICING_PRODUCTS,
    STATUSES_REQUIRING_NOTE,
    BOK_PERMISSIONS,
    ROLE_BOK,
    ROLE_MANAGER,
    ROLE_OWNER,
    ROLE_TRADER,
    SELLING_ROLES,
    Company,
    SalesTarget,
    Contract,
    ContractStatusEvent,
    Supplier,
    SupplierRuleSet,
    User,
    UserRate,
)


class BusinessError(ValueError):
    pass


@dataclass(frozen=True)
class BokPerms:
    """Uprawnienia biura obsługi ustawione przez właściciela."""

    bok_can_change_status: bool = BOK_PERMISSIONS["bok_can_change_status"][2]
    bok_sees_commissions: bool = BOK_PERMISSIONS["bok_sees_commissions"][2]
    bok_can_reserve_nip: bool = BOK_PERMISSIONS["bok_can_reserve_nip"][2]
    bok_can_reassign_clients: bool = BOK_PERMISSIONS["bok_can_reassign_clients"][2]

    @classmethod
    def of(cls, company: Optional[Company]) -> "BokPerms":
        if company is None:
            return cls()
        return cls(**{k: bool(getattr(company, k)) for k in BOK_PERMISSIONS})


DEFAULT_PERMS = BokPerms()


# --------------------------------------------------------------------------
# Reguły obowiązujące w danym dniu
# --------------------------------------------------------------------------

def rule_set_on(db: Session, supplier_id: int, day: date) -> Optional[SupplierRuleSet]:
    return db.scalars(
        select(SupplierRuleSet)
        .where(SupplierRuleSet.supplier_id == supplier_id, SupplierRuleSet.valid_from <= day)
        .order_by(SupplierRuleSet.valid_from.desc(), SupplierRuleSet.id.desc())
        .limit(1)
    ).first()


def user_rate_on(db: Session, user_id: int, day: date) -> Optional[UserRate]:
    return db.scalars(
        select(UserRate)
        .where(UserRate.user_id == user_id, UserRate.valid_from <= day)
        .order_by(UserRate.valid_from.desc(), UserRate.id.desc())
        .limit(1)
    ).first()


def current_rule_set(supplier: Supplier, today: Optional[date] = None) -> Optional[SupplierRuleSet]:
    today = today or date.today()
    for rs in supplier.rule_sets:  # posortowane malejąco po valid_from
        if rs.valid_from <= today:
            return rs
    return None


def current_rate(user: User, today: Optional[date] = None) -> Optional[UserRate]:
    today = today or date.today()
    for r in user.rates:
        if r.valid_from <= today:
            return r
    return None


# --------------------------------------------------------------------------
# Umowy
# --------------------------------------------------------------------------

def _initial_event_date(status: str, signed_date: date) -> date:
    """Dla umów już podpisanych pierwszy wpis dostaje datę podpisania, dla leadów i ofert dzisiejszą."""
    today = date.today()
    signed_or_later = CONTRACT_STATUSES.index(status) >= CONTRACT_STATUSES.index("Umowa podpisana")
    return min(signed_date, today) if signed_or_later else today


def create_contract(db: Session, **kw) -> Contract:
    """Tworzy umowę i zatwierdza zapis."""
    c = build_contract(db, **kw)
    db.commit()
    db.refresh(c)
    return c


def build_contract(
    db: Session,
    *,
    actor: User,
    trader: User,
    supplier: Supplier,
    client_name: str,
    client_nip: str,
    medium: str,
    signed_date: date,
    start_date: Optional[date],
    term_months: int,
    annual_volume_mwh: Decimal,
    markup_pln_mwh: Decimal,
    base_price_pln_mwh: Optional[Decimal],
    new_connection: bool,
    status: str,
    pricing_product: str = DEFAULT_PRICING_PRODUCT,
    initial_note: str = "Umowa wpisana do systemu.",
) -> Contract:
    """Buduje umowę z regułami zamrożonymi na dzień podpisania. Bez zatwierdzania zapisu."""
    if not can_assign_trader(actor, trader):
        raise BusinessError("Nie możesz przypisać umowy do tej osoby.")
    rs = rule_set_on(db, supplier.id, signed_date)
    if rs is None:
        raise BusinessError(
            f"Spółka {supplier.name} nie ma reguł prowizji obowiązujących na dzień "
            f"{signed_date:%d.%m.%Y}. Właściciel musi je najpierw ustawić."
        )
    if rs.max_markup_pln_mwh is not None and markup_pln_mwh > rs.max_markup_pln_mwh:
        raise BusinessError(
            f"Marża {markup_pln_mwh} zł/MWh przekracza limit spółki obrotu "
            f"{supplier.name}: {rs.max_markup_pln_mwh} zł/MWh."
        )

    trader_rate = user_rate_on(db, trader.id, signed_date)
    trader_share = trader_rate.trader_share_pct if trader_rate else Decimal(0)

    manager_id = None
    override_pct = Decimal(0)
    override_base = eng.OVERRIDE_OD_NARZUTU
    # Override należy się przełożonemu sprzedającego (nie od własnej sprzedaży).
    if trader.manager_id:
        manager_id = trader.manager_id
        mrate = user_rate_on(db, trader.manager_id, signed_date)
        if mrate:
            override_pct = mrate.override_pct
            override_base = mrate.override_base

    c = Contract(
        client_name=client_name.strip(),
        client_nip=client_nip.strip(),
        medium=medium,
        supplier_id=supplier.id,
        trader_id=trader.id,
        signed_date=signed_date,
        start_date=start_date,
        term_months=term_months,
        annual_volume_mwh=annual_volume_mwh,
        base_price_pln_mwh=base_price_pln_mwh,
        markup_pln_mwh=markup_pln_mwh,
        pricing_product=pricing_product if pricing_product in PRICING_PRODUCTS else DEFAULT_PRICING_PRODUCT,
        new_connection=new_connection,
        status=status,
        rule_set_id=rs.id,
        broker_share_pct=rs.broker_share_pct,
        first_tranche_pct=rs.first_tranche_pct,
        new_connection_months=rs.new_connection_months,
        clawback_mode=rs.clawback_mode,
        trader_share_pct=trader_share,
        manager_id=manager_id,
        manager_override_pct=override_pct,
        manager_override_base=override_base,
        created_by_id=actor.id,
    )
    # Walidacja silnikiem zanim zapiszemy.
    calculate_contract(c)
    c.events.append(
        ContractStatusEvent(
            from_status=None, to_status=status,
            effective_date=_initial_event_date(status, signed_date), changed_by_id=actor.id,
            note=initial_note,
        )
    )
    db.add(c)
    db.flush()
    return c


def terms_of(c: Contract) -> eng.ContractTerms:
    return eng.ContractTerms(
        annual_volume_mwh=eng.D(c.annual_volume_mwh),
        term_months=int(c.term_months),
        markup_pln_mwh=eng.D(c.markup_pln_mwh),
        broker_share_pct=eng.D(c.broker_share_pct),
        first_tranche_pct=eng.D(c.first_tranche_pct),
        trader_share_pct=eng.D(c.trader_share_pct),
        manager_override_pct=eng.D(c.manager_override_pct),
        manager_override_base=c.manager_override_base,
        new_connection=bool(c.new_connection),
        new_connection_months=int(c.new_connection_months or 0),
    )


def calculate_contract(c: Contract) -> eng.Breakdown:
    return eng.calculate(terms_of(c))


# --------------------------------------------------------------------------
# Uprawnienia
# --------------------------------------------------------------------------

def team_ids(db: Session, manager: User) -> list[int]:
    return list(db.scalars(select(User.id).where(User.manager_id == manager.id)))


def can_assign_trader(actor: User, trader: User) -> bool:
    if not trader.active or trader.role not in SELLING_ROLES:
        return False
    if actor.role in (ROLE_OWNER, ROLE_BOK):
        return True
    if actor.role == ROLE_MANAGER:
        return trader.id == actor.id or trader.manager_id == actor.id
    return trader.id == actor.id


def visible_contracts_query(user: User):
    q = select(Contract).order_by(Contract.signed_date.desc(), Contract.id.desc())
    if user.role in (ROLE_OWNER, ROLE_BOK):
        return q
    if user.role == ROLE_MANAGER:
        return q.where(or_(Contract.trader_id == user.id, Contract.manager_id == user.id))
    return q.where(Contract.trader_id == user.id)


SORT_OPTIONS = {
    "podpisana_desc": (Contract.signed_date.desc(), Contract.id.desc()),
    "podpisana_asc": (Contract.signed_date.asc(), Contract.id.asc()),
    "wolumen_desc": (Contract.annual_volume_mwh.desc(), Contract.id.desc()),
    "wolumen_asc": (Contract.annual_volume_mwh.asc(), Contract.id.asc()),
    "narzut_desc": (Contract.markup_pln_mwh.desc(), Contract.id.desc()),
    "narzut_asc": (Contract.markup_pln_mwh.asc(), Contract.id.asc()),
    "klient_asc": (Contract.client_name.asc(),),
    "klient_desc": (Contract.client_name.desc(),),
}
SORT_LABELS = {
    "podpisana_desc": "Data podpisania: najnowsze najpierw",
    "podpisana_asc": "Data podpisania: najstarsze najpierw",
    "wolumen_desc": "Wolumen roczny: od największego",
    "wolumen_asc": "Wolumen roczny: od najmniejszego",
    "narzut_desc": "Marża: od największej",
    "narzut_asc": "Marża: od najmniejszej",
    "klient_asc": "Nazwa klienta: A–Z",
    "klient_desc": "Nazwa klienta: Z–A",
}
DEFAULT_SORT = "podpisana_desc"


@dataclass(frozen=True)
class ContractFilters:
    """Filtry listy umów. Pusta (domyślna) instancja nic nie zawęża."""

    products: tuple = ()
    supplier_id: Optional[int] = None
    medium: Optional[str] = None
    trader_id: Optional[int] = None
    status: Optional[str] = None
    signed_from: Optional[date] = None
    signed_to: Optional[date] = None
    volume_min: Optional[Decimal] = None
    volume_max: Optional[Decimal] = None
    markup_min: Optional[Decimal] = None
    markup_max: Optional[Decimal] = None
    new_connection: Optional[bool] = None
    sort: str = DEFAULT_SORT

    @property
    def active_count(self) -> int:
        """Ile filtrów zawęża listę (zakres liczy się jako jeden filtr)."""
        return sum(bool(x) for x in (
            self.products, self.supplier_id, self.medium, self.trader_id, self.status,
            self.signed_from or self.signed_to,
            self.volume_min is not None or self.volume_max is not None,
            self.markup_min is not None or self.markup_max is not None,
            self.new_connection is not None,
        ))

    @property
    def active(self) -> bool:
        """Czy choć jeden filtr zawęża listę (nie licząc samego sortowania)."""
        return bool(
            self.products or self.supplier_id or self.medium or self.trader_id or self.status
            or self.signed_from or self.signed_to or self.volume_min is not None or self.volume_max is not None
            or self.markup_min is not None or self.markup_max is not None or self.new_connection is not None
        )


def apply_contract_filters(q, f: ContractFilters):
    """Dokłada WHERE dla każdego ustawionego filtru i podmienia sortowanie."""
    if f.products:
        q = q.where(Contract.pricing_product.in_(f.products))
    if f.supplier_id:
        q = q.where(Contract.supplier_id == f.supplier_id)
    if f.medium:
        q = q.where(Contract.medium == f.medium)
    if f.trader_id:
        q = q.where(Contract.trader_id == f.trader_id)
    if f.status:
        q = q.where(Contract.status == f.status)
    if f.signed_from:
        q = q.where(Contract.signed_date >= f.signed_from)
    if f.signed_to:
        q = q.where(Contract.signed_date <= f.signed_to)
    if f.volume_min is not None:
        q = q.where(Contract.annual_volume_mwh >= f.volume_min)
    if f.volume_max is not None:
        q = q.where(Contract.annual_volume_mwh <= f.volume_max)
    if f.markup_min is not None:
        q = q.where(Contract.markup_pln_mwh >= f.markup_min)
    if f.markup_max is not None:
        q = q.where(Contract.markup_pln_mwh <= f.markup_max)
    if f.new_connection is not None:
        q = q.where(Contract.new_connection.is_(f.new_connection))
    return q.order_by(None).order_by(*SORT_OPTIONS.get(f.sort, SORT_OPTIONS[DEFAULT_SORT]))


def can_view_contract(user: User, c: Contract) -> bool:
    if user.role in (ROLE_OWNER, ROLE_BOK):
        return True
    if user.role == ROLE_MANAGER:
        return c.trader_id == user.id or c.manager_id == user.id
    return c.trader_id == user.id


def can_edit_status(user: User, c: Contract, perms: BokPerms = DEFAULT_PERMS) -> bool:
    if user.role == ROLE_BOK:
        return perms.bok_can_change_status
    return can_view_contract(user, c)


HISTORY_MAX_YEARS_BACK = 5


def change_status(db: Session, **kw) -> ContractStatusEvent:
    """Zmienia status umowy, zapisuje zdarzenie w historii i zatwierdza zapis."""
    ev = apply_status_change(db, **kw)
    db.commit()
    return ev


def apply_status_change(
    db: Session, *, actor: User, c: Contract, new_status: str, effective_date: date, note: str = "",
    perms: BokPerms = DEFAULT_PERMS,
) -> ContractStatusEvent:
    """Zmienia status umowy i dodaje zdarzenie do historii. Bez zatwierdzania zapisu."""
    if new_status not in CONTRACT_STATUSES:
        raise BusinessError("Niepoprawny status.")
    if not can_edit_status(actor, c, perms):
        raise BusinessError("Nie możesz zmienić statusu tej umowy.")
    if new_status == c.status:
        raise BusinessError(f"Umowa ma już status „{new_status}”. Wybierz inny status.")
    today = date.today()
    if effective_date > today:
        raise BusinessError("Data zdarzenia nie może być z przyszłości.")
    if effective_date.year < today.year - HISTORY_MAX_YEARS_BACK:
        raise BusinessError(f"Data zdarzenia może być najwyżej {HISTORY_MAX_YEARS_BACK} lat wstecz.")
    last_real = next((e for e in reversed(c.events) if not e.baseline), None)
    if last_real and effective_date < last_real.effective_date:
        raise BusinessError(
            f"Data zdarzenia nie może być wcześniejsza niż poprzednia zmiana statusu "
            f"({last_real.effective_date:%d.%m.%Y}: {last_real.to_status})."
        )
    note = (note or "").strip()[:2000]
    if new_status in STATUSES_REQUIRING_NOTE and not note:
        raise BusinessError(f"Przy statusie „{new_status}” podaj powód. Trafi do raportu zerwań.")
    ev = ContractStatusEvent(
        contract_id=c.id, from_status=c.status, to_status=new_status,
        effective_date=effective_date, changed_by_id=actor.id, note=note,
    )
    c.status = new_status
    db.add(ev)
    c.events.append(ev)
    db.flush()
    return ev


def status_since(c: Contract, today: Optional[date] = None) -> Optional[dict]:
    """Od kiedy umowa jest w obecnym statusie. None, gdy brak historii."""
    today = today or date.today()
    last = next((e for e in reversed(c.events) if e.to_status == c.status), None)
    if not last:
        return None
    return {"date": last.effective_date, "days": (today - last.effective_date).days, "baseline": last.baseline}


# --------------------------------------------------------------------------
# Widoki przycięte do roli
# --------------------------------------------------------------------------

def _payout(p: eng.Payout) -> dict:
    return {
        "total": p.total,
        "first_period_invoices": p.first_period_invoices,
        "tranche1": p.tranche1,
        "remaining_invoices": p.remaining_invoices,
    }


def tranche_b_visible(viewer: User, company: Optional[Company]) -> bool:
    """Polityka biura: handlowiec może nie widzieć prognozy transzy B (motywacja do bieżącej sprzedaży)."""
    if viewer.role != ROLE_TRADER:
        return True
    return True if company is None else bool(company.traders_see_tranche_b)


def contract_view(viewer: User, c: Contract, perms: BokPerms = DEFAULT_PERMS, show_tranche_b: bool = True) -> dict:
    """Słownik z danymi umowy, który wolno pokazać danej osobie."""
    b = calculate_contract(c)
    client_price = None
    if c.base_price_pln_mwh is not None:
        client_price = eng.D(c.base_price_pln_mwh) + eng.D(c.markup_pln_mwh)

    view: dict = {
        "id": c.id,
        "client_name": c.client_name,
        "client_nip": c.client_nip,
        "medium": c.medium,
        "pricing_product": c.pricing_product,
        "pricing_product_label": PRICING_PRODUCTS.get(c.pricing_product, c.pricing_product),
        "supplier_name": c.supplier.name,
        "trader_name": c.trader.name,
        "trader_id": c.trader_id,
        "signed_date": c.signed_date,
        "start_date": c.start_date,
        "term_months": c.term_months,
        "annual_volume_mwh": c.annual_volume_mwh,
        "total_volume_mwh": b.total_volume_mwh,
        "markup_pln_mwh": c.markup_pln_mwh,
        "base_price_pln_mwh": c.base_price_pln_mwh,
        "client_price_pln_mwh": client_price,
        "new_connection": c.new_connection,
        "new_connection_months": c.new_connection_months,
        "status": c.status,
        "rows": [],  # wiersze tabeli prowizji: (etykieta, payout)
        "warnings": [],
    }

    is_owner = viewer.role == ROLE_OWNER
    is_seller = c.trader_id == viewer.id
    is_contract_manager = c.manager_id == viewer.id

    if is_owner:
        view["total_markup"] = b.total_markup
        view["broker_share_pct"] = c.broker_share_pct
        view["first_tranche_pct"] = c.first_tranche_pct
        view["trader_share_pct"] = c.trader_share_pct
        view["manager_name"] = c.manager.name if c.manager else None
        view["manager_override_pct"] = c.manager_override_pct
        view["manager_override_base"] = c.manager_override_base
        view["clawback_mode"] = c.clawback_mode
        view["rows"] = [
            ("Spółka obrotu → broker", _payout(b.broker)),
            (f"Handlowiec: {c.trader.name}", _payout(b.trader)),
            (
                f"Override menedżera: {c.manager.name}" if c.manager else "Override menedżera",
                _payout(b.manager_override),
            ),
            ("Przychód spółki", _payout(b.owner_margin)),
        ]
        view["warnings"] = list(b.warnings)
        return view

    if viewer.role == ROLE_BOK:
        # BOK nigdy nie widzi warunków właściciela u spółki ani jego marży.
        view["total_markup"] = b.total_markup
        view["manager_name"] = c.manager.name if c.manager else None
        if perms.bok_sees_commissions:
            view["trader_share_pct"] = c.trader_share_pct
            view["first_tranche_pct"] = c.first_tranche_pct
            view["rows"].append((f"Prowizja handlowca: {c.trader.name}", _payout(b.trader)))
            if c.manager:
                view["manager_override_pct"] = c.manager_override_pct
                view["manager_override_base"] = c.manager_override_base
                view["rows"].append((f"Override menedżera: {c.manager.name}", _payout(b.manager_override)))
        return view

    # Menedżer i handlowiec: cała masa narzutu jest jawna (wynika z ceny
    # dla klienta), poufne są warunki właściciela u spółki.
    view["total_markup"] = b.total_markup
    if is_seller:
        view["trader_share_pct"] = c.trader_share_pct
        view["first_tranche_pct"] = c.first_tranche_pct
        view["tranche_a"] = b.trader.tranche1
        if show_tranche_b:
            view["rows"].append(("Twoja prowizja", _payout(b.trader)))
        else:
            # bez prognozy transzy B: nie wysyłamy jej nawet do szablonu
            view["hide_b"] = True
    elif is_contract_manager:
        view["trader_share_pct"] = c.trader_share_pct
        view["rows"].append((f"Prowizja handlowca: {c.trader.name}", _payout(b.trader)))
    if is_contract_manager:
        view["manager_override_pct"] = c.manager_override_pct
        view["manager_override_base"] = c.manager_override_base
        view["rows"].append(("Twój override", _payout(b.manager_override)))
    return view


def summary_for(viewer: User, contracts: list[Contract], perms: BokPerms = DEFAULT_PERMS) -> dict:
    """Sumy na pulpit — tylko kolumny dozwolone dla roli.

    Lead, Kontakt i Oferta to jeszcze nie sprzedaż: nie wchodzą do portfela ani do prognoz.
    Liczy je osobno pole „offers”.
    """
    offers = sum(1 for c in contracts if c.status in PIPELINE_STATUSES)
    contracts = [c for c in contracts if c.status not in PIPELINE_STATUSES]
    sums = {
        "count": len(contracts),
        "offers": offers,
        "total_volume_mwh": Decimal(0),
        "total_markup": Decimal(0),
        "mine_total": Decimal(0),
        "mine_tranche1": Decimal(0),
        "override_total": Decimal(0),
        "broker_total": Decimal(0),
        "owner_total": Decimal(0),
        "trader_total": Decimal(0),
    }
    for c in contracts:
        b = calculate_contract(c)
        sums["total_volume_mwh"] += b.total_volume_mwh
        sums["total_markup"] += b.total_markup
        if c.trader_id == viewer.id:
            sums["mine_total"] += b.trader.total
            sums["mine_tranche1"] += b.trader.tranche1
        if c.manager_id == viewer.id:
            sums["override_total"] += b.manager_override.total
        if viewer.role == ROLE_OWNER:
            sums["broker_total"] += b.broker.total
            sums["owner_total"] += b.owner_margin.total
        if viewer.role == ROLE_OWNER or (viewer.role == ROLE_BOK and perms.bok_sees_commissions):
            sums["trader_total"] += b.trader.total
            sums["override_all_total"] = sums.get("override_all_total", Decimal(0)) + b.manager_override.total
    if viewer.role != ROLE_OWNER:
        for k in ("broker_total", "owner_total"):
            sums.pop(k)
    if not (viewer.role == ROLE_OWNER or (viewer.role == ROLE_BOK and perms.bok_sees_commissions)):
        sums.pop("trader_total")
    return sums


def assignable_traders(db: Session, actor: User) -> list[User]:
    if actor.role in (ROLE_OWNER, ROLE_BOK):
        return list(
            db.scalars(
                select(User)
                .where(User.active.is_(True), User.role.in_(SELLING_ROLES))
                .order_by(User.last_name, User.first_name)
            )
        )
    if actor.role == ROLE_MANAGER:
        return list(
            db.scalars(
                select(User)
                .where(User.active.is_(True), or_(User.id == actor.id, User.manager_id == actor.id))
                .order_by(User.last_name, User.first_name)
            )
        )
    return [actor]


__all__ = [
    "BusinessError",
    "ROLE_MANAGER",
    "ROLE_OWNER",
    "ROLE_TRADER",
]


# --------------------------------------------------------------------------
# Sprzedaż w miesiącu i targety
# --------------------------------------------------------------------------

MONTHS_PL = ["styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec", "lipiec",
             "sierpień", "wrzesień", "październik", "listopad", "grudzień"]
# statusy przed podpisaniem i zerwane nie liczą się do sprzedaży miesiąca
NOT_SALE_STATUSES = {"Lead", "Kontakt", "Oferta", "Zerwana"}


def month_start(d: Optional[date] = None) -> date:
    d = d or date.today()
    return date(d.year, d.month, 1)


def month_label(m: date) -> str:
    return f"{MONTHS_PL[m.month - 1]} {m.year}"


def _next_month(m: date) -> date:
    return date(m.year + (m.month == 12), m.month % 12 + 1, 1)


def target_of(db: Session, user_id: int, month: date) -> Optional[Decimal]:
    t = db.scalar(select(SalesTarget).where(SalesTarget.user_id == user_id, SalesTarget.month == month))
    return t.amount if t else None


def set_target(db: Session, *, actor: User, person: User, month: date, amount: Decimal) -> None:
    if not can_set_target(actor, person):
        raise BusinessError("Nie możesz ustawić targetu tej osobie.")
    if amount < 0:
        raise BusinessError("Target nie może być ujemny.")
    t = db.scalar(select(SalesTarget).where(SalesTarget.user_id == person.id, SalesTarget.month == month))
    if t:
        t.amount, t.set_by_id = amount, actor.id
    else:
        db.add(SalesTarget(user_id=person.id, month=month, amount=amount, set_by_id=actor.id))
    db.commit()


def can_set_target(actor: User, person: User) -> bool:
    if person.role not in SELLING_ROLES:
        return False
    if actor.role == ROLE_OWNER:
        return True
    return actor.role == ROLE_MANAGER and person.manager_id == actor.id


def month_sales(db: Session, user_ids: list[int], month: date) -> dict:
    """Sprzedaż w miesiącu (umowy podpisane w tym miesiącu, bez zerwanych)."""
    out = {"count": 0, "markup": Decimal(0), "tranche_a": Decimal(0), "target": None, "pct": None}
    if not user_ids:
        return out
    q = select(Contract).where(
        Contract.trader_id.in_(user_ids),
        Contract.signed_date >= month,
        Contract.signed_date < _next_month(month),
        Contract.status.not_in(NOT_SALE_STATUSES),
    )
    for c in db.scalars(q):
        b = calculate_contract(c)
        out["count"] += 1
        out["markup"] += b.total_markup
        out["tranche_a"] += b.trader.tranche1
    targets = [target_of(db, uid, month) for uid in user_ids]
    targets = [t for t in targets if t is not None]
    if targets:
        out["target"] = sum(targets, Decimal(0))
        if out["target"] > 0:
            out["pct"] = int((out["markup"] / out["target"] * 100).quantize(Decimal(1)))
    return out


# --------------------------------------------------------------------------
# Oferty złożone i statystyki sprzedaży po miesiącach
# --------------------------------------------------------------------------

PIPELINE_STATUSES = ("Lead", "Kontakt", "Oferta")
OFFER_STALE_DAYS = 14  # oferta bez decyzji dłużej niż tyle dni jest wyróżniona na pulpicie
OFFER_STATUS = "Oferta"


def offers_overview(viewer: User, contracts: list[Contract], show_tranche_b: bool = True) -> dict:
    """Oferty złożone (status „Oferta”) pogrupowane po handlowcach, z prognozą, gdyby wszystkie się zamknęły.

    Prognoza tylko w kolumnach dozwolonych dla roli: właściciel widzi przychód spółki, menedżer swój
    override, handlowiec swoją prowizję (transzę A, gdy biuro ukrywa transzę B). Masa marży — wszyscy.
    """
    today = date.today()
    out = {"count": 0, "markup": Decimal(0), "owner": Decimal(0), "override": Decimal(0), "mine": Decimal(0), "groups": []}
    groups: dict[int, dict] = {}
    for c in contracts:
        if c.status != OFFER_STATUS:
            continue
        b = calculate_contract(c)
        out["count"] += 1
        out["markup"] += b.total_markup
        if viewer.role == ROLE_OWNER:
            out["owner"] += b.owner_margin.total
        if c.manager_id == viewer.id:
            out["override"] += b.manager_override.total
        if c.trader_id == viewer.id:
            out["mine"] += b.trader.total if show_tranche_b else b.trader.tranche1
        g = groups.setdefault(c.trader_id, {"trader_name": c.trader.name, "count": 0, "markup": Decimal(0), "lista": []})
        g["count"] += 1
        g["markup"] += b.total_markup
        g["stale"] = g.get("stale", 0) + ((today - c.signed_date).days > OFFER_STALE_DAYS)
        g["lista"].append({
            "id": c.id, "client_name": c.client_name, "supplier_name": c.supplier.name, "medium": c.medium,
            "pricing_product": c.pricing_product, "annual_volume_mwh": c.annual_volume_mwh,
            "markup_pln_mwh": c.markup_pln_mwh, "term_months": c.term_months, "markup": b.total_markup,
            "date": c.signed_date, "days": (today - c.signed_date).days,
        })
    for g in groups.values():
        g["lista"].sort(key=lambda i: i["date"])
    out["groups"] = sorted(groups.values(), key=lambda g: (-g["markup"], g["trader_name"]))
    out["show_mine_only"] = viewer.role == ROLE_TRADER
    out["mine_label"] = "Twoja prowizja" if show_tranche_b else "Twoja transza A"
    return out


def parse_month(raw: str) -> Optional[date]:
    """„2026-11” → 1.11.2026; śmieci → None (bez wyjątków, bo to parametr adresu)."""
    try:
        y, m = raw.split("-")
        return date(int(y), int(m), 1)
    except (ValueError, AttributeError):
        return None


def add_months(m: date, n: int) -> date:
    y, mm = divmod(m.month - 1 + n, 12)
    return date(m.year + y, mm + 1, 1)


STATS_MAX_MONTHS = 36


def month_range(raw_from: str, raw_to: str, default_months: int = 6) -> tuple[date, date]:
    """Zakres miesięcy statystyk: domyślnie ostatnie pół roku, najwyżej 36 miesięcy, od ≤ do."""
    end = parse_month(raw_to) or month_start()
    start = parse_month(raw_from) or add_months(end, -(default_months - 1))
    if start > end:
        start, end = end, start
    if add_months(start, STATS_MAX_MONTHS - 1) < end:
        start = add_months(end, -(STATS_MAX_MONTHS - 1))
    return start, end


def monthly_stats(contracts: list[Contract], start: date, end: date) -> dict:
    """Sprzedaż w każdym miesiącu zakresu: umowy podpisane i masa marży (bez ofert i zerwanych)."""
    months = []
    m = start
    while m <= end:
        months.append({"month": m, "label": month_label(m), "count": 0, "markup": Decimal(0)})
        m = _next_month(m)
    index = {row["month"]: row for row in months}
    for c in contracts:
        if c.status in NOT_SALE_STATUSES:
            continue
        row = index.get(month_start(c.signed_date))
        if row:
            row["count"] += 1
            row["markup"] += calculate_contract(c).total_markup
    best = max((r["markup"] for r in months), default=Decimal(0))
    for r in months:
        r["share"] = int(r["markup"] / best * 100) if best > 0 else 0
    return {
        "active": sum(1 for r in months if r["count"]),  # w ilu miesiącach była choć jedna umowa
        "n": len(months),
        "months": months[::-1],  # najnowszy miesiąc na górze
        "count": sum(r["count"] for r in months),
        "markup": sum((r["markup"] for r in months), Decimal(0)),
        "from": start, "to": end,
    }


def person_stats(db: Session, person: User, start: date, end: date) -> dict:
    """Statystyki jednej osoby po miesiącach, z targetem i wykonaniem w każdym miesiącu."""
    contracts = list(db.scalars(select(Contract).where(Contract.trader_id == person.id)))
    stats = monthly_stats(contracts, start, end)
    for r in stats["months"]:
        r["target"] = target_of(db, person.id, r["month"])
        r["pct"] = int((r["markup"] / r["target"] * 100).quantize(Decimal(1))) if r["target"] else None
    return stats


def team_ranking(rows: list) -> list:
    """Ranking miesiąca: osoby z targetem według wykonania, potem bez targetu według masy marży."""
    sellers = [(p, m) for p, _, m in rows if m is not None and p.active]
    return sorted(sellers, key=lambda pm: (pm[1]["pct"] is None, -(pm[1]["pct"] or 0), -pm[1]["markup"]))


def plural_umowy(n: int) -> str:
    if n == 1:
        return "1 umowa"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} umowy"
    return f"{n} umów"


def plural_oferty(n: int) -> str:
    if n == 1:
        return "1 oferta"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} oferty"
    return f"{n} ofert"
