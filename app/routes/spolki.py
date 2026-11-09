"""Spółki obrotu i reguły prowizji (tylko właściciel)."""
from __future__ import annotations

from datetime import date

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import engine as eng
from .. import services as svc
from ..db import get_db
from ..models import (
    TRIGGERS,
    Supplier,
    SupplierRuleSet,
    User,
)
from ..web.auth import owner_only
from ..web.forms import (
    FormError,
    p_date,
    p_dec,
    p_int,
)
from ..web.ui import (
    flash,
    fmt_date,
    fmt_pct,
    form_data,
    redirect,
    render,
)

router = APIRouter()

@router.get("/spolki", response_class=HTMLResponse)
def suppliers_page(request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    suppliers = list(db.scalars(select(Supplier).order_by(Supplier.name)))
    rows = [(s, svc.current_rule_set(s)) for s in suppliers]
    return render(request, "spolki.html", {"user": user, "rows": rows})


@router.get("/spolki/nowa", response_class=HTMLResponse)
def supplier_new_page(request: Request, user: User = Depends(owner_only)):
    return render(request, "spolka_nowa.html", {"user": user, "form": {}})


@router.post("/spolki")
async def supplier_add(request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    form = await form_data(request)
    name = form.get("nazwa", "")
    if not name:
        return render(request, "spolka_nowa.html", {"user": user, "form": form, "error": "Podaj nazwę spółki."}, 400)
    if db.scalar(select(Supplier).where(Supplier.name == name)):
        return render(
            request, "spolka_nowa.html", {"user": user, "form": form, "error": f"Spółka {name} już istnieje."}, 400
        )
    s = Supplier(name=name)
    db.add(s)
    db.commit()
    flash(request, f"Dodano spółkę {name}. Ustaw teraz jej reguły prowizji.")
    return redirect(f"/spolki/{s.id}")


def _get_supplier(db: Session, sid: int) -> Supplier:
    s = db.get(Supplier, sid)
    if not s:
        raise HTTPException(status_code=404)
    return s


@router.get("/spolki/{sid}", response_class=HTMLResponse)
def supplier_page(sid: int, request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    s = _get_supplier(db, sid)
    return render(
        request,
        "spolka.html",
        {"user": user, "s": s, "current": svc.current_rule_set(s), "today": date.today(), "form": {}},
    )


@router.post("/spolki/{sid}/reguly")
async def supplier_rules_add(sid: int, request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    s = _get_supplier(db, sid)
    form = await form_data(request)
    try:
        rs = SupplierRuleSet(
            supplier_id=s.id,
            valid_from=p_date(form, "od", "Obowiązuje od"),
            broker_share_pct=p_dec(form, "udzial", "Udział brokera w narzucie", minimum=0, maximum=100),
            first_tranche_pct=p_dec(form, "transza", "Pierwsza transza", minimum=0, maximum=100),
            first_tranche_trigger=form.get("wyzwalacz") if form.get("wyzwalacz") in TRIGGERS else "weryfikacja",
            max_markup_pln_mwh=p_dec(form, "limit", "Limit marży", required=False, minimum=0),
            new_connection_months=p_int(form, "nowe_msc", "Okres rozliczeń z faktur dla nowych przyłączy", maximum=60),
            clawback_mode=form.get("korekta") if form.get("korekta") in eng.CLAWBACK_MODES else eng.KOREKTA_PROPORCJONALNA,
            note=form.get("uwagi", "")[:2000],
        )
    except FormError as e:
        return render(
            request,
            "spolka.html",
            {"user": user, "s": s, "current": svc.current_rule_set(s), "today": date.today(), "error": str(e), "form": form},
            400,
        )
    db.add(rs)
    db.commit()
    flash(
        request,
        f"Zapisano reguły {s.name} od {fmt_date(rs.valid_from)}: udział brokera {fmt_pct(rs.broker_share_pct)}, "
        f"pierwsza transza {fmt_pct(rs.first_tranche_pct)}. Umowy już zapisane zachowują swoje dotychczasowe reguły.",
    )
    return redirect(f"/spolki/{s.id}")


@router.post("/spolki/{sid}/aktywna")
async def supplier_toggle(sid: int, request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    s = _get_supplier(db, sid)
    await form_data(request)
    s.active = not s.active
    db.commit()
    flash(request, f"Spółka {s.name} jest teraz {'aktywna' if s.active else 'nieaktywna'}.")
    return redirect(f"/spolki/{s.id}")
