"""Lejek sprzedaży: Mój dzień, karty klientów, zlecenia dla BOK, oferty, kalkulator, listy wymagań."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import engine as eng
from .. import pipeline as pl
from .. import services as svc
from ..db import get_db
from ..models import (
    CHECKLIST_KEYS,
    LEAD_SOURCES,
    LOST_REASONS,
    MEDIA,
    NIP_CHECK_RESULTS,
    OFFER_STATUSES,
    OPEN_STAGES,
    PRICING_PRODUCTS,
    ROLE_BOK,
    ROLE_MANAGER,
    ROLE_OWNER,
    ROLE_TRADER,
    SELLING_ROLES,
    STAGES,
    Client,
    ClientOffer,
    NipCheck,
    Supplier,
    User,
)
from ..web.auth import current_user, owner_only
from ..web.forms import FormError, p_date, p_dec, p_int
from ..web.ui import flash, form_data, redirect, render

router = APIRouter()


def _get_client(db: Session, user: User, cid: int) -> Client:
    c = db.get(Client, cid)
    if not c or not pl.can_view_client(user, c):
        raise HTTPException(status_code=404)
    return c


def _sellable(db: Session, user: User, cid: int) -> Client:
    c = _get_client(db, user, cid)
    if not pl.can_sell_for(user, c):
        raise HTTPException(status_code=403)
    return c


def _team_ids(db: Session, user: User) -> list[int]:
    return [user.id] + list(db.scalars(select(User.id).where(User.manager_id == user.id, User.active.is_(True))))


# --------------------------------------------------------------------------
# Mój dzień
# --------------------------------------------------------------------------

@router.get("/dzien", response_class=HTMLResponse)
def day_page(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role == ROLE_BOK:
        return redirect("/bok")
    month = svc.month_start()
    ctx = {"user": user, "d": pl.day_view(db, user), "mine": svc.month_sales(db, [user.id], month),
           "month_label": svc.month_label(month), "STAGES": STAGES, "OPEN_STAGES": OPEN_STAGES}
    if user.role == ROLE_MANAGER:
        people = list(db.scalars(select(User).where(User.manager_id == user.id, User.active.is_(True)).order_by(User.last_name)))
        ctx["team_funnels"] = [(p, pl.funnel(db, [p.id])) for p in people]
        ctx["team_funnel"] = pl.funnel(db, [p.id for p in people])
    return render(request, "dzien.html", ctx)


# --------------------------------------------------------------------------
# Lista klientów i nowy klient
# --------------------------------------------------------------------------

@router.get("/klienci", response_class=HTMLResponse)
def clients_page(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    qp = request.query_params
    q = pl.visible_clients_query(user)
    stage = qp.get("etap", "")
    if stage == "w_toku":
        q = q.where(Client.stage.in_(OPEN_STAGES))
    elif stage in STAGES:
        q = q.where(Client.stage == stage)
    owner = qp.get("handlowiec", "")
    if owner.isdigit():
        q = q.where(Client.owner_id == int(owner))
    text = qp.get("szukaj", "").strip()
    if text:
        digits = pl.clean_nip(text)
        cond = Client.name.ilike(f"%{text}%")
        q = q.where(or_(cond, Client.nip == digits) if len(digits) == 10 else cond)
    clients = list(db.scalars(q.order_by(Client.next_step_date.is_(None), Client.next_step_date, Client.name)))
    if user.role == ROLE_TRADER:
        people = []
    elif user.role == ROLE_MANAGER:
        people = [db.get(User, i) for i in _team_ids(db, user)]
    else:
        people = list(db.scalars(select(User).where(User.role.in_(SELLING_ROLES), User.active.is_(True)).order_by(User.last_name)))
    funnel = None
    if user.role in (ROLE_TRADER, ROLE_MANAGER):
        funnel = pl.funnel(db, _team_ids(db, user) if user.role == ROLE_MANAGER else [user.id])
    return render(request, "klienci.html", {
        "user": user, "clients": clients, "people": people, "qp": qp, "stage": stage, "funnel": funnel,
        "STAGES": STAGES, "OPEN_STAGES": OPEN_STAGES, "today": date.today(),
        "filtered": bool(stage or owner or text),
    })


def _new_ctx(db: Session, user: User, **extra) -> dict:
    owners = svc.assignable_traders(db, user) if user.role != ROLE_TRADER else [user]
    ctx = {"user": user, "owners": owners, "sources": LEAD_SOURCES, "form": {},
           "tomorrow": date.today() + timedelta(days=1)}
    ctx.update(extra)
    return ctx


@router.get("/klienci/nowy", response_class=HTMLResponse)
def client_new_page(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return render(request, "klient_nowy.html", _new_ctx(db, user))


@router.post("/klienci/nowy")
async def client_create(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    form = await form_data(request)
    try:
        oid = form.get("opiekun") or str(user.id)
        owner = db.get(User, int(oid)) if oid.isdigit() else None
        if not owner:
            raise FormError("Wybierz opiekuna klienta.")
        c = pl.create_client(
            db, actor=user, owner=owner, name=form.get("nazwa", ""), nip=form.get("nip", ""),
            contact_person=form.get("osoba", ""), phone=form.get("telefon", ""), email=form.get("email", ""),
            source=form.get("zrodlo") if form.get("zrodlo") in LEAD_SOURCES else "",
            next_step=form.get("krok", "") or "Pierwszy telefon: osoba decyzyjna i termin końca obecnej umowy",
            next_step_date=p_date(form, "krok_data", "Data następnego kroku", required=False) or date.today() + timedelta(days=1),
            note=form.get("notatka", ""),
        )
        db.commit()
    except (FormError, svc.BusinessError) as e:
        db.rollback()
        return render(request, "klient_nowy.html", _new_ctx(db, user, error=str(e), form=form), 400)
    flash(request, f"Zapisano klienta {c.name}. Następny krok: {c.next_step}, {c.next_step_date:%d.%m.%Y}.")
    return redirect(f"/klienci/{c.id}")


# --------------------------------------------------------------------------
# Karta klienta
# --------------------------------------------------------------------------

def _client_ctx(db: Session, user: User, c: Client, **extra) -> dict:
    today = date.today()
    suppliers = list(db.scalars(select(Supplier).where(Supplier.active.is_(True)).order_by(Supplier.name)))
    checked = {k.supplier_id: k for k in c.checks}
    ctx = {
        "user": user, "c": c, "today": today, "STAGES": STAGES, "OPEN_STAGES": OPEN_STAGES,
        "LOST_REASONS": LOST_REASONS, "NIP_CHECK_RESULTS": NIP_CHECK_RESULTS, "OFFER_STATUSES": OFFER_STATUSES,
        "can_sell": pl.can_sell_for(user, c), "suppliers": suppliers, "checked": checked,
        "free": pl.free_suppliers(c, today), "sources": LEAD_SOURCES,
        "offers": [(o, pl.offer_state(o, c, today), pl.offer_total_markup(o)) for o in c.offers],
        "need_offer": pl.checklist(db, "oferta"), "need_contract": pl.checklist(db, "umowa"),
        "form": {}, "week": today + timedelta(days=7),
    }
    ctx.update(extra)
    return ctx


@router.get("/klienci/{cid}", response_class=HTMLResponse)
def client_page(cid: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _get_client(db, user, cid)
    return render(request, "klient.html", _client_ctx(db, user, c))


def _error(request: Request, db: Session, user: User, c: Client, e: Exception, form: dict):
    db.rollback()
    db.refresh(c)
    return render(request, "klient.html", _client_ctx(db, user, c, error=str(e), form=form), 400)


@router.post("/klienci/{cid}/dzialanie")
async def client_action(cid: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _sellable(db, user, cid)
    form = await form_data(request)
    try:
        pl.log_contact(
            db, c, user, kind=form.get("rodzaj", "notatka"), text=form.get("wynik", ""),
            next_step=form.get("krok", ""), next_step_date=p_date(form, "krok_data", "Data następnego kroku", required=False),
            stage=form.get("etap", "") if form.get("etap") != c.stage else "", lost_reason=form.get("powod", ""),
        )
        db.commit()
    except (FormError, svc.BusinessError) as e:
        return _error(request, db, user, c, e, form)
    flash(request, "Zapisano." + (f" Następny krok: {c.next_step_date:%d.%m.%Y}." if c.next_step_date else ""))
    return redirect(f"/klienci/{c.id}")


@router.post("/klienci/{cid}/dane")
async def client_details(cid: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _sellable(db, user, cid)
    form = await form_data(request)
    try:
        name = form.get("nazwa", "").strip()
        if len(name) < 2:
            raise FormError("Podaj nazwę firmy.")
        nip = pl.clean_nip(form.get("nip", ""))
        pl.check_nip_free(db, nip, c.owner, exclude_id=c.id)
        if c.nip and nip != c.nip and any(k.result != "do_sprawdzenia" for k in c.checks):
            raise FormError("Nie zmieniaj NIP-u klienta sprawdzonego już przez BOK. Załóż nową kartę albo poproś BOK.")
        c.name, c.nip = name[:300], nip or None
        c.contact_person, c.phone, c.email = form.get("osoba", "")[:200], form.get("telefon", "")[:50], form.get("email", "")[:200]
        if form.get("zrodlo") in LEAD_SOURCES:
            c.source = form["zrodlo"]
        db.commit()
    except (FormError, svc.BusinessError) as e:
        return _error(request, db, user, c, e, form)
    flash(request, "Zapisano dane klienta.")
    return redirect(f"/klienci/{c.id}")


@router.post("/klienci/{cid}/bok")
async def client_request_check(cid: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _sellable(db, user, cid)
    await form_data(request)  # CSRF
    raw = await request.form()  # Starlette trzyma formularz w pamięci; getlist dla kilku pól wyboru
    ids = [int(x) for x in raw.getlist("spolka") if str(x).isdigit()]
    suppliers = [s for s in (db.get(Supplier, i) for i in ids) if s and s.active]
    try:
        n = pl.request_checks(db, c, user, suppliers)
        db.commit()
    except svc.BusinessError as e:
        return _error(request, db, user, c, e, {})
    flash(request, f"Wysłano do BOK: {n} {'spółka' if n == 1 else 'spółki' if 2 <= n <= 4 else 'spółek'} do sprawdzenia." if n else "Te spółki czekają już na BOK.")
    return redirect(f"/klienci/{c.id}")


@router.post("/klienci/{cid}/oferta")
async def client_offer(cid: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _sellable(db, user, cid)
    form = await form_data(request)
    try:
        s = db.get(Supplier, int(form.get("spolka", "0") or 0)) if form.get("spolka", "").isdigit() else None
        if not s:
            raise FormError("Wybierz spółkę z wolnym NIP-em.")
        sent = p_date(form, "wyslana", "Data wysłania", required=False) or date.today()
        pl.add_offer(
            db, c, user, supplier=s, pricing_product=form.get("produkt", "fix"), medium=form.get("medium", "energia"),
            base_price=p_dec(form, "cena_bazowa", "Cena bazowa", required=False, minimum=0),
            markup=p_dec(form, "marza", "Marża", minimum=0),
            volume=p_dec(form, "wolumen", "Wolumen roczny", minimum=Decimal("0.001")),
            term_months=p_int(form, "okres", "Okres w miesiącach", minimum=1, maximum=120),
            sent_date=sent, valid_until=p_date(form, "wazna_do", "Ważna do", required=False),
        )
        db.commit()
    except (FormError, svc.BusinessError, eng.EngineError) as e:
        return _error(request, db, user, c, e, form)
    flash(request, f"Zapisano ofertę. Zadzwoń do klienta {c.next_step_date:%d.%m.%Y}: zapytaj, jak oferta się podoba.")
    return redirect(f"/klienci/{c.id}")


@router.post("/klienci/{cid}/oferta/{oid}/odrzucona")
async def offer_rejected(cid: int, oid: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _sellable(db, user, cid)
    await form_data(request)
    o = db.get(ClientOffer, oid)
    if not o or o.client_id != c.id:
        raise HTTPException(status_code=404)
    o.status = "odrzucona"
    pl.add_event(db, c, user, "oferta", f"Klient odrzucił ofertę {o.supplier.name}.")
    db.commit()
    flash(request, "Oznaczono ofertę jako odrzuconą. Zmień etap albo złóż nową ofertę.")
    return redirect(f"/klienci/{c.id}")


def _dec(raw: str) -> Optional[Decimal]:
    try:
        return eng.D(raw.replace(",", ".").replace(" ", "")) if raw.strip() else None
    except (InvalidOperation, ValueError):
        return None


@router.get("/klienci/{cid}/kalkulator", response_class=HTMLResponse)
def calculator_page(cid: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _sellable(db, user, cid)
    qp = request.query_params
    free_ids = {s.id for s in pl.free_suppliers(c)}
    suppliers = [s for s in db.scalars(select(Supplier).where(Supplier.active.is_(True)).order_by(Supplier.name))]
    # najpierw spółki z wolnym NIP-em, potem pozostałe (do porównania przed zleceniem do BOK)
    suppliers.sort(key=lambda s: (s.id not in free_ids, s.name))
    price, volume = _dec(qp.get("cena", "")), _dec(qp.get("wolumen", ""))
    term = int(qp.get("okres")) if qp.get("okres", "").isdigit() else None
    bases = {s.id: v for s in suppliers if (v := _dec(qp.get(f"baza_{s.id}", ""))) is not None}
    rows, error = [], None
    if "cena" in qp:
        if not price or price <= 0 or not volume or volume <= 0 or not term or not 1 <= term <= 120:
            error = "Podaj cenę dla klienta, wolumen roczny i okres (1–120 miesięcy)."
        elif not bases:
            error = "Wpisz cenę bazową z cennika co najmniej jednej spółki."
        else:
            rows = pl.calculator(db, c, client_price=price, volume=volume, term_months=term, base_prices=bases,
                                 suppliers=[s for s in suppliers if s.id in bases])
            rows.sort(key=lambda r: (bool(r.error), -r.commission))
    return render(request, "kalkulator.html", {
        "user": user, "c": c, "suppliers": suppliers, "free_ids": free_ids, "qp": qp, "rows": rows, "error": error,
    })


# --------------------------------------------------------------------------
# BOK: kolejka zleceń sprawdzenia NIP
# --------------------------------------------------------------------------

def _bok_user(user: User = Depends(current_user)) -> User:
    if user.role not in (ROLE_BOK, ROLE_OWNER):
        raise HTTPException(status_code=403)
    return user


@router.get("/bok", response_class=HTMLResponse)
def bok_page(request: Request, user: User = Depends(_bok_user), db: Session = Depends(get_db)):
    checks = list(db.scalars(pl.pending_checks_query()))
    groups: dict[int, dict] = {}
    for k in checks:
        g = groups.setdefault(k.client_id, {"c": k.client, "checks": [], "since": k.requested_at})
        g["checks"].append(k)
    recent = list(db.scalars(select(NipCheck).where(NipCheck.checked_at.is_not(None)).order_by(NipCheck.checked_at.desc()).limit(15)))
    return render(request, "bok.html", {
        "user": user, "groups": list(groups.values()), "count": len(checks), "recent": recent,
        "NIP_CHECK_RESULTS": NIP_CHECK_RESULTS, "default_until": date.today() + timedelta(days=30),
    })


@router.post("/bok/{kid}")
async def bok_resolve(kid: int, request: Request, user: User = Depends(_bok_user), db: Session = Depends(get_db)):
    form = await form_data(request)
    k = db.get(NipCheck, kid)
    if not k:
        raise HTTPException(status_code=404)
    try:
        pl.resolve_check(db, k, user, form.get("wynik", ""), p_date(form, "do", "Rezerwacja do", required=False), form.get("uwagi", ""))
        db.commit()
    except (FormError, svc.BusinessError) as e:
        db.rollback()
        flash(request, f"Nie zapisano: {e}")
        return redirect("/bok")
    flash(request, f"Zapisano: {k.client.name}, {k.supplier.name} — {NIP_CHECK_RESULTS[k.result].lower()}.")
    return redirect("/bok")


# --------------------------------------------------------------------------
# Listy wymagań (właściciel)
# --------------------------------------------------------------------------

@router.get("/konto/listy", response_class=HTMLResponse)
def checklists_page(request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    lists = {k: "\n".join(pl.checklist(db, k)) for k in CHECKLIST_KEYS}
    return render(request, "listy.html", {"user": user, "lists": lists, "CHECKLIST_KEYS": CHECKLIST_KEYS})


@router.post("/konto/listy")
async def checklists_save(request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    form = await form_data(request)
    for k in CHECKLIST_KEYS:
        if k in form:
            pl.save_checklist(db, k, form[k], user)
    db.commit()
    flash(request, "Zapisano listy wymagań. Handlowcy widzą je na kartach klientów.")
    return redirect("/konto/listy")
