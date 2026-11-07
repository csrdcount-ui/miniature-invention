"""Raporty (w przygotowaniu)."""
from __future__ import annotations


from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..models import (
    User,
)
from ..web.auth import current_user
from ..web.ui import render

router = APIRouter()

@router.get("/raporty", response_class=HTMLResponse)
def reports_page(request: Request, user: User = Depends(current_user)):
    return render(request, "raporty.html", {"user": user})
