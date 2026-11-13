"""Punkty poboru, dane z faktur i „odeślij do BOK” (zdjęcia faktur). Strony; logika w app/faktury.py."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from .. import faktury as fk
from .. import services as svc
from ..db import get_db
from ..models import INVOICE_TASK_STATUSES, ROLE_BOK, ROLE_OWNER, InvoicePhoto, InvoiceTask, MeteringPoint, User
from ..pipeline import can_view_client
from ..web.auth import current_user
from ..web.forms import FormError, p_date, p_dec, p_int
from ..web.ui import flash, form_data, redirect, render
from .klienci import _bok_user, _error, _get_client

router = APIRouter()


def _enterable(db: Session, user: User, cid: int):
    c = _get_client(db, user, cid)
    if not fk.can_enter_data(user, c):
        raise HTTPException(status_code=403)
    return c


def _point(c, pid: int) -> MeteringPoint:
    p = next((p for p in c.points if p.id == pid), None)
    if not p:
        raise HTTPException(status_code=404)
    return p


@router.post("/klienci/{cid}/punkty")
async def point_add(cid: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _enterable(db, user, cid)
    form = await form_data(request)
    try:
        notice = form.get("wypowiedzenie", "")
        fk.add_point(
            db, c, user, ppe=form.get("ppe", ""), address=form.get("adres", ""), tariff_group=form.get("grupa", ""),
            current_seller=form.get("sprzedawca", ""), contract_end=p_date(form, "koniec", "Koniec obecnej umowy", required=False),
            notice_months=p_int(form, "wypowiedzenie", "Okres wypowiedzenia w miesiącach", maximum=36) if notice else None,
        )
        db.commit()
    except (FormError, svc.BusinessError) as e:
        return _error(request, db, user, c, e, form)
    flash(request, "Dodano punkt poboru. Wpisz dane z faktur albo odeślij zdjęcia do BOK.")
    return redirect(f"/klienci/{c.id}#dane")


@router.post("/klienci/{cid}/punkty/{pid}/faktura")
async def reading_add(cid: int, pid: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _enterable(db, user, cid)
    p = _point(c, pid)
    form = await form_data(request)
    try:
        fk.add_reading(
            db, p, user,
            period_from=p_date(form, "od", "Okres od"), period_to=p_date(form, "do", "Okres do"),
            meter_start=p_dec(form, "licznik_od", "Stan licznika na początek okresu", required=False, minimum=0),
            meter_end=p_dec(form, "licznik_do", "Stan licznika na koniec okresu", required=False, minimum=0),
            consumption_kwh=p_dec(form, "zuzycie", "Zużycie w okresie, kWh", required=False, minimum=0),
        )
        db.commit()
    except (FormError, svc.BusinessError) as e:
        return _error(request, db, user, c, e, form)
    db.refresh(p)
    v = fk.annual_volume(p.readings)
    flash(request, f"Zapisano dane z faktury. Wolumen roczny: {v.mwh} MWh." if v.mwh is not None
          else "Zapisano dane z faktury. Do wolumenu rocznego potrzeba faktur z co najmniej 10 miesięcy.")
    return redirect(f"/klienci/{c.id}#dane")


@router.post("/klienci/{cid}/punkty/{pid}/faktura/{rid}/usun")
async def reading_delete(cid: int, pid: int, rid: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _enterable(db, user, cid)
    p = _point(c, pid)
    await form_data(request)
    r = next((r for r in p.readings if r.id == rid), None)
    if not r:
        raise HTTPException(status_code=404)
    db.delete(r)
    db.commit()
    flash(request, "Usunięto dane z faktury.")
    return redirect(f"/klienci/{c.id}#dane")


@router.post("/klienci/{cid}/faktury-bok")
async def task_request(cid: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _get_client(db, user, cid)
    form = await form_data(request)  # CSRF
    raw = await request.form()
    files = []
    for f in raw.getlist("zdjecia"):
        if getattr(f, "filename", ""):
            files.append(await f.read(fk.MAX_UPLOAD_BYTES + 1))
    try:
        fk.request_task(db, c, user, files, form.get("uwagi", "") if isinstance(form.get("uwagi", ""), str) else "")
        db.commit()
    except svc.BusinessError as e:
        return _error(request, db, user, c, e, {})
    flash(request, "Wysłano faktury do BOK. Dostaniesz informację, gdy dane będą wprowadzone. Możesz prowadzić rozmowę dalej.")
    return redirect(f"/klienci/{c.id}#dane")


# --------------------------------------------------------------------------
# BOK: zadanie z fakturami
# --------------------------------------------------------------------------

def _task(db: Session, tid: int) -> InvoiceTask:
    t = db.get(InvoiceTask, tid)
    if not t:
        raise HTTPException(status_code=404)
    return t


@router.get("/bok/faktury/{tid}", response_class=HTMLResponse)
def task_page(tid: int, request: Request, user: User = Depends(_bok_user), db: Session = Depends(get_db)):
    t = _task(db, tid)
    return render(request, "bok_faktury.html", {"user": user, "t": t, "STATUSES": INVOICE_TASK_STATUSES,
                                                "all_downloaded": fk.all_downloaded(t)})


@router.get("/bok/faktury/{tid}/zdjecie/{phid}")
def task_photo(tid: int, phid: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = _task(db, tid)
    if not can_view_client(user, t.client):
        raise HTTPException(status_code=404)
    ph = db.get(InvoicePhoto, phid)
    if not ph or ph.task_id != t.id:
        raise HTTPException(status_code=404)
    headers = {"Cache-Control": "private, no-store"}
    if request.query_params.get("pobierz") == "1" and user.role in (ROLE_BOK, ROLE_OWNER):
        # pobranie do dokumentacji biura: zapisujemy kto i kiedy (warunek bezpiecznego usunięcia)
        fk.mark_downloaded([ph], user)
        db.commit()
        name = fk.photo_filename(t, ph, t.photos.index(ph) + 1)
        headers["Content-Disposition"] = f'attachment; filename="{name}"'
    return Response(ph.data, media_type=ph.content_type, headers=headers)


@router.get("/bok/faktury/{tid}/pobierz")
def task_zip(tid: int, user: User = Depends(_bok_user), db: Session = Depends(get_db)):
    t = _task(db, tid)
    if not t.photos:
        raise HTTPException(status_code=404)
    data = fk.zip_task(t)
    fk.mark_downloaded(list(t.photos), user)
    db.commit()
    return Response(data, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="{fk.zip_name(t)}"', "Cache-Control": "private, no-store"})


@router.post("/bok/faktury/{tid}/archiwizuj")
async def task_archive(tid: int, request: Request, user: User = Depends(_bok_user), db: Session = Depends(get_db)):
    t = _task(db, tid)
    form = await form_data(request)
    try:
        n = fk.archive_photos(db, t, user, confirmed=form.get("potwierdzam") == "1",
                              without_download=form.get("bez_pobrania") == "1")
        db.commit()
    except svc.BusinessError as e:
        db.rollback()
        flash(request, f"Nie usunięto: {e}")
        return redirect(f"/bok/faktury/{t.id}")
    flash(request, f"Usunięto z platformy {n} {'plik' if n == 1 else 'pliki' if n < 5 else 'plików'}: {t.client.name}. Dane na karcie klienta zostają.")
    return redirect("/bok")


@router.post("/bok/faktury/{tid}/zamknij")
async def task_close(tid: int, request: Request, user: User = Depends(_bok_user), db: Session = Depends(get_db)):
    t = _task(db, tid)
    form = await form_data(request)
    try:
        fk.finish_task(db, t, user, form.get("uwagi", ""), cancel=form.get("wynik") == "anuluj")
        db.commit()
    except svc.BusinessError as e:
        db.rollback()
        flash(request, f"Nie zapisano: {e}")
        return redirect(f"/bok/faktury/{t.id}")
    flash(request, f"Zamknięto zadanie: {t.client.name}. Faktury czekają na pobranie do dokumentacji biura.")
    return redirect(f"/bok/faktury/{t.id}")
