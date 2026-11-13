"""Rejestr rozliczeń: wpływy od spółek, proporcje dla zespołu, korekty, poufność.

Przykład bazowy (Spółka A: broker 77%, transza 30%; Hania 40%; Marek override 5% narzutu):
100 MWh × 5 lat × 100 zł = 50 000 zł narzutu.
Broker 38 500, handlowiec 20 000, override 2 500, właściciel 16 000.
Pierwsza transza od spółki: 30% × 38 500 = 11 550
  → handlowiec 6 000, menedżer 750, właściciel 4 800.
"""
from datetime import date
from decimal import Decimal

from app import settlements as st
from app.db import SessionLocal
from app.models import Contract, PayoutEntry

from .conftest import login, post
from .test_app import CONTRACT, setup_company


def _contract_with_tranche(client, **contract_overrides):
    setup_company(client)
    login(client, "hania@firma.pl")
    r = post(client, "/umowy/nowa", "/umowy/nowa", {**CONTRACT, **contract_overrides})
    assert r.status_code == 303, r.text
    cid = int(r.headers["location"].rsplit("/", 1)[1])
    login(client, "kris@firma.pl")
    r = post(client, f"/umowy/{cid}", f"/umowy/{cid}/rozliczenia",
             {"rodzaj": "transza1", "data": "2026-11-02", "kwota": "11 550,00", "uwagi": "Zestawienie 10/2026"})
    assert r.status_code == 303, r.text
    return cid


def test_wplyw_dzielony_proporcjonalnie_i_status(client):
    cid = _contract_with_tranche(client)
    with SessionLocal() as db:
        e = db.query(PayoutEntry).one()
        assert e.broker_amount == Decimal("11550.00")
        assert e.trader_amount == Decimal("6000.00")
        assert e.override_amount == Decimal("750.00")
        assert e.owner_amount == Decimal("4800.00")
        assert db.get(Contract, cid).status == "Transza 1 wypłacona"


def test_poufnosc_rozliczen(client):
    cid = _contract_with_tranche(client)

    login(client, "hania@firma.pl")
    page = client.get(f"/umowy/{cid}").text
    assert "6 000,00 zł" in page
    assert "11 550" not in page and "4 800" not in page and "Zestawienie 10/2026" not in page
    assert "Dodaj wpływ" not in page
    reg = client.get("/rozliczenia").text
    assert "6 000,00 zł" in reg and "11 550" not in reg and "Marża właściciela" not in reg
    csv = client.get("/rozliczenia.csv").content.decode("utf-8-sig")
    assert "6000,00" in csv and "11550" not in csv and "4800" not in csv
    # handlowiec nie wpisze wpływu ani nie oznaczy wypłaty
    r = post(client, f"/umowy/{cid}", f"/umowy/{cid}/rozliczenia",
             {"rodzaj": "faktury", "data": "2026-11-02", "kwota": "100"})
    assert r.status_code == 403
    r = post(client, "/rozliczenia", "/rozliczenia/1/wyplata", {"komu": "handlowiec"})
    assert r.status_code == 403

    login(client, "marek@firma.pl")
    page = client.get(f"/umowy/{cid}").text
    assert "750,00 zł" in page and "6 000,00 zł" in page
    assert "11 550" not in page and "4 800" not in page

    login(client, "olek@firma.pl")
    assert "Piekarnia" not in client.get("/rozliczenia").text
    assert "Piekarnia" not in client.get("/rozliczenia.csv").content.decode("utf-8-sig")


def test_wyplata_dla_zespolu(client):
    cid = _contract_with_tranche(client)
    reg = client.get("/rozliczenia").text
    assert "Hania Handlowiec: 6 000,00 zł" in reg
    assert "Marek Menedżer: 750,00 zł" in reg

    r = post(client, "/rozliczenia", "/rozliczenia/1/wyplata", {"komu": "handlowiec", "wroc": "/rozliczenia"})
    assert r.status_code == 303 and r.headers["location"] == "/rozliczenia"
    reg = client.get("/rozliczenia").text
    assert "Hania Handlowiec: 6 000,00 zł" not in reg
    assert "Marek Menedżer: 750,00 zł" in reg

    # wpisu rozliczonego z zespołem nie da się usunąć
    r = post(client, f"/umowy/{cid}", "/rozliczenia/1/usun", {})
    assert r.status_code == 303
    with SessionLocal() as db:
        assert db.query(PayoutEntry).count() == 1

    # przekierowanie tylko wewnątrz aplikacji
    r = post(client, "/rozliczenia", "/rozliczenia/1/wyplata", {"komu": "menedzer", "wroc": "//zly.pl"})
    assert r.headers["location"].startswith("/umowy/")


def test_korekta_nie_wieksza_niz_wplywy_i_zerwanie(client):
    cid = _contract_with_tranche(client)
    r = post(client, f"/umowy/{cid}", f"/umowy/{cid}/rozliczenia",
             {"rodzaj": "korekta", "data": "2026-11-10", "kwota": "20000"})
    assert r.status_code == 400 and "większa niż suma" in r.text

    r = post(client, f"/umowy/{cid}", f"/umowy/{cid}/rozliczenia",
             {"rodzaj": "korekta", "data": "2026-11-10", "kwota": "3850", "zerwana": "1"})
    assert r.status_code == 303
    with SessionLocal() as db:
        e = db.query(PayoutEntry).filter_by(kind="korekta").one()
        assert e.broker_amount == Decimal("-3850.00")
        assert e.trader_amount == Decimal("-2000.00")
        assert e.override_amount == Decimal("-250.00")
        assert e.owner_amount == Decimal("-1600.00")
        assert db.get(Contract, cid).status == "Zerwana"


def test_usuniecie_blednego_wpisu(client):
    cid = _contract_with_tranche(client)
    r = post(client, f"/umowy/{cid}", "/rozliczenia/1/usun", {})
    assert r.status_code == 303
    with SessionLocal() as db:
        assert db.query(PayoutEntry).count() == 0


def test_zagrozone_korekta_i_sugestia(client):
    cid = _contract_with_tranche(client, start="2026-01-01")
    with SessionLocal() as db:
        c = db.get(Contract, cid)
        # rok dostaw z 5 lat = 20% umowy zarobione
        state = st.contract_state(c, date(2027, 1, 1))
        assert state["broker"].settled == Decimal("11550.00")
        assert state["broker"].remaining == Decimal("26950.00")
        assert state["broker"].at_risk == Decimal("3850.00")   # 11 550 − 20% × 38 500
        assert state["trader"].at_risk == Decimal("2000.00")   # 6 000 − 20% × 20 000
        assert state["trader"].to_pay == Decimal("6000.00")
        cb = st.suggested_clawback(c, date(2027, 1, 1))
        assert (cb.broker, cb.trader, cb.manager_override, cb.owner_margin) == (
            Decimal("3850.00"), Decimal("2000.00"), Decimal("250.00"), Decimal("1600.00"))
        # po 30% umowy transza jest już zarobiona
        assert st.contract_state(c, date(2027, 7, 1))["broker"].at_risk == Decimal(0)


def test_strony_rozliczen_renderuja_sie(client):
    cid = _contract_with_tranche(client)
    for who in ("kris@firma.pl", "marek@firma.pl", "hania@firma.pl", "olek@firma.pl"):
        login(client, who)
        for url in ("/pulpit", "/rozliczenia", "/rozliczenia.csv"):
            assert client.get(url).status_code == 200, (who, url)
    login(client, "kris@firma.pl")
    assert client.get(f"/umowy/{cid}").status_code == 200


def test_miesiace_dostaw():
    assert st.months_elapsed(None, date(2027, 1, 1), 60) == 0
    assert st.months_elapsed(date(2026, 1, 15), date(2026, 2, 14), 60) == 0
    assert st.months_elapsed(date(2026, 1, 15), date(2026, 2, 15), 60) == 1
    assert st.months_elapsed(date(2026, 1, 1), date(2040, 1, 1), 60) == 60
    assert st.months_elapsed(date(2027, 1, 1), date(2026, 1, 1), 60) == 0
