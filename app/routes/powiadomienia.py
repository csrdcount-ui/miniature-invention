"""Powiadomienia (każdy swoje) i dziennik firmy (właściciel). Logika w app/powiadomienia.py."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from .. import powiadomienia as pw
from ..db import get_db
from ..models import NOTIFICATION_KINDS, User
from ..web.auth import current_user, owner_only
from ..web.forms import is_id
from ..web.ui import flash, form_data, redirect, render
from .samouczek import _safe_path

router = APIRouter()


@router.get("/powiadomienia", response_class=HTMLResponse)
def notifications_page(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = pw.my_notifications(db, user)
    # „nowe” liczone przed zapisem czasu zobaczenia, żeby osoba wiedziała, które przyszły od ostatniej wizyty
    new_ids = {n.id for n in rows if n.seen_at is None}
    unread = sum(1 for n in rows if n.read_at is None)
    pw.mark_seen(db, user)
    db.commit()
    request.state.unseen_notifications = 0
    return render(request, "powiadomienia.html", {
        "user": user, "rows": rows, "new_ids": new_ids, "unread": unread, "KINDS": NOTIFICATION_KINDS,
        "limit": pw.PAGE_SIZE,
    })


@router.get("/powiadomienia/{nid}")
def notification_open(nid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = pw.open_notification(db, user, nid)
    if n is None:
        raise HTTPException(status_code=404)
    db.commit()
    return redirect(_safe_path(n.url, "/powiadomienia"))


@router.post("/powiadomienia/przeczytane")
async def notifications_all_read(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    await form_data(request)  # CSRF
    n = pw.mark_all_read(db, user)
    db.commit()
    flash(request, f"Oznaczono jako przeczytane: {n}." if n else "Wszystkie powiadomienia były już przeczytane.")
    return redirect("/powiadomienia")


def _day(raw: str):
    try:
        return date.fromisoformat(raw) if raw else None
    except ValueError:
        return None  # literówka w adresie = pusty filtr, nie błąd


@router.get("/konto/dziennik", response_class=HTMLResponse)
def journal_page(request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    q = request.query_params
    person = q.get("osoba", "")
    f = pw.JournalFilters(
        person=int(person) if is_id(person) else None,
        kind=q.get("rodzaj", "") if q.get("rodzaj", "") in NOTIFICATION_KINDS else "",
        day_from=_day(q.get("od", "")), day_to=_day(q.get("do", "")),
        unread_only=q.get("nieprzeczytane") == "1",
    )
    rows, total = pw.journal(db, f)
    active = bool(f.person or f.kind or f.day_from or f.day_to or f.unread_only)
    return render(request, "dziennik.html", {
        "user": user, "rows": rows, "total": total, "f": f, "active": active, "people": pw.journal_people(db),
        "KINDS": NOTIFICATION_KINDS, "limit": pw.JOURNAL_PAGE,
    })
