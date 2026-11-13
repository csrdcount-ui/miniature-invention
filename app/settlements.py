"""Rejestr rozliczeń: wpływy od spółek obrotu, wypłaty dla zespołu, korekty.

Zasada proporcji: wpływ od spółki to pewna część udziału brokera z umowy.
Handlowiec i menedżer dostają tę samą część swoich kwot (dziedziczą
harmonogram spółki), a reszta to marża właściciela. Tak samo działa korekta,
tylko z minusem.

Zagrożone korektą: to, co już rozliczono ponad część umowy zrealizowaną do
dziś (miesiące od startu dostaw / okres umowy). Przed startem dostaw całe
rozliczone kwoty są zaliczką.

Poufność: widoki budowane tu są przycięte do roli, tak jak w services.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from . import engine as eng
from .models import (
    CONTRACT_STATUSES,
    ENTRY_KINDS,
    ROLE_MANAGER,
    ROLE_OWNER,
    Contract,
    PayoutEntry,
    User,
)
from .services import BusinessError, calculate_contract

ZERO = Decimal(0)
KOREKTA = "korekta"


# --------------------------------------------------------------------------
# Czas i zrealizowana część umowy
# --------------------------------------------------------------------------

def months_elapsed(start: Optional[date], today: date, term_months: int) -> int:
    """Pełne miesiące dostaw od startu do dziś, w granicach okresu umowy."""
    if not start or today < start:
        return 0
    months = (today.year - start.year) * 12 + (today.month - start.month)
    if today.day < start.day:
        months -= 1
    return max(0, min(months, term_months))


def earned_ratio(c: Contract, today: date) -> Decimal:
    return Decimal(months_elapsed(c.start_date, today, c.term_months)) / Decimal(c.term_months)


# --------------------------------------------------------------------------
# Zapis wpływu i korekty
# --------------------------------------------------------------------------

def split_broker_amount(c: Contract, broker_amount: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    """Dzieli kwotę od spółki na handlowca, menedżera i właściciela."""
    b = calculate_contract(c)
    if b.broker.total == 0:
        raise BusinessError("Ta umowa nie generuje prowizji brokera, nie ma czego rozliczać.")
    part = broker_amount / b.broker.total
    trader = eng.zl(b.trader.total * part)
    override = eng.zl(b.manager_override.total * part)
    owner = eng.zl(broker_amount) - trader - override
    return trader, override, owner


def net_received(c: Contract) -> Decimal:
    return sum((eng.D(e.broker_amount) for e in c.entries), ZERO)


def record_entry(
    db,
    *,
    actor: User,
    contract: Contract,
    kind: str,
    booked_on: date,
    amount: Decimal,
    note: str = "",
    mark_broken: bool = False,
) -> PayoutEntry:
    """Zapisuje wpływ (kwota dodatnia) albo korektę (podawana dodatnio, zapisywana z minusem)."""
    if actor.role != ROLE_OWNER:
        raise BusinessError("Rozliczenia ze spółkami wpisuje tylko właściciel.")
    if kind not in ENTRY_KINDS:
        raise BusinessError("Wybierz rodzaj wpisu.")
    if amount is None or amount <= 0:
        raise BusinessError("Kwota musi być większa od zera.")
    amount = eng.zl(amount)
    if kind == KOREKTA:
        received = net_received(contract)
        if amount > received:
            raise BusinessError(
                f"Korekta {amount} zł jest większa niż suma dotychczasowych wpływów "
                f"z tej umowy ({received} zł). Sprawdź zestawienie od spółki."
            )
        amount = -amount

    trader, override, owner = split_broker_amount(contract, amount)
    entry = PayoutEntry(
        contract_id=contract.id,
        kind=kind,
        booked_on=booked_on,
        broker_amount=amount,
        trader_amount=trader,
        override_amount=override,
        owner_amount=owner,
        note=(note or "")[:2000],
        created_by_id=actor.id,
    )
    db.add(entry)

    # Status w lejku idzie za pieniędzmi, ale nigdy się nie cofa.
    idx = CONTRACT_STATUSES.index
    if kind == KOREKTA and mark_broken:
        contract.status = "Zerwana"
    elif kind == "transza1" and contract.status in CONTRACT_STATUSES and idx(contract.status) < idx("Transza 1 wypłacona"):
        contract.status = "Transza 1 wypłacona"
    elif kind == "faktury" and contract.status in CONTRACT_STATUSES and idx(contract.status) < idx("Rozliczenia bieżące"):
        contract.status = "Rozliczenia bieżące"

    db.commit()
    db.refresh(entry)
    db.refresh(contract)
    return entry


def mark_paid(db, *, actor: User, entry: PayoutEntry, who: str, paid_on: date) -> None:
    if actor.role != ROLE_OWNER:
        raise BusinessError("Wypłaty dla zespołu oznacza tylko właściciel.")
    if who == "handlowiec":
        entry.trader_paid_on = paid_on
    elif who == "menedzer":
        if entry.contract.manager_id is None or entry.override_amount == 0:
            raise BusinessError("Ten wpis nie ma części menedżera.")
        entry.manager_paid_on = paid_on
    else:
        raise BusinessError("Nieznany odbiorca wypłaty.")
    db.commit()


def delete_entry(db, *, actor: User, entry: PayoutEntry) -> None:
    if actor.role != ROLE_OWNER:
        raise BusinessError("Wpisy usuwa tylko właściciel.")
    if entry.trader_paid_on or entry.manager_paid_on:
        raise BusinessError(
            "Nie można usunąć wpisu, który został już rozliczony z zespołem. "
            "Jeśli wpis jest błędny, dodaj korektę."
        )
    db.delete(entry)
    db.commit()


# --------------------------------------------------------------------------
# Stan rozliczeń umowy
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PartyState:
    forecast: Decimal      # prognoza z pełnego okresu umowy
    settled: Decimal       # rozliczone z wpływów od spółki (po korektach)
    remaining: Decimal     # prognoza minus rozliczone
    at_risk: Decimal       # rozliczone ponad część zrealizowaną do dziś
    paid: Optional[Decimal] = None     # faktycznie wypłacone osobie (tylko zespół)
    to_pay: Optional[Decimal] = None   # rozliczone, ale jeszcze niewypłacone


def _at_risk(c: Contract, forecast: Decimal, settled: Decimal, ratio: Decimal) -> Decimal:
    if c.clawback_mode == eng.KOREKTA_BRAK:
        return ZERO
    return max(ZERO, eng.zl(settled - forecast * ratio))


def contract_state(c: Contract, today: date) -> dict[str, PartyState]:
    b = calculate_contract(c)
    ratio = earned_ratio(c, today)
    sums = {"broker": ZERO, "trader": ZERO, "override": ZERO, "owner": ZERO}
    paid_t = paid_m = ZERO
    for e in c.entries:
        sums["broker"] += eng.D(e.broker_amount)
        sums["trader"] += eng.D(e.trader_amount)
        sums["override"] += eng.D(e.override_amount)
        sums["owner"] += eng.D(e.owner_amount)
        if e.trader_paid_on:
            paid_t += eng.D(e.trader_amount)
        if e.manager_paid_on:
            paid_m += eng.D(e.override_amount)
    forecasts = {
        "broker": b.broker.total,
        "trader": b.trader.total,
        "override": b.manager_override.total,
        "owner": b.owner_margin.total,
    }
    out = {}
    for k, f in forecasts.items():
        s = sums[k]
        extra = {}
        if k == "trader":
            extra = {"paid": paid_t, "to_pay": s - paid_t}
        elif k == "override":
            extra = {"paid": paid_m, "to_pay": s - paid_m}
        out[k] = PartyState(f, s, f - s, _at_risk(c, f, s, ratio), **extra)
    return out


def suggested_clawback(c: Contract, today: date) -> Optional[eng.Clawback]:
    """Korekta, jaką spółka powinna naliczyć przy zerwaniu umowy dzisiaj."""
    if not c.entries:
        return None
    st = contract_state(c, today)
    return eng.clawback(
        calculate_contract(c),
        paid_broker=st["broker"].settled,
        paid_trader=st["trader"].settled,
        paid_override=st["override"].settled,
        earned_ratio=earned_ratio(c, today),
        mode=c.clawback_mode,
    )


# --------------------------------------------------------------------------
# Widoki przycięte do roli
# --------------------------------------------------------------------------

def _parties_for(viewer: User, c: Contract) -> list[tuple[str, str]]:
    """(klucz, etykieta) stron, które dana osoba może zobaczyć w tej umowie."""
    if viewer.role == ROLE_OWNER:
        rows = [("broker", "Spółka obrotu → broker"), ("trader", f"Handlowiec: {c.trader.name}")]
        if c.manager_id:
            rows.append(("override", f"Override menedżera: {c.manager.name}"))
        rows.append(("owner", "Marża właściciela"))
        return rows
    rows = []
    if c.trader_id == viewer.id:
        rows.append(("trader", "Twoja prowizja"))
    elif c.manager_id == viewer.id:
        rows.append(("trader", f"Prowizja handlowca: {c.trader.name}"))
    if c.manager_id == viewer.id:
        rows.append(("override", "Twój override"))
    return rows


def contract_settlement_view(viewer: User, c: Contract, today: date) -> dict:
    state = contract_state(c, today)
    parties = _parties_for(viewer, c)
    keys = {k for k, _ in parties}
    months = months_elapsed(c.start_date, today, c.term_months)

    entries = []
    for e in c.entries:
        row = {"id": e.id, "booked_on": e.booked_on, "kind": e.kind, "kind_label": e.kind_label, "amounts": []}
        for k, label in parties:
            amt = {"broker": e.broker_amount, "trader": e.trader_amount,
                   "override": e.override_amount, "owner": e.owner_amount}[k]
            row["amounts"].append((label, amt))
        if "trader" in keys:
            row["trader_paid_on"] = e.trader_paid_on
        if "override" in keys:
            row["manager_paid_on"] = e.manager_paid_on
        if viewer.role == ROLE_OWNER:
            row["note"] = e.note
            row["deletable"] = not (e.trader_paid_on or e.manager_paid_on)
            row["has_override"] = c.manager_id is not None and e.override_amount != 0
        entries.append(row)

    view = {
        "rows": [(label, state[k]) for k, label in parties],
        "entries": entries,
        "months_elapsed": months,
        "term_months": c.term_months,
        "started": c.start_date is not None and c.start_date <= today,
        "clawback_applies": c.clawback_mode != eng.KOREKTA_BRAK,
    }
    if viewer.role == ROLE_OWNER:
        view["net_received"] = state["broker"].settled
        view["suggested_clawback"] = suggested_clawback(c, today)
    return view


def _blank() -> dict:
    return {"forecast": ZERO, "settled": ZERO, "remaining": ZERO, "at_risk": ZERO, "paid": ZERO, "to_pay": ZERO}


def register_view(viewer: User, contracts: list[Contract], today: date) -> dict:
    """Zbiorczy rejestr: sumy per strona i lista pozycji do wypłaty."""
    labels = {
        "broker": "Spółki obrotu → broker",
        "trader_all": "Prowizje handlowców",
        "override_all": "Override menedżerów",
        "owner": "Marża właściciela",
        "mine": "Twoja prowizja z własnej sprzedaży",
        "team_trader": "Prowizje handlowców Twojego zespołu",
        "my_override": "Twój override od zespołu",
    }
    totals: dict[str, dict] = {}

    def add(key: str, st: PartyState):
        t = totals.setdefault(key, _blank())
        t["forecast"] += st.forecast
        t["settled"] += st.settled
        t["remaining"] += st.remaining
        t["at_risk"] += st.at_risk
        if st.paid is not None:
            t["paid"] += st.paid
            t["to_pay"] += st.to_pay

    pending = []  # pozycje rozliczone, ale niewypłacone
    by_supplier: dict[str, dict] = {}
    is_owner = viewer.role == ROLE_OWNER

    for c in contracts:
        st = contract_state(c, today)
        if is_owner:
            add("broker", st["broker"])
            add("trader_all", st["trader"])
            if c.manager_id:
                add("override_all", st["override"])
            add("owner", st["owner"])
            s = by_supplier.setdefault(c.supplier.name, _blank())
            for f in ("forecast", "settled", "remaining", "at_risk"):
                s[f] += getattr(st["broker"], f)
        else:
            if c.trader_id == viewer.id:
                add("mine", st["trader"])
            elif c.manager_id == viewer.id:
                add("team_trader", st["trader"])
            if c.manager_id == viewer.id:
                add("my_override", st["override"])

        for e in c.entries:
            if (is_owner or c.trader_id == viewer.id) and e.trader_amount != 0 and not e.trader_paid_on:
                pending.append({
                    "entry_id": e.id, "contract_id": c.id, "client_name": c.client_name,
                    "booked_on": e.booked_on, "kind_label": e.kind_label, "who": "handlowiec",
                    "person": c.trader.name if is_owner else "Ty", "amount": e.trader_amount,
                })
            if (is_owner or c.manager_id == viewer.id) and c.manager_id and e.override_amount != 0 and not e.manager_paid_on:
                pending.append({
                    "entry_id": e.id, "contract_id": c.id, "client_name": c.client_name,
                    "booked_on": e.booked_on, "kind_label": e.kind_label, "who": "menedzer",
                    "person": c.manager.name if is_owner else "Ty, override", "amount": e.override_amount,
                })

    pending.sort(key=lambda p: (p["booked_on"], p["entry_id"]))
    order = ["broker", "trader_all", "override_all", "owner", "mine", "team_trader", "my_override"]
    rows = []
    for k in order:
        if k not in totals:
            continue
        t = totals[k]
        # „Do wypłaty” ma sens tylko dla osób, którym właściciel wypłaca.
        if k not in ("trader_all", "override_all", "mine", "my_override"):
            t["paid"] = t["to_pay"] = None
        rows.append((labels[k], t))
    view = {"rows": rows, "pending": pending, "pending_total": sum((p["amount"] for p in pending), ZERO)}
    if is_owner:
        view["by_supplier"] = sorted(by_supplier.items())
    return view


__all__ = [
    "KOREKTA",
    "contract_settlement_view",
    "contract_state",
    "delete_entry",
    "earned_ratio",
    "mark_paid",
    "months_elapsed",
    "record_entry",
    "register_view",
    "suggested_clawback",
]
