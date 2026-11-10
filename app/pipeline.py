"""Lejek sprzedaży: karty klientów, zlecenia sprawdzenia NIP dla BOK, oferty, dzień handlowca.

Bez FastAPI i bez warstwy stron. Zasada przewodnia: każdy klient w toku ma następny krok
z datą; klient bez następnego kroku trafia do „Pilne”.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from . import engine as eng
from . import services as svc
from .models import (
    CHECKLIST_DEFAULTS,
    CONTACT_KINDS,
    LOST_REASONS,
    OFFER_FOLLOWUP_DAYS,
    OFFER_VALID_DAYS,
    OPEN_STAGES,
    PRICING_PRODUCTS,
    ROLE_BOK,
    ROLE_MANAGER,
    ROLE_OWNER,
    SELLING_ROLES,
    STAGES,
    WORK_STAGES,
    Checklist,
    Client,
    ClientEvent,
    ClientOffer,
    Contract,
    NipCheck,
    Supplier,
    User,
)

MIN_WORK_THREADS = 3  # mniej niż 3 wątki w toku = pilny sygnał: dodaj nowych klientów
RESERVATION_WARN_DAYS = 7
DUPLICATE_NIP_MESSAGE = "NIP obsługuje już Twój kolega z biura. Zapytaj BOK o szczegóły."


BusinessError = svc.BusinessError  # wspólny typ błędu z services


# --------------------------------------------------------------------------
# Widoczność
# --------------------------------------------------------------------------

def visible_clients_query(user: User):
    q = select(Client)
    if user.role in (ROLE_OWNER, ROLE_BOK):
        return q
    if user.role == ROLE_MANAGER:
        team = select(User.id).where(User.manager_id == user.id)
        return q.where(or_(Client.owner_id == user.id, Client.owner_id.in_(team)))
    return q.where(Client.owner_id == user.id)


def can_view_client(user: User, c: Client) -> bool:
    if user.role in (ROLE_OWNER, ROLE_BOK):
        return True
    if c.owner_id == user.id:
        return True
    return user.role == ROLE_MANAGER and c.owner.manager_id == user.id


def can_sell_for(user: User, c: Client) -> bool:
    """Prowadzenie sprzedaży (etap, oferty, następny krok): opiekun, jego menedżer, właściciel."""
    return user.role != ROLE_BOK and can_view_client(user, c)


# --------------------------------------------------------------------------
# Karta klienta
# --------------------------------------------------------------------------

def clean_nip(raw: str) -> str:
    return "".join(ch for ch in (raw or "") if ch.isdigit())


def valid_nip(nip: str) -> bool:
    weights = [6, 5, 7, 2, 3, 4, 5, 6, 7]
    if len(nip) != 10:
        return False
    check = sum(int(d) * w for d, w in zip(nip, weights)) % 11
    return check != 10 and check == int(nip[9])


def add_event(db: Session, c: Client, user: Optional[User], kind: str, text: str, day: Optional[date] = None) -> ClientEvent:
    e = ClientEvent(client=c, kind=kind, text=text.strip(), day=day or date.today(), user_id=user.id if user else None)
    db.add(e)
    return e


def check_nip_free(db: Session, nip: str, owner: User, exclude_id: Optional[int] = None) -> None:
    """Jeden NIP = jedna karta w biurze. Kolega nie poznaje szczegółów (kto, jaki etap)."""
    if not nip:
        return
    if not valid_nip(nip):
        raise BusinessError("NIP ma niepoprawną sumę kontrolną.")
    other = db.scalar(select(Client).where(Client.nip == nip))
    if other and other.id != exclude_id:
        if other.owner_id == owner.id:
            raise BusinessError(f"Ten klient jest już na Twojej liście: {other.name}.")
        raise BusinessError(DUPLICATE_NIP_MESSAGE)


def create_client(
    db: Session, *, actor: User, owner: User, name: str, nip: str = "", contact_person: str = "",
    phone: str = "", email: str = "", source: str = "", next_step: str = "", next_step_date: Optional[date] = None,
    note: str = "", stage: str = "lead",
) -> Client:
    name = (name or "").strip()
    if len(name) < 2:
        raise BusinessError("Podaj nazwę firmy.")
    if owner.role not in SELLING_ROLES or not owner.active:
        raise BusinessError("Klienta może prowadzić tylko aktywny handlowiec, menedżer albo właściciel.")
    if not svc.can_assign_trader(actor, owner):
        raise BusinessError("Nie możesz przypisać klienta tej osobie.")
    nip = clean_nip(nip)
    check_nip_free(db, nip, owner)
    c = Client(
        name=name[:300], nip=nip or None, contact_person=contact_person.strip()[:200], phone=phone.strip()[:50],
        email=email.strip()[:200], source=source[:50], owner_id=owner.id, stage=stage if stage in STAGES else "lead",
        stage_since=date.today(), next_step=next_step.strip()[:300], next_step_date=next_step_date,
    )
    db.add(c)
    db.flush()
    add_event(db, c, actor, "system", "Karta klienta założona." + (f" {note.strip()}" if note.strip() else ""))
    return c


def set_stage(db: Session, c: Client, user: User, stage: str, lost_reason: str = "") -> None:
    if stage not in STAGES or stage == c.stage:
        return
    if stage == "przegrana":
        if lost_reason not in LOST_REASONS:
            raise BusinessError("Przy przegranej wybierz powód z listy.")
        c.lost_reason = lost_reason
    add_event(db, c, user, "etap", f"{STAGES[c.stage]} → {STAGES[stage]}" + (f". Powód: {lost_reason}" if stage == "przegrana" else ""))
    c.stage, c.stage_since = stage, date.today()
    if stage not in OPEN_STAGES:
        c.next_step, c.next_step_date = "", None


def log_contact(
    db: Session, c: Client, user: User, *, kind: str, text: str, next_step: str, next_step_date: Optional[date],
    stage: str = "", lost_reason: str = "",
) -> None:
    """Zapisz wynik działania i ustaw następny krok — jedna czynność, jak po każdej rozmowie."""
    if kind not in ("telefon", "spotkanie", "email", "notatka"):
        kind = "notatka"
    if text.strip():
        add_event(db, c, user, kind, text)
    if stage:
        set_stage(db, c, user, stage, lost_reason)
    if c.stage in OPEN_STAGES:
        if not next_step.strip() or not next_step_date:
            raise BusinessError("Klient w toku musi mieć następny krok z datą.")
        c.next_step, c.next_step_date = next_step.strip()[:300], next_step_date


# --------------------------------------------------------------------------
# Sprawdzenie NIP przez BOK
# --------------------------------------------------------------------------

def request_checks(db: Session, c: Client, user: User, suppliers: list[Supplier]) -> int:
    """Handlowiec wskazuje spółki, które chce ofertować; BOK sprawdza tylko te."""
    if not c.nip:
        raise BusinessError("Wpisz NIP klienta, zanim wyślesz go do BOK.")
    if not suppliers:
        raise BusinessError("Zaznacz spółki, w których chcesz ofertować.")
    existing = {k.supplier_id: k for k in c.checks}
    n = 0
    for s in suppliers:
        k = existing.get(s.id)
        if k and k.result == "do_sprawdzenia":
            continue
        if k:
            k.result, k.reserved_until, k.note, k.checked_by_id, k.checked_at = "do_sprawdzenia", None, "", None, None
            k.requested_by_id, k.requested_at = user.id, datetime.utcnow()
        else:
            db.add(NipCheck(client=c, supplier_id=s.id, requested_by_id=user.id))
        n += 1
    if n:
        add_event(db, c, user, "bok", "Wysłano do BOK do sprawdzenia NIP: " + ", ".join(s.name for s in suppliers) + ".")
    return n


def resolve_check(db: Session, k: NipCheck, user: User, result: str, reserved_until: Optional[date], note: str = "") -> None:
    from .models import NIP_CHECK_RESULTS
    if result not in NIP_CHECK_RESULTS or result == "do_sprawdzenia":
        raise BusinessError("Wybierz wynik sprawdzenia.")
    if result == "zarezerwowany" and not reserved_until:
        raise BusinessError("Podaj, do kiedy rezerwacja jest ważna.")
    k.result, k.reserved_until, k.note = result, reserved_until if result == "zarezerwowany" else None, note.strip()[:500]
    k.checked_by_id, k.checked_at = user.id, datetime.utcnow()
    text = f"{k.supplier.name}: {NIP_CHECK_RESULTS[result].lower()}"
    if k.reserved_until:
        text += f" do {k.reserved_until:%d.%m.%Y}"
    add_event(db, k.client, user, "bok", text + (f". {k.note}" if k.note else "."))


def free_suppliers(c: Client, today: Optional[date] = None) -> list[Supplier]:
    today = today or date.today()
    return [k.supplier for k in c.checks
            if k.result == "zarezerwowany" and (k.reserved_until is None or k.reserved_until >= today)]


def pending_checks_query():
    return select(NipCheck).where(NipCheck.result == "do_sprawdzenia").order_by(NipCheck.requested_at)


# --------------------------------------------------------------------------
# Oferty
# --------------------------------------------------------------------------

def add_offer(
    db: Session, c: Client, user: User, *, supplier: Supplier, pricing_product: str, medium: str,
    base_price: Optional[Decimal], markup: Decimal, volume: Decimal, term_months: int,
    sent_date: date, valid_until: Optional[date] = None,
) -> ClientOffer:
    if supplier not in free_suppliers(c, sent_date):
        raise BusinessError(f"W spółce {supplier.name} nie masz potwierdzonej rezerwacji NIP. Najpierw zleć sprawdzenie w BOK.")
    rs = svc.rule_set_on(db, supplier.id, sent_date)
    if rs is None:
        raise BusinessError(f"Spółka {supplier.name} nie ma reguł prowizji. Właściciel musi je ustawić.")
    if rs.max_markup_pln_mwh is not None and markup > rs.max_markup_pln_mwh:
        raise BusinessError(f"Marża {markup} zł/MWh przekracza limit spółki {supplier.name}: {rs.max_markup_pln_mwh} zł/MWh.")
    if volume <= 0 or term_months <= 0 or markup < 0:
        raise BusinessError("Wolumen i okres muszą być większe od zera, marża nie może być ujemna.")
    o = ClientOffer(
        client=c, supplier_id=supplier.id, pricing_product=pricing_product if pricing_product in PRICING_PRODUCTS else "fix",
        medium=medium if medium in ("energia", "gaz") else "energia", base_price_pln_mwh=base_price,
        markup_pln_mwh=markup, annual_volume_mwh=volume, term_months=term_months, sent_date=sent_date,
        valid_until=valid_until or sent_date + timedelta(days=OFFER_VALID_DAYS), created_by_id=user.id,
    )
    db.add(o)
    db.flush()
    add_event(db, c, user, "oferta",
              f"Oferta {supplier.name}, {PRICING_PRODUCTS.get(o.pricing_product)}, marża {markup} zł/MWh, ważna do {o.valid_until:%d.%m.%Y}.",
              sent_date)
    if c.stage in ("lead", "kontakt", "dane"):
        set_stage(db, c, user, "oferta")
    follow = sent_date + timedelta(days=OFFER_FOLLOWUP_DAYS)
    if not c.next_step_date or c.next_step_date > follow or c.stage == "oferta":
        c.next_step, c.next_step_date = "Zadzwoń w sprawie oferty: jak się podoba, czy coś poprawić", follow
    return o


def offer_total_markup(o: ClientOffer) -> Decimal:
    return eng.zl(eng.D(o.annual_volume_mwh) * eng.D(o.markup_pln_mwh) * Decimal(o.term_months) / 12)


def offer_state(o: ClientOffer, c: Client, today: date) -> dict:
    """Czy oferta wymaga telefonu, czy wygasa."""
    contacted = any(e.kind in CONTACT_KINDS and e.day > o.sent_date for e in c.events)
    days = (today - o.sent_date).days
    return {
        "days": days,
        "needs_followup": o.status == "otwarta" and days >= OFFER_FOLLOWUP_DAYS and not contacted,
        "expired": o.status == "otwarta" and o.valid_until < today,
        "expires_soon": o.status == "otwarta" and today <= o.valid_until <= today + timedelta(days=1),
    }


@dataclass
class CalcRow:
    supplier: Supplier
    base_price: Optional[Decimal]
    markup: Optional[Decimal]
    limit: Optional[Decimal]
    over_limit: bool
    total_markup: Decimal
    commission: Decimal
    tranche_a: Decimal
    first_tranche_pct: Optional[Decimal]
    free: bool
    error: str = ""


def calculator(db: Session, c: Client, *, client_price: Decimal, volume: Decimal, term_months: int,
               base_prices: dict[int, Decimal], suppliers: list[Supplier], today: Optional[date] = None) -> list[CalcRow]:
    """Ta sama cena dla klienta w kilku spółkach: ile marży, prowizji i transzy A w każdej.

    Pokazuje tylko kwoty handlowca (opiekuna klienta). Udział brokera u spółki zostaje ukryty.
    """
    today = today or date.today()
    rate = svc.user_rate_on(db, c.owner_id, today)
    share = rate.trader_share_pct if rate else Decimal(0)
    free_ids = {s.id for s in free_suppliers(c, today)}
    rows = []
    for s in suppliers:
        base = base_prices.get(s.id)
        rs = svc.rule_set_on(db, s.id, today)
        row = CalcRow(s, base, None, rs.max_markup_pln_mwh if rs else None, False, Decimal(0), Decimal(0), Decimal(0),
                      rs.first_tranche_pct if rs else None, s.id in free_ids)
        if rs is None:
            row.error = "spółka nie ma reguł prowizji"
        elif base is None:
            row.error = "wpisz cenę bazową z cennika"
        else:
            markup = client_price - base
            if markup < 0:
                row.error = "cena bazowa wyższa niż cena dla klienta"
            else:
                row.over_limit = rs.max_markup_pln_mwh is not None and markup > rs.max_markup_pln_mwh
                used = min(markup, rs.max_markup_pln_mwh) if row.over_limit else markup
                row.markup = used
                b = eng.calculate(eng.ContractTerms(
                    annual_volume_mwh=volume, term_months=term_months, markup_pln_mwh=used,
                    broker_share_pct=eng.D(rs.broker_share_pct), first_tranche_pct=eng.D(rs.first_tranche_pct),
                    trader_share_pct=eng.D(share),
                ))
                row.total_markup, row.commission, row.tranche_a = b.total_markup, b.trader.total, b.trader.tranche1
        rows.append(row)
    return rows


# --------------------------------------------------------------------------
# Lejek i dzień handlowca
# --------------------------------------------------------------------------

def funnel(db: Session, owner_ids: list[int], month: Optional[date] = None) -> dict:
    """Wypełnienie lejka: liczba klientów na każdym etapie + umowy podpisane w miesiącu."""
    month = month or svc.month_start()
    counts = {s: 0 for s in OPEN_STAGES}
    if owner_ids:
        for (stage,) in db.execute(select(Client.stage).where(Client.owner_id.in_(owner_ids), Client.stage.in_(OPEN_STAGES))):
            counts[stage] += 1
    signed = svc.month_sales(db, owner_ids, month)["count"] if owner_ids else 0
    work = sum(counts[s] for s in WORK_STAGES)
    return {"counts": counts, "signed": signed, "work": work, "low": work < MIN_WORK_THREADS, "min": MIN_WORK_THREADS}


def day_view(db: Session, user: User, today: Optional[date] = None) -> dict:
    today = today or date.today()
    clients = list(db.scalars(select(Client).where(Client.owner_id == user.id, Client.stage.in_(OPEN_STAGES))))
    overdue = sorted([c for c in clients if c.next_step_date and c.next_step_date < today], key=lambda c: c.next_step_date)
    no_step = [c for c in clients if not c.next_step_date]
    todays = [c for c in clients if c.next_step_date == today]
    week = sorted([c for c in clients if c.next_step_date and today < c.next_step_date <= today + timedelta(days=7)],
                  key=lambda c: c.next_step_date)
    followups, expiring = [], []
    for c in clients:
        for o in c.offers:
            st = offer_state(o, c, today)
            if st["needs_followup"] and not st["expired"]:  # wygasłej nie dublujemy: jest w „wygasła”
                followups.append((c, o, st))
            if st["expired"] or st["expires_soon"]:
                expiring.append((c, o, st))
    reservations = []
    for c in clients:
        for k in c.checks:
            if k.result == "zarezerwowany" and k.reserved_until and today <= k.reserved_until <= today + timedelta(days=RESERVATION_WARN_DAYS):
                reservations.append((c, k))
    since = datetime.utcnow() - timedelta(days=7)
    from_bok = list(db.scalars(
        select(NipCheck).join(Client).where(Client.owner_id == user.id, NipCheck.checked_at.is_not(None), NipCheck.checked_at >= since)
        .order_by(NipCheck.checked_at.desc())
    ))
    waiting_bok = list(db.scalars(
        select(NipCheck).join(Client).where(Client.owner_id == user.id, NipCheck.result == "do_sprawdzenia")
    ))
    f = funnel(db, [user.id])
    urgent = len(overdue) + len(no_step) + len(followups) + len(expiring) + len(reservations) + (1 if f["low"] else 0)
    return {
        "today": today, "overdue": overdue, "no_step": no_step, "todays": todays, "week": week,
        "followups": followups, "expiring": expiring, "reservations": reservations,
        "from_bok": from_bok, "waiting_bok": waiting_bok, "funnel": f, "urgent": urgent,
    }


def checklist(db: Session, key: str) -> list[str]:
    row = db.get(Checklist, key)
    body = row.body if row else CHECKLIST_DEFAULTS.get(key, "")
    return [line.strip() for line in body.splitlines() if line.strip()]


def save_checklist(db: Session, key: str, body: str, user: User) -> None:
    row = db.get(Checklist, key)
    if not row:
        row = Checklist(key=key)
        db.add(row)
    row.body, row.updated_by_id, row.updated_at = body.strip()[:5000], user.id, datetime.utcnow()


def win_with_contract(db: Session, c: Client, user: User, contract: Contract, offer: Optional[ClientOffer]) -> None:
    if offer and offer.client_id == c.id:
        offer.status = "przyjeta"
    add_event(db, c, user, "etap", f"Podpisana umowa z {contract.supplier.name} (umowa nr {contract.id}).")
    set_stage(db, c, user, "wygrana")
