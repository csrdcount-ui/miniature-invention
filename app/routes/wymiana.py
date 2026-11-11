"""Import danych z pliku Excela: szablon, plik demonstracyjny, podgląd, zatwierdzenie, cofnięcie.

Na razie tylko właściciel. Uprawnienie BOK do importu zespołu i umów: kolejny krok.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import services as svc
from ..db import get_db
from ..exchange import importer
from ..exchange.demo import demo_workbook
from ..exchange.standard import build_workbook
from ..models import ImportBatch, User
from ..web.auth import owner_only
from ..web.ui import flash, form_data, redirect, render

router = APIRouter()

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _download(content: bytes, filename: str) -> Response:
    return Response(content, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _batch(db: Session, bid: int) -> ImportBatch:
    b = db.get(ImportBatch, bid)
    if not b:
        raise HTTPException(status_code=404)
    return b


@router.get("/konto/import", response_class=HTMLResponse)
def import_page(request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    batches = list(db.scalars(select(ImportBatch).where(ImportBatch.status != "odrzucony").order_by(ImportBatch.id.desc()).limit(30)))
    rows = [(b, importer.Report.from_json(b.summary)) for b in batches]
    missing = len(importer.demo_suppliers_without_prices(db))
    return render(request, "import.html", {"user": user, "batches": rows, "demo_prices_missing": missing})


@router.get("/konto/import/szablon.xlsx")
def template_download(user: User = Depends(owner_only)):
    return _download(build_workbook(), "szablon-importu.xlsx")


@router.get("/konto/import/demo.xlsx")
def demo_download(user: User = Depends(owner_only)):
    return _download(demo_workbook(), f"dane-demonstracyjne-{date.today().isoformat()}.xlsx")


@router.post("/konto/import")
async def import_upload(request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    form = await form_data(request)
    f = form.get("plik")
    if not f or not getattr(f, "filename", ""):
        flash(request, "Błąd: wybierz plik Excela do wgrania.")
        return redirect("/konto/import")
    if not f.filename.lower().endswith(".xlsx"):
        flash(request, "Błąd: plik musi mieć rozszerzenie .xlsx.")
        return redirect("/konto/import")
    content = await f.read(importer.MAX_FILE_BYTES + 1)
    batch = importer.preview(db, actor=user, filename=f.filename, content=content)
    return redirect(f"/konto/import/{batch.id}")


@router.post("/konto/import/demo")
async def import_demo(request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    await form_data(request)
    batch = importer.preview(
        db, actor=user, filename=f"dane-demonstracyjne-{date.today().isoformat()}.xlsx", content=demo_workbook()
    )
    return redirect(f"/konto/import/{batch.id}")


@router.post("/konto/import/demo-cenniki")
async def import_demo_prices(request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    await form_data(request)
    n = importer.add_demo_price_lists(db, user)
    flash(request, f"Dodano {n} cenników demonstracyjnych (ceny fikcyjne). Sprawdź je w Spółki, Cenniki, potem w kalkulatorze na karcie klienta."
          if n else "Wszystkie spółki demo mają już cenniki.")
    return redirect("/konto/import")


@router.get("/konto/import/{bid}", response_class=HTMLResponse)
def batch_page(bid: int, request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    b = _batch(db, bid)
    return render(request, "import_raport.html", {
        "user": user, "b": b, "r": importer.Report.from_json(b.summary),
        "blockers": importer.blockers(db, b) if b.status == "zatwierdzony" else [],
        "max_errors": importer.MAX_ERRORS_SHOWN,
    })


@router.post("/konto/import/{bid}/zatwierdz")
async def batch_commit(bid: int, request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    await form_data(request)
    b = _batch(db, bid)
    try:
        report = importer.commit(db, actor=user, batch=b)
    except svc.BusinessError as e:
        flash(request, f"Błąd: {e}")
        return redirect(f"/konto/import/{bid}")
    # hasła pokazujemy tylko teraz, w tej odpowiedzi; nigdzie ich nie zapisujemy
    resp = render(request, "import_wynik.html", {"user": user, "b": b, "r": report})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.post("/konto/import/{bid}/odrzuc")
async def batch_reject(bid: int, request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    await form_data(request)
    importer.reject(db, _batch(db, bid))
    flash(request, "Import anulowany. Nic nie zostało zapisane.")
    return redirect("/konto/import")


@router.post("/konto/import/{bid}/cofnij")
async def batch_revert(bid: int, request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    form = await form_data(request)
    b = _batch(db, bid)
    if form.get("potwierdzam") != "1":
        flash(request, "Błąd: zaznacz potwierdzenie, że chcesz usunąć dane z tego importu.")
        return redirect(f"/konto/import/{bid}")
    try:
        counts = importer.revert(db, b)
    except svc.BusinessError as e:
        flash(request, f"Błąd: {e}")
        return redirect(f"/konto/import/{bid}")
    flash(request, f"Import cofnięty. Usunięto: umów {counts['umowy']}, osób {counts['osoby']}, spółek {counts['spolki']}.")
    return redirect("/konto/import")
