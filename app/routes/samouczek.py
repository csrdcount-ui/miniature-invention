"""Samouczek (kroki per rola, postęp) i uwagi testerów (zgłaszanie, lista dla właściciela)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import samouczek as sm
from ..db import get_db
from ..models import FEEDBACK_STATUSES, ROLES, Feedback, User
from ..web.auth import current_user, owner_only
from ..web.ui import flash, form_data, redirect, render

router = APIRouter()
MAX_FEEDBACK = 3000


def _safe_path(raw: str, default: str = "/") -> str:
    """Tylko adresy wewnątrz platformy (bez //, bez schematu), żeby nie dało się przekierować na obcą stronę."""
    raw = (raw or "").strip()
    if raw.startswith("/") and not raw.startswith("//") and "\\" not in raw and len(raw) <= 300 and "\n" not in raw:
        return raw
    return default


@router.get("/samouczek", response_class=HTMLResponse)
def tutorial_page(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    nip = sm.test_nip(db, user) if user.role in ("handlowiec", "menedzer", "wlasciciel") else ""
    done = sm.done_keys(db, user)
    sections = []
    for sec in sm.sections_for(user):
        steps = [{**s, "do": sm.fill(s["do"], user, nip), "expect": sm.fill(s["expect"], user, nip), "done": s["key"] in done}
                 for s in sec["steps"]]
        sections.append({**sec, "steps": steps})
    keys = sm.all_keys(user)
    return render(request, "samouczek.html", {
        "user": user, "sections": sections, "nip": nip, "plan": sm.PLAN_TESTU,
        "total": len(keys), "done_count": len([k for k in keys if k in done]), "role_label": ROLES.get(user.role, user.role),
    })


@router.post("/samouczek/krok")
async def tutorial_step(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    form = await form_data(request)
    key = form.get("krok", "")
    if not sm.set_step(db, user, key, form.get("zrobione") == "1"):
        raise HTTPException(status_code=400, detail="Nieznany krok samouczka.")
    db.commit()
    return redirect(f"/samouczek#krok-{key}")


@router.post("/samouczek/ukryj")
async def tutorial_hide(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    form = await form_data(request)
    sm.hide_invite(db, user)
    db.commit()
    return redirect(_safe_path(form.get("wroc", "/")))


@router.get("/uwagi", response_class=HTMLResponse)
def feedback_page(request: Request, user: User = Depends(current_user)):
    page = _safe_path(request.query_params.get("strona", ""), "/")
    return render(request, "uwagi.html", {"user": user, "page": page, "text": ""})


@router.post("/uwagi")
async def feedback_save(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    form = await form_data(request)
    page = _safe_path(form.get("strona", ""), "/")
    text = form.get("uwaga", "")
    if len(text) < 3:
        return render(request, "uwagi.html", {"user": user, "page": page, "text": text,
                                              "error": "Napisz, co było niejasne albo nie działało (co najmniej kilka słów)."}, 400)
    db.add(Feedback(user_id=user.id, role=user.role, url=page, text=text[:MAX_FEEDBACK]))
    db.commit()
    flash(request, "Dziękuję, uwaga zapisana. Właściciel zobaczy ją na liście.")
    return redirect(page)


@router.get("/konto/uwagi", response_class=HTMLResponse)
def feedback_list(request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    rows = list(db.scalars(select(Feedback).order_by(Feedback.status.desc(), Feedback.id.desc()).limit(300)))
    new = sum(1 for r in rows if r.status == "nowa")
    return render(request, "uwagi_lista.html", {"user": user, "rows": rows, "new": new, "STATUSES": FEEDBACK_STATUSES, "ROLES": ROLES})


@router.post("/konto/uwagi/{fid}/status")
async def feedback_status(fid: int, request: Request, user: User = Depends(owner_only), db: Session = Depends(get_db)):
    form = await form_data(request)
    f = db.get(Feedback, fid)
    if not f:
        raise HTTPException(status_code=404)
    f.status = "zalatwiona" if form.get("status") == "zalatwiona" else "nowa"
    db.commit()
    return redirect("/konto/uwagi")
