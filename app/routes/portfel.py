"""Portfel: pulpit, lista umów, nowa umowa, strona umowy i zmiana statusu."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import engine as eng
from .. import pipeline as pl
from .. import services as svc
from ..db import get_db
from ..models import (
    CONTRACT_STATUSES,
    MEDIA,
    PRICING_PRODUCTS,
    ROLE_BOK,
    ROLE_MANAGER,
    ROLE_OWNER,
    ROLE_TRADER,
    SELLING_ROLES,
    Client,
    ClientOffer,
    Contract,
    Supplier,
    User,
)
from ..web.auth import bok_perms, company_of, current_user
from ..web.forms import (
    FormError,
    p_date,
    p_dec,
    p_int,
    valid_nip,
)
from ..web.ui import (
    flash,
    fmt_date,
    form_data,
    redirect,
    render,
)

router = APIRouter()

@router.get("/pulpit", response_class=HTMLResponse)
def dashboard(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Pulpit nastawiony na bieżącą sprzedaż: miesiąc i target, oferty złożone, a statystyki zwinięte."""
    contracts = list(db.scalars(svc.visible_contracts_query(user)))
    perms = bok_perms(db)
    show_b = svc.tranche_b_visible(user, company_of(db))
    summary = svc.summary_for(user, contracts, perms)
    month = svc.month_start()
    qp = request.query_params
    stats_from, stats_to = svc.month_range(qp.get("od_mies", ""), qp.get("do_mies", ""))
    ctx = {
        "user": user, "summary": summary, "show_b": show_b,
        "recent": [svc.contract_view(user, c, perms, show_b) for c in contracts[:5]],
        "month_label": svc.month_label(month),
        "offers": svc.offers_overview(
            user, contracts, show_b, db=db,
            client_offers=[o for cl in db.scalars(pl.visible_clients_query(user).where(Client.stage == "oferta")) for o in cl.offers],
        ),
        "stats": svc.monthly_stats(contracts, stats_from, stats_to),
        "stats_open": "od_mies" in qp or "do_mies" in qp,
    }
    if user.role in (ROLE_TRADER, ROLE_MANAGER):
        ctx["mine"] = svc.month_sales(db, [user.id], month)
    if user.role == ROLE_MANAGER:
        team = [u.id for u in db.scalars(select(User).where(User.manager_id == user.id, User.active.is_(True)))]
        ctx["team"] = svc.month_sales(db, team, month)
        ctx["team_size"] = len(team)
    if user.role in (ROLE_OWNER, ROLE_BOK):
        sellers = [u.id for u in db.scalars(select(User).where(User.role.in_(SELLING_ROLES), User.active.is_(True)))]
        ctx["company_month"] = svc.month_sales(db, sellers, month)
    if user.role == ROLE_OWNER:
        suppliers = list(db.scalars(select(Supplier).order_by(Supplier.name)))
        ctx["suppliers_without_rules"] = [s.name for s in suppliers if not s.rule_sets]
        ctx["supplier_count"] = len(suppliers)
    return render(request, "pulpit.html", ctx)


def _opt_decimal(raw: str) -> Optional[Decimal]:
    try:
        return eng.D(raw.replace(",", ".")) if raw else None
    except (InvalidOperation, ValueError):
        return None


def _opt_date(raw: str) -> Optional[date]:
    try:
        return date.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def _filters_from_query(qp) -> svc.ContractFilters:
    """Parsowanie bez wyjątków: adres z literówką pokazuje po prostu pustą listę, nie błąd."""
    supplier_id = qp.get("spolka", "")
    trader_id = qp.get("handlowiec", "")
    nowe = qp.get("nowe", "")
    return svc.ContractFilters(
        products=tuple(p for p in qp.getlist("produkt") if p in PRICING_PRODUCTS),
        supplier_id=int(supplier_id) if supplier_id.isdigit() else None,
        medium=qp.get("medium") if qp.get("medium") in MEDIA else None,
        trader_id=int(trader_id) if trader_id.isdigit() else None,
        status=qp.get("status") if qp.get("status") in CONTRACT_STATUSES else None,
        signed_from=_opt_date(qp.get("od", "")),
        signed_to=_opt_date(qp.get("do", "")),
        volume_min=_opt_decimal(qp.get("wolumen_min", "")),
        volume_max=_opt_decimal(qp.get("wolumen_max", "")),
        markup_min=_opt_decimal(qp.get("narzut_min", "")),
        markup_max=_opt_decimal(qp.get("narzut_max", "")),
        new_connection={"tak": True, "nie": False}.get(nowe),
        sort=qp.get("sort") if qp.get("sort") in svc.SORT_OPTIONS else svc.DEFAULT_SORT,
    )


@router.get("/umowy", response_class=HTMLResponse)
def contracts_page(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    filters = _filters_from_query(request.query_params)
    q = svc.apply_contract_filters(svc.visible_contracts_query(user), filters)
    contracts = list(db.scalars(q))
    perms = bok_perms(db)
    show_b = svc.tranche_b_visible(user, company_of(db))
    views = [svc.contract_view(user, c, perms, show_b) for c in contracts]
    ctx = {
        "user": user,
        "contracts": views,
        "summary": svc.summary_for(user, contracts, perms),
        "filters": filters,
        "qp": request.query_params,
        "suppliers": list(db.scalars(select(Supplier).order_by(Supplier.name))),
        "traders": svc.assignable_traders(db, user) if user.role != ROLE_TRADER else [],
        "sort_options": svc.SORT_LABELS,
    }
    ctx["count_text"] = svc.plural_umowy(len(views))
    return render(request, "umowy.html", ctx)


@router.get("/umowy/liczba")
def contracts_count(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Licznik wyników na żywo podczas zaznaczania filtrów (te same filtry i ta sama widoczność co lista)."""
    filters = _filters_from_query(request.query_params)
    q = svc.apply_contract_filters(svc.visible_contracts_query(user), filters)
    n = len(list(db.scalars(q)))
    return JSONResponse(
        {"count": n, "text": svc.plural_umowy(n)},
        headers={"Cache-Control": "no-store"},
    )


def _new_contract_ctx(db: Session, user: User, **extra) -> dict:
    ctx = {
        "user": user,
        "suppliers": list(db.scalars(select(Supplier).where(Supplier.active.is_(True)).order_by(Supplier.name))),
        "traders": svc.assignable_traders(db, user),
        "today": date.today(),
        "form": {},
    }
    ctx.update(extra)
    return ctx


def _offer_from_query(db: Session, user: User, klient: str, oferta: str):
    """Umowa z oferty na karcie klienta: klient i oferta muszą być widoczne dla zapisującego."""
    if not (klient.isdigit() and oferta.isdigit()):
        return None, None
    c = db.get(Client, int(klient))
    o = db.get(ClientOffer, int(oferta))
    if not c or not o or o.client_id != c.id or not pl.can_sell_for(user, c):
        return None, None
    return c, o


@router.get("/umowy/nowa", response_class=HTMLResponse)
def contract_new_page(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c, o = _offer_from_query(db, user, request.query_params.get("klient", ""), request.query_params.get("oferta", ""))
    form = {}
    if c:
        form = {
            "klient": c.name, "nip": c.nip or "", "spolka": str(o.supplier_id), "medium": o.medium,
            "produkt": o.pricing_product, "handlowiec": str(c.owner_id), "okres": o.term_months,
            "wolumen": f"{o.annual_volume_mwh.normalize():f}", "narzut": f"{o.markup_pln_mwh.normalize():f}",
            "cena_bazowa": f"{o.base_price_pln_mwh.normalize():f}" if o.base_price_pln_mwh is not None else "",
            "klient_id": str(c.id), "oferta_id": str(o.id),
        }
    return render(request, "umowa_nowa.html", _new_contract_ctx(db, user, form=form))


@router.post("/umowy/nowa")
async def contract_create(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    form = await form_data(request)
    try:
        supplier = db.get(Supplier, int(form.get("spolka", "0") or 0))
        if not supplier or not supplier.active:
            raise FormError("Wybierz spółkę obrotu.")
        tid = form.get("handlowiec") or str(user.id)
        trader = db.get(User, int(tid)) if tid.isdigit() else None
        if not trader:
            raise FormError("Wybierz handlowca.")
        if not form.get("klient"):
            raise FormError("Pole „Nazwa klienta” jest wymagane.")
        nip = "".join(ch for ch in form.get("nip", "") if ch.isdigit())
        if nip and not valid_nip(nip):
            raise FormError("NIP ma niepoprawną sumę kontrolną.")
        c = svc.create_contract(
            db,
            actor=user,
            trader=trader,
            supplier=supplier,
            client_name=form["klient"],
            client_nip=nip,
            medium=form.get("medium") if form.get("medium") in MEDIA else "energia",
            signed_date=p_date(form, "podpisana", "Data podpisania"),
            start_date=p_date(form, "start", "Start dostaw", required=False),
            term_months=p_int(form, "okres", "Okres umowy w miesiącach", minimum=1, maximum=120),
            annual_volume_mwh=p_dec(form, "wolumen", "Wolumen roczny", minimum=Decimal("0.001")),
            markup_pln_mwh=p_dec(form, "narzut", "Marża", minimum=0),
            base_price_pln_mwh=p_dec(form, "cena_bazowa", "Cena bazowa spółki", required=False, minimum=0),
            new_connection=form.get("nowe_przylacze") == "1",
            status=form.get("status") if form.get("status") in CONTRACT_STATUSES else "Umowa podpisana",
            pricing_product=form.get("produkt") if form.get("produkt") in PRICING_PRODUCTS else None,
        )
    except (FormError, svc.BusinessError, eng.EngineError) as e:
        return render(request, "umowa_nowa.html", _new_contract_ctx(db, user, error=str(e), form=form), 400)
    client, offer = _offer_from_query(db, user, form.get("klient_id", ""), form.get("oferta_id", ""))
    if client:
        pl.win_with_contract(db, client, user, c, offer)
        db.commit()
    flash(request, f"Zapisano umowę z klientem {c.client_name}." + (" Klient przeszedł na etap „Umowa podpisana”." if client else ""))
    return redirect(f"/umowy/{c.id}")


def _get_visible_contract(db: Session, user: User, cid: int) -> Contract:
    c = db.get(Contract, cid)
    # 404 zamiast 403: nie zdradzamy, że umowa istnieje.
    if not c or not svc.can_view_contract(user, c):
        raise HTTPException(status_code=404)
    return c


def _contract_ctx(user: User, c: Contract, form: Optional[dict] = None, error: Optional[str] = None, perms=None, show_b: bool = True) -> dict:
    perms = perms or svc.DEFAULT_PERMS
    return {
        "user": user,
        "c": svc.contract_view(user, c, perms, show_b),
        "can_edit_status": svc.can_edit_status(user, c, perms),
        "history": c.events,
        "since": svc.status_since(c),
        "today": date.today(),
        "form": form or {},
        "error": error,
    }


@router.get("/umowy/{cid}", response_class=HTMLResponse)
def contract_page(cid: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _get_visible_contract(db, user, cid)
    return render(request, "umowa.html", _contract_ctx(user, c, perms=bok_perms(db), show_b=svc.tranche_b_visible(user, company_of(db))))


@router.post("/umowy/{cid}/status")
async def contract_status(cid: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _get_visible_contract(db, user, cid)
    form = await form_data(request)
    try:
        when = p_date(form, "data", "Data zdarzenia", required=False) or date.today()
        svc.change_status(db, actor=user, c=c, new_status=form.get("status", ""), effective_date=when, note=form.get("notatka", ""), perms=bok_perms(db))
    except (FormError, svc.BusinessError) as e:
        db.rollback()
        return render(request, "umowa.html", _contract_ctx(user, c, form, str(e), perms=bok_perms(db), show_b=svc.tranche_b_visible(user, company_of(db))), 400)
    flash(request, f"Status umowy: {c.status}, od {fmt_date(when)}. Zmiana zapisana w historii.")
    return redirect(f"/umowy/{c.id}")
