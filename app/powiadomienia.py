"""Powiadomienia i dziennik firmy, etap N1 (docs/PROJEKT-POWIADOMIENIA.md). Bez FastAPI.

Zasady:
- powiadomienie tworzy wyłącznie platforma, przy konkretnym zdarzeniu (wysłanie NIP do BOK, wynik,
  faktury, umowa, zmiana statusu); osoba, która coś zrobiła, nie dostaje powiadomienia o własnym ruchu;
- treść to jedno zdanie bez danych poufnych (bez udziału brokera, przychodu spółki i kwot prowizji),
  szczegóły po wejściu w link, według uprawnień;
- wpisów nikt nie edytuje ani nie usuwa; zapisują się trzy czasy: powstało, zobaczone (adresat otworzył
  listę), przeczytane (adresat otworzył sprawę z powiadomienia);
- każdy widzi swoje; właściciel widzi wszystko w dzienniku firmy;
- w N1 wszystko przychodzi od razu; zbiorcze podsumowania, terminy i eskalacje to etap N3.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable, Optional

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .models import (
    NIP_CHECK_RESULTS,
    NOTIFICATION_KINDS,
    ROLE_BOK,
    ROLE_OWNER,
    Client,
    Contract,
    InvoiceTask,
    NipCheck,
    Notification,
    User,
)

PAGE_SIZE = 50
JOURNAL_PAGE = 100
# Statusy umowy, o których dowiaduje się także właściciel (sprawy pilne).
URGENT_STATUSES = {"Zerwana"}


def _plural_spolek(n: int) -> str:
    if n == 1:
        return "1 spółka"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} spółki"
    return f"{n} spółek"


# --------------------------------------------------------------------------
# Tworzenie
# --------------------------------------------------------------------------

def notify(
    db: Session, recipients: Iterable[Optional[User]], kind: str, text: str, *, url: str = "",
    actor: Optional[User] = None, client: Optional[Client] = None, contract: Optional[Contract] = None,
    urgent: bool = False,
) -> list[Notification]:
    """Dodaje powiadomienie dla każdej osoby z listy (bez powtórzeń, bez autora zdarzenia, tylko aktywne)."""
    if kind not in NOTIFICATION_KINDS:
        raise ValueError(f"Nieznany rodzaj powiadomienia: {kind}")
    out, seen = [], set()
    for r in recipients:
        if r is None or not r.active or r.id in seen or (actor is not None and r.id == actor.id):
            continue
        seen.add(r.id)
        n = Notification(
            recipient_id=r.id, recipient_name=r.name, recipient_role=r.role,
            actor_id=actor.id if actor else None, actor_name=actor.name if actor else "",
            kind=kind, text=text.strip()[:500], url=url[:300], urgent=urgent,
            client_id=client.id if client else None, contract_id=contract.id if contract else None,
        )
        db.add(n)
        out.append(n)
    return out


def bok_people(db: Session) -> list[User]:
    """Wszystkie aktywne osoby BOK. Platforma nie odróżnia jeszcze szefa BOK (pytanie 3 w projekcie)."""
    return list(db.scalars(select(User).where(User.role == ROLE_BOK, User.active.is_(True)).order_by(User.id)))


def owners(db: Session) -> list[User]:
    return list(db.scalars(select(User).where(User.role == ROLE_OWNER, User.active.is_(True)).order_by(User.id)))


def manager_of(db: Session, person: Optional[User]) -> Optional[User]:
    if person is None or not person.manager_id:
        return None
    return db.get(User, person.manager_id)


# --------------------------------------------------------------------------
# Zdarzenia procesu (wołane z warstwy stron po udanej akcji, przed zatwierdzeniem zapisu)
# --------------------------------------------------------------------------

def nip_sent(db: Session, c: Client, actor: User, n_suppliers: int) -> None:
    """Krok 3: handlowiec wysłał NIP do BOK."""
    notify(db, bok_people(db), "nip_nowe",
           f"Nowe NIP-y do sprawdzenia: {c.name}, {_plural_spolek(n_suppliers)}.",
           url="/bok", actor=actor, client=c)


def nip_resolved(db: Session, k: NipCheck, actor: User) -> None:
    """Krok 3: BOK wpisał wynik. Dostaje opiekun klienta i osoba, która zleciła sprawdzenie."""
    c = k.client
    result = NIP_CHECK_RESULTS.get(k.result, k.result).lower()
    text = f"{k.supplier.name}, klient {c.name}: {result}"
    if k.reserved_until:
        text += f" do {k.reserved_until:%d.%m.%Y}"
    requester = db.get(User, k.requested_by_id) if k.requested_by_id else None
    notify(db, [c.owner, requester], "nip_wynik", text + ".", url=f"/klienci/{c.id}", actor=actor, client=c)


def invoices_sent(db: Session, t: InvoiceTask, actor: User) -> None:
    """Krok 2: handlowiec przekazał zdjęcia faktur do BOK."""
    c = t.client
    notify(db, bok_people(db), "faktury_nowe", f"Nowe faktury do wprowadzenia: {c.name}.",
           url="/bok", actor=actor, client=c)


def invoices_done(db: Session, t: InvoiceTask, actor: User) -> None:
    """Krok 2: BOK zamknął zadanie z fakturami (dane wpisane albo faktury nieczytelne)."""
    c = t.client
    requester = db.get(User, t.requested_by_id) if t.requested_by_id else None
    if t.status == "anulowane":
        text = f"BOK nie odczytał faktur klienta {c.name}"
        text += f": {t.done_note}" if t.done_note else ". Wyślij nowe zdjęcia."
    else:
        text = f"Dane z faktur gotowe: {c.name}."
    notify(db, [c.owner, requester], "faktury_gotowe", text, url=f"/klienci/{c.id}#dane", actor=actor, client=c)


def contract_signed(db: Session, contract: Contract, actor: User) -> None:
    """Krok 5: zapisano umowę. Menedżer handlowca: dobra wiadomość; BOK: umowa do przygotowania.
    Handlowiec dostaje powiadomienie, gdy umowę zapisał za niego ktoś inny."""
    trader = contract.trader
    who = trader.name if trader else "handlowiec"
    supplier = contract.supplier.name if contract.supplier else "spółka"
    url = f"/umowy/{contract.id}"
    notify(db, [manager_of(db, trader), trader], "umowa_podpisana",
           f"Podpisana umowa: {who}, klient {contract.client_name}, {supplier}.",
           url=url, actor=actor, contract=contract)
    notify(db, bok_people(db), "umowa_do_przygotowania",
           f"Umowa do przygotowania: klient {contract.client_name}, {supplier}, handlowiec: {who}.",
           url=url, actor=actor, contract=contract)


def contract_status_changed(db: Session, contract: Contract, actor: User, old: str, new: str, note: str = "") -> None:
    """Krok 6: zmiana statusu umowy. Handlowiec i jego menedżer zawsze; przy zerwaniu także właściciel."""
    trader = contract.trader
    text = f"Umowa z klientem {contract.client_name}: status „{new}” (wcześniej „{old}”)"
    if new in URGENT_STATUSES:
        text += f". Powód: {note}" if note else ""
        recipients = [trader, db.get(User, contract.manager_id) if contract.manager_id else manager_of(db, trader)]
        notify(db, recipients + owners(db), "umowa_problem", text + ".", url=f"/umowy/{contract.id}",
               actor=actor, contract=contract, urgent=True)
        return
    recipients = [trader, db.get(User, contract.manager_id) if contract.manager_id else manager_of(db, trader)]
    notify(db, recipients, "umowa_status", text + ".", url=f"/umowy/{contract.id}", actor=actor, contract=contract)


# --------------------------------------------------------------------------
# Odczyt: znacznik, lista, przeczytanie
# --------------------------------------------------------------------------

def unseen_count(db: Session, user: User) -> int:
    """Liczba do znacznika w menu: jedno szybkie zapytanie po indeksie adresata."""
    return db.scalar(
        select(func.count(Notification.id)).where(Notification.recipient_id == user.id, Notification.seen_at.is_(None))
    ) or 0


def my_notifications(db: Session, user: User, limit: int = PAGE_SIZE) -> list[Notification]:
    return list(db.scalars(
        select(Notification).where(Notification.recipient_id == user.id)
        .order_by(Notification.id.desc()).limit(limit)
    ))


def mark_seen(db: Session, user: User) -> int:
    """Adresat otworzył listę: wszystkie jego niezobaczone dostają czas zobaczenia."""
    res = db.execute(
        update(Notification).where(Notification.recipient_id == user.id, Notification.seen_at.is_(None))
        .values(seen_at=datetime.utcnow())
    )
    return res.rowcount or 0


def open_notification(db: Session, user: User, nid: int) -> Optional[Notification]:
    """Adresat otworzył sprawę z powiadomienia. Cudze powiadomienie: None (strona zwraca 404)."""
    n = db.get(Notification, nid)
    if n is None or n.recipient_id != user.id:
        return None
    now = datetime.utcnow()
    if n.seen_at is None:
        n.seen_at = now
    if n.read_at is None:
        n.read_at = now
    return n


def mark_all_read(db: Session, user: User) -> int:
    now = datetime.utcnow()
    db.execute(update(Notification).where(Notification.recipient_id == user.id, Notification.seen_at.is_(None))
               .values(seen_at=now))
    res = db.execute(update(Notification).where(Notification.recipient_id == user.id, Notification.read_at.is_(None))
                     .values(read_at=now))
    return res.rowcount or 0


# --------------------------------------------------------------------------
# Dziennik firmy (tylko właściciel)
# --------------------------------------------------------------------------

@dataclass
class JournalFilters:
    person: Optional[int] = None
    kind: str = ""
    day_from: Optional[date] = None
    day_to: Optional[date] = None
    unread_only: bool = False


def journal(db: Session, f: JournalFilters, limit: int = JOURNAL_PAGE) -> tuple[list[Notification], int]:
    q = select(Notification)
    if f.person:
        q = q.where(Notification.recipient_id == f.person)
    if f.kind in NOTIFICATION_KINDS:
        q = q.where(Notification.kind == f.kind)
    if f.day_from:
        q = q.where(Notification.created_at >= datetime.combine(f.day_from, time.min))
    if f.day_to:
        q = q.where(Notification.created_at < datetime.combine(f.day_to + timedelta(days=1), time.min))
    if f.unread_only:
        q = q.where(Notification.read_at.is_(None))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = list(db.scalars(q.order_by(Notification.id.desc()).limit(limit)))
    return rows, total


def journal_people(db: Session) -> list[tuple[int, str]]:
    """Osoby, które kiedykolwiek dostały powiadomienie (także usunięte: imię z chwili zapisu)."""
    rows = db.execute(
        select(Notification.recipient_id, func.max(Notification.recipient_name))
        .where(Notification.recipient_id.is_not(None)).group_by(Notification.recipient_id)
    ).all()
    return sorted(((rid, name) for rid, name in rows), key=lambda r: r[1].lower())
