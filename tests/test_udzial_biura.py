"""Udział w masie marży biura: suma 100%, widoczność (właściciel, menedżer), ocena tendencji."""
from datetime import date
from decimal import Decimal as D

from app import services as svc
from app.db import SessionLocal
from app.models import ROLE_BOK, ROLE_MANAGER, ROLE_TRADER, User
from app.security import hash_password

from .conftest import login, post
from .test_app import PW, _ustaw_bok, setup_company
from .test_import import _commit, _demo_preview

SEKCJA = "Udział w masie marży biura"


def _demo(client):
    setup_company(client)
    login(client, "kris@firma.pl")
    _commit(client, _demo_preview(client))
    with SessionLocal() as db:
        for u in db.query(User).filter(User.email.like("%@demo.invalid")):
            u.password_hash = hash_password(PW)
        db.commit()


def test_udzialy_wszystkich_sprzedawcow_sumuja_sie_do_100(client):
    _demo(client)
    with SessionLocal() as db:
        ids = [u.id for u in db.query(User).filter(User.role.in_((ROLE_MANAGER, ROLE_TRADER)))]
        sh = svc.office_markup_shares(db, ids, svc.month_start())
    assert len(sh["months"]) == 6
    for i, (label, total) in enumerate(sh["total_months"]):
        parts = [d["months"][i][1] for d in sh["people"].values() if d["months"][i][1] is not None]
        if total > 0:
            assert abs(sum(parts, D(0)) - 100) <= D("0.1") * len(parts), (label, parts)  # zaokrąglenia do 0,1
    assert sh["team_current"] in (D(100), None)


def test_widzi_wlasciciel_i_menedzer_nie_handlowiec_ani_bok(client):
    _demo(client)
    page = client.get("/zespol").text
    assert SEKCJA in page and "Masa marży biura, " in page
    assert "Prowizja: " in page and "masy marży z własnych umów" in page
    _ustaw_bok(client, bok_sees_commissions=True)  # BOK widzi zakładkę Zespół, ale nie udział
    with SessionLocal() as db:
        manager = db.query(User).filter_by(role=ROLE_MANAGER).filter(User.email.like("%@demo.invalid")).first().email
        trader = db.query(User).filter_by(role=ROLE_TRADER).filter(User.email.like("%@demo.invalid")).first().email
        bok = db.query(User).filter_by(role=ROLE_BOK).filter(User.email.like("%@demo.invalid")).first().email
    login(client, manager, PW)
    page = client.get("/zespol").text
    assert SEKCJA in page and "Twój zespół, " in page
    assert "Masa marży biura, " not in page  # kwoty całego biura widzi tylko właściciel
    login(client, bok, PW)
    r = client.get("/zespol")
    assert r.status_code == 200 and SEKCJA not in r.text
    login(client, trader, PW)
    r = client.get("/zespol")
    assert r.status_code == 403 and SEKCJA not in r.text
    for url in ("/pulpit", "/dzien", "/umowy"):
        assert SEKCJA not in client.get(url).text


def test_ocena_tendencji():
    t = svc.share_trend
    s = lambda *xs: [None if x is None else D(x) for x in xs]
    assert t(s(20, 20, 20, 20, 21, 19)) == "w normie"
    assert t(s(20, 20, 20, 21, 20, 10)).startswith("słabszy bieżący miesiąc")
    assert t(s(20, 20, 20, 21, 10, 10)).startswith("słabiej drugi miesiąc z rzędu")
    assert t(s(20, 20, 20, 10, 10, 10)).startswith("trwała tendencja spadkowa: 3 miesiące")
    assert t(s(33.5, 9.5, 0, 0, 79.4, 59.4)) == "powyżej średniej"  # sprzedaż zrywami: nie „stabilnie”
    assert t(s(None, None, None, None, None, 10)) == "za krótka historia"
    assert t(s(0, 0, 0, 0, 0, 5)) == "powyżej średniej"
    assert t(s(0, 0, 0, 0, 0, 0)) == "brak sprzedaży od 6 miesięcy"
    assert t(s(10, 10, 10, 10, 10, None)) == "brak sprzedaży w biurze w tym miesiącu"
    assert t(s(20, 20, 20, 5, None, 5)).startswith("słabszy bieżący miesiąc")  # miesiąc bez sprzedaży przerywa serię
