"""Cenniki spółek: budowa cennika, formularz BOK, projekt i zatwierdzenie (BOK i właściciel)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import cenniki as cn
from .. import services as svc
from ..db import get_db
from ..models import OH_MODES, PRICE_PRODUCTS, ROLE_BOK, ROLE_OWNER, TARIFF_GROUPS, PriceList, Supplier, User
from ..web.auth import current_user
from ..web.forms import FormError, p_date, p_dec
from ..web.ui import flash, form_data, redirect, render

router = APIRouter()


def bok_or_owner(user: User = Depends(current_user)) -> User:
    if user.role not in (ROLE_BOK, ROLE_OWNER):
        raise HTTPException(status_code=403)
    return user


def _supplier(db: Session, sid: int) -> Supplier:
    s = db.get(Supplier, sid)
    if not s:
        raise HTTPException(status_code=404)
    return s


@router.get("/cenniki", response_class=HTMLResponse)
def price_lists_page(request: Request, user: User = Depends(bok_or_owner), db: Session = Depends(get_db)):
    today = date.today()
    rows = []
    for s in db.scalars(select(Supplier).where(Supplier.active.is_(True)).order_by(Supplier.name)):
        pl = cn.current_list(db, s.id, today)
        rows.append({"s": s, "tpl": cn.template_of(db, s.id), "pl": pl, "stale": cn.stale(pl, today),
                     "draft": cn.latest_draft(db, s.id)})
    rows.sort(key=lambda r: (r["tpl"] is None, not r["stale"], r["s"].name))
    return render(request, "cenniki.html", {"user": user, "rows": rows, "today": today, "STALE_DAYS": cn.STALE_DAYS})


@router.get("/cenniki/{sid}/budowa", response_class=HTMLResponse)
def template_page(sid: int, request: Request, user: User = Depends(bok_or_owner), db: Session = Depends(get_db)):
    s = _supplier(db, sid)
    tpl = cn.template_of(db, s.id)
    form = {}
    if tpl:
        form = {"produkty": cn.products_of(tpl), "okresy": tpl.periods, "podzial": tpl.split, "segmenty": tpl.segments,
                "oh": tpl.oh_mode, "zakres": f"{tpl.max_volume_mwh.normalize():f}" if tpl.max_volume_mwh is not None else "",
                "indywidualna": f"{tpl.individual_from_mwh.normalize():f}" if tpl.individual_from_mwh is not None else "",
                "uwagi": tpl.note}
    return render(request, "cennik_budowa.html", _tpl_ctx(user, s, form))


def _tpl_ctx(user, s, form, **extra):
    ctx = {"user": user, "s": s, "form": form, "PRICE_PRODUCTS": PRICE_PRODUCTS, "OH_MODES": OH_MODES,
           "TARIFF_GROUPS": TARIFF_GROUPS}
    ctx.update(extra)
    return ctx


@router.post("/cenniki/{sid}/budowa")
async def template_save(sid: int, request: Request, user: User = Depends(bok_or_owner), db: Session = Depends(get_db)):
    s = _supplier(db, sid)
    form = await form_data(request)
    raw = await request.form()
    form["produkty"] = [p for p in raw.getlist("produkty")]
    try:
        cn.save_template(
            db, s, user, products=form["produkty"], periods=form.get("okresy", ""), split=form.get("podzial", ""),
            segments=form.get("segmenty", ""), oh_mode=form.get("oh", ""),
            max_volume=p_dec(form, "zakres", "Cennik dla klientów do (MWh rocznie)", required=False, minimum=0),
            individual_from=p_dec(form, "indywidualna", "Wycena indywidualna od (MWh rocznie)", required=False, minimum=0),
            note=form.get("uwagi", ""),
        )
        db.commit()
    except (FormError, svc.BusinessError) as e:
        db.rollback()
        return render(request, "cennik_budowa.html", _tpl_ctx(user, s, form, error=str(e)), 400)
    flash(request, f"Zapisano budowę cennika: {s.name}. Teraz wpisz ceny.")
    return redirect(f"/cenniki/{s.id}/nowy")


def _form_ctx(db, user, s, values, **extra):
    tpl = cn.template_of(db, s.id)
    ctx = {"user": user, "s": s, "tpl": tpl, "secs": cn.form_sections(tpl), "values": values,
           "today": date.today(), "OH_MODES": OH_MODES}
    ctx.update(extra)
    return ctx


@router.get("/cenniki/{sid}/nowy", response_class=HTMLResponse)
def new_list_page(sid: int, request: Request, user: User = Depends(bok_or_owner), db: Session = Depends(get_db)):
    s = _supplier(db, sid)
    if not cn.template_of(db, s.id):
        return redirect(f"/cenniki/{s.id}/budowa")
    draft = cn.latest_draft(db, s.id)
    source = draft or cn.current_list(db, s.id) or db.scalar(
        select(PriceList).where(PriceList.supplier_id == s.id, PriceList.status == "zatwierdzony")
        .order_by(PriceList.valid_from.desc()).limit(1))
    values = cn.values_of(source)
    meta = {"od": date.today().isoformat(), "do": "", "uwagi": ""}
    if draft:
        meta = {"od": draft.valid_from.isoformat(), "do": draft.valid_to.isoformat() if draft.valid_to else "", "uwagi": draft.note}
    return render(request, "cennik_formularz.html", _form_ctx(db, user, s, values, meta=meta, draft=draft, source=source))


@router.post("/cenniki/{sid}/nowy")
async def new_list_save(sid: int, request: Request, user: User = Depends(bok_or_owner), db: Session = Depends(get_db)):
    s = _supplier(db, sid)
    form = await form_data(request)
    try:
        pl = cn.save_draft(
            db, s, user, form, valid_from=p_date(form, "od", "Obowiązuje od"),
            valid_to=p_date(form, "do", "Obowiązuje do", required=False), note=form.get("uwagi", ""),
            draft=cn.latest_draft(db, s.id),
        )
        db.commit()
    except (FormError, svc.BusinessError) as e:
        db.rollback()
        meta = {"od": form.get("od", ""), "do": form.get("do", ""), "uwagi": form.get("uwagi", "")}
        return render(request, "cennik_formularz.html",
                      _form_ctx(db, user, s, form, meta=meta, draft=None, source=None, error=str(e)), 400)
    flash(request, "Zapisano projekt cennika. Sprawdź zmiany i zatwierdź.")
    return redirect(f"/cenniki/projekt/{pl.id}")


@router.get("/cenniki/projekt/{pid}", response_class=HTMLResponse)
def draft_page(pid: int, request: Request, user: User = Depends(bok_or_owner), db: Session = Depends(get_db)):
    pl = db.get(PriceList, pid)
    if not pl:
        raise HTTPException(status_code=404)
    tpl = cn.template_of(db, pl.supplier_id)
    prev = cn.previous_list(db, pl) if pl.status == "zatwierdzony" else cn.current_list(db, pl.supplier_id)
    return render(request, "cennik_projekt.html", {
        "user": user, "pl": pl, "prev": prev, "ch": cn.changes(db, tpl, pl, prev),
    })


@router.post("/cenniki/projekt/{pid}/zatwierdz")
async def draft_approve(pid: int, request: Request, user: User = Depends(bok_or_owner), db: Session = Depends(get_db)):
    await form_data(request)
    pl = db.get(PriceList, pid)
    if not pl:
        raise HTTPException(status_code=404)
    try:
        cn.approve(db, pl, user)
        db.commit()
    except svc.BusinessError as e:
        db.rollback()
        flash(request, f"Nie zatwierdzono: {e}")
        return redirect(f"/cenniki/projekt/{pid}")
    flash(request, f"Zatwierdzono cennik: {pl.supplier.name}, od {pl.valid_from:%d.%m.%Y}. Handlowcy widzą go w kalkulatorze.")
    return redirect("/cenniki")


@router.post("/cenniki/projekt/{pid}/usun")
async def draft_delete(pid: int, request: Request, user: User = Depends(bok_or_owner), db: Session = Depends(get_db)):
    await form_data(request)
    pl = db.get(PriceList, pid)
    if not pl or pl.status != "projekt":
        raise HTTPException(status_code=404)
    db.delete(pl)
    db.commit()
    flash(request, "Usunięto projekt cennika.")
    return redirect("/cenniki")
