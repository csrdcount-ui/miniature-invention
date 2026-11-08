"""Strony techniczne: wersja działająca na serwerze."""
from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ..web.ui import render

router = APIRouter()

# Chwila uruchomienia tej kopii aplikacji (po każdym wdrożeniu nowa).
STARTED_AT = datetime.now(timezone.utc)


def running_version() -> dict:
    """Render ustawia RENDER_GIT_COMMIT i RENDER_GIT_BRANCH przy każdym wdrożeniu."""
    commit = os.environ.get("RENDER_GIT_COMMIT", "")
    return {
        "commit": commit[:7] if commit else None,
        "commit_full": commit or None,
        "branch": os.environ.get("RENDER_GIT_BRANCH") or None,
        "started_at": STARTED_AT,
    }


@router.get("/wersja", response_class=HTMLResponse)
def version_page(request: Request):
    # Strona publiczna: bez logowania, żeby sprawdzić wdrożenie jednym adresem.
    return render(request, "wersja.html", {"v": running_version()})
