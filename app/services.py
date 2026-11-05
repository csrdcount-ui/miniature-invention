"""Logika biznesowa: reguły, tworzenie umów, uprawnienia i widoki per rola.

Kluczowa zasada poufności: szablony dostają wyłącznie słowniki zbudowane
tu, na serwerze, przycięte do roli oglądającego. Handlowiec i menedżer
nigdy nie dostają do przeglądarki udziału brokera ani marży właściciela.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from . import engine as eng
from .models import (
    ROLE_MANAGER,
    ROLE_OWNER,
    ROLE_TRADER,
    Contract,
    Supplier,
    SupplierRuleSet,
    User,
    UserRate,
)


class BusinessError(ValueError):
    pass


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

def create_contract(
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
) -> Contract:
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
            f"Narzut {markup_pln_mwh} zł/MWh przekracza limit spółki "
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
    db.add(c)
    db.commit()
    db.refresh(c)
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
    if not trader.active:
        return False
    if actor.role == ROLE_OWNER:
        return True
    if actor.role == ROLE_MANAGER:
        return trader.id == actor.id or trader.manager_id == actor.id
    return trader.id == actor.id


def visible_contracts_query(user: User):
    q = select(Contract).order_by(Contract.signed_date.desc(), Contract.id.desc())
    if user.role == ROLE_OWNER:
        return q
    if user.role == ROLE_MANAGER:
        return q.where(or_(Contract.trader_id == user.id, Contract.manager_id == user.id))
    return q.where(Contract.trader_id == user.id)


def can_view_contract(user: User, c: Contract) -> bool:
    if user.role == ROLE_OWNER:
        return True
    if user.role == ROLE_MANAGER:
        return c.trader_id == user.id or c.manager_id == user.id
    return c.trader_id == user.id


def can_edit_status(user: User, c: Contract) -> bool:
    return can_view_contract(user, c)


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


def contract_view(viewer: User, c: Contract) -> dict:
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
            ("Marża właściciela", _payout(b.owner_margin)),
        ]
        view["warnings"] = list(b.warnings)
        return view

    # Menedżer i handlowiec: cała masa narzutu jest jawna (wynika z ceny
    # dla klienta), poufne są warunki właściciela u spółki.
    view["total_markup"] = b.total_markup
    if is_seller:
        view["trader_share_pct"] = c.trader_share_pct
        view["first_tranche_pct"] = c.first_tranche_pct
        view["rows"].append(("Twoja prowizja", _payout(b.trader)))
    elif is_contract_manager:
        view["trader_share_pct"] = c.trader_share_pct
        view["rows"].append((f"Prowizja handlowca: {c.trader.name}", _payout(b.trader)))
    if is_contract_manager:
        view["manager_override_pct"] = c.manager_override_pct
        view["manager_override_base"] = c.manager_override_base
        view["rows"].append(("Twój override", _payout(b.manager_override)))
    return view


def summary_for(viewer: User, contracts: list[Contract]) -> dict:
    """Sumy na pulpit — tylko kolumny dozwolone dla roli."""
    sums = {
        "count": len(contracts),
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
            sums["trader_total"] += b.trader.total
    if viewer.role != ROLE_OWNER:
        for k in ("broker_total", "owner_total", "trader_total"):
            sums.pop(k)
    return sums


def assignable_traders(db: Session, actor: User) -> list[User]:
    if actor.role == ROLE_OWNER:
        return list(db.scalars(select(User).where(User.active.is_(True)).order_by(User.name)))
    if actor.role == ROLE_MANAGER:
        return list(
            db.scalars(
                select(User)
                .where(User.active.is_(True), or_(User.id == actor.id, User.manager_id == actor.id))
                .order_by(User.name)
            )
        )
    return [actor]


__all__ = [
    "BusinessError",
    "ROLE_MANAGER",
    "ROLE_OWNER",
    "ROLE_TRADER",
]
