"""Nawigacja: zakładki główne i podsekcje zależne od roli."""
from __future__ import annotations

from typing import Optional

from ..models import ROLE_BOK, ROLE_MANAGER, ROLE_OWNER, ROLE_TRADER, User

# (klucz, podpis, adres, prefiksy adresów należących do zakładki, dostęp)
# dostęp: False (każdy zalogowany), "owner" (tylko właściciel),
#         "team" (właściciel, menedżer, albo BOK gdy widzi prowizje),
#         "seller" (handlowiec i menedżer: dzień pracy), "bok" (BOK i właściciel: kolejka zleceń)
# Na telefonie najwyżej 5 zakładek; Raporty (na razie zapowiedź) są podsekcją Portfela.
TABS = [
    ("dzien", "Mój dzień", "/dzien", ("/dzien",), "seller"),
    ("bok", "Zlecenia", "/bok", ("/bok", "/cenniki"), "bokq"),
    ("klienci", "Klienci", "/klienci", ("/klienci",), False),
    ("portfel", "Portfel", "/pulpit", ("/pulpit", "/umowy", "/raporty"), False),
    ("spolki", "Spółki", "/spolki", ("/spolki", "/cenniki"), "owner"),
    ("zespol", "Zespół", "/zespol", ("/zespol",), "team"),
    ("konto", "Konto", "/konto", ("/konto", "/haslo", "/samouczek", "/uwagi"), False),
]

# podsekcje widoczne tylko dla właściciela
OWNER_ONLY_SUBTABS = {"/konto/import", "/zespol/nowa", "/konto/listy", "/konto/uwagi"}

SUBTABS = {
    "portfel": [("Podsumowanie", "/pulpit"), ("Umowy", "/umowy"), ("Nowa umowa", "/umowy/nowa"), ("Raporty", "/raporty")],
    "klienci": [("Lista klientów", "/klienci"), ("Nowy klient", "/klienci/nowy")],
    "spolki": [("Lista spółek", "/spolki"), ("Cenniki", "/cenniki"), ("Dodaj spółkę", "/spolki/nowa")],
    "bok": [("Do sprawdzenia", "/bok"), ("Cenniki", "/cenniki")],
    "zespol": [("Lista osób", "/zespol"), ("Dodaj osobę", "/zespol/nowa")],
    "konto": [("Moje konto", "/konto"), ("Moje dane", "/konto/dane"), ("Zmiana hasła", "/haslo"),
              ("Samouczek", "/samouczek"), ("Zgłoś uwagę", "/uwagi"),
              ("Listy wymagań", "/konto/listy"), ("Uwagi testerów", "/konto/uwagi"), ("Import danych", "/konto/import")],
}


def _belongs(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def navigation(user: Optional[User], path: str, *, bok_sees_commissions: bool = False) -> dict:
    """Zakładki widoczne dla roli oraz podsekcje bieżącej zakładki."""
    if not user:
        return {"tabs": [], "sub": [], "section": None}
    tabs, active = [], None
    for key, label, url, prefixes, access in TABS:
        if access == "owner" and user.role != ROLE_OWNER:
            continue
        if access == "seller" and user.role not in (ROLE_MANAGER, ROLE_TRADER):
            continue
        if access == "bokq" and user.role != ROLE_BOK:
            continue
        if access == "team" and not (
            user.role in (ROLE_OWNER, ROLE_MANAGER) or (user.role == ROLE_BOK and bok_sees_commissions)
        ):
            continue
        is_active = any(_belongs(path, pre) for pre in prefixes)
        if is_active:
            active = key
        tabs.append({"key": key, "label": label, "url": url, "active": is_active})
    sub = []
    if active in SUBTABS:
        # najdłuższe pasujące dopasowanie wygrywa, np. /umowy/nowa przed /umowy
        items = [(lab, u) for lab, u in SUBTABS[active] if user.role == ROLE_OWNER or u not in OWNER_ONLY_SUBTABS]
        urls = [u for _, u in items]
        match = max((u for u in urls if _belongs(path, u)), key=len, default=None)
        sub = [{"label": lab, "url": u, "active": u == match} for lab, u in items]
    section = next((t["label"] for t in tabs if t["active"]), None)
    return {"tabs": tabs, "sub": sub, "section": section}
