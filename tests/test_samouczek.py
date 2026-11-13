"""Samouczek: kroki każdej roli prowadzą do działających ekranów, postęp, testowy NIP, zaproszenie, uwagi.

Najważniejszy test przechodzi proces handlowca z samouczka na prawdziwej aplikacji krok po kroku:
jeśli ekran albo pole się zmieni, samouczek przestanie być prawdziwy i test to pokaże.
"""
import re
from datetime import date, timedelta
from decimal import Decimal as D

from app import pipeline as pl
from app import samouczek as sm
from app.db import SessionLocal
from app.models import Client, Feedback, InvoiceReading, MeteringPoint, NipCheck, TutorialProgress, User

from .conftest import login, post
from .test_app import PW, setup_company
from .test_klienci import _bok

ROLE_USERS = {"wlasciciel": "kris@firma.pl", "menedzer": "marek@firma.pl", "handlowiec": "hania@firma.pl", "bok": "basia@firma.pl"}


def _setup(client):
    setup_company(client)
    _bok(client)


def test_nip_testowy_poprawny_i_rozny_dla_kazdego(client):
    _setup(client)
    with SessionLocal() as db:
        nips = {u.email: sm.test_nip(db, u) for u in db.query(User)}
    assert len(set(nips.values())) == len(nips)
    for nip in nips.values():
        assert len(nip) == 10 and pl.valid_nip(nip), nip
    with SessionLocal() as db:  # stały dla osoby
        u = db.query(User).filter_by(email="hania@firma.pl").one()
        assert sm.test_nip(db, u) == nips["hania@firma.pl"]


def test_kazdy_link_z_samouczka_dziala_dla_swojej_roli(client):
    _setup(client)
    for role, email in ROLE_USERS.items():
        login(client, email)
        page = client.get("/samouczek")
        assert page.status_code == 200 and "Samouczek" in page.text, role
        with SessionLocal() as db:
            user = db.query(User).filter_by(email=email).one()
            urls = {s["url"] for sec in sm.sections_for(user) for s in sec["steps"] if s["url"]}
        assert urls
        for url in sorted(urls):
            r = client.get(url, follow_redirects=True)
            assert r.status_code == 200, (role, url, r.status_code)


def test_postep_zaproszenie_i_cudze_kroki(client):
    _setup(client)
    login(client, "hania@firma.pl")
    assert "Pierwszy raz w platformie?" in client.get("/dzien").text
    assert "Pierwszy raz w platformie?" not in client.get("/samouczek").text  # na samej stronie samouczka nie dubluje
    r = post(client, "/dzien", "/samouczek/krok", {"krok": "h-lead", "zrobione": "1"})
    assert r.status_code == 303 and r.headers["location"] == "/samouczek#krok-h-lead"
    page = client.get("/samouczek").text
    assert "Zrobione 1 z" in page and "(zrobione)" in page and "Cofnij:" in page
    assert "Pierwszy raz w platformie?" not in client.get("/dzien").text  # po pierwszym kroku zaproszenie znika
    r = post(client, "/samouczek", "/samouczek/krok", {"krok": "h-lead", "zrobione": "0"})
    assert "Zrobione 0 z" in client.get("/samouczek").text
    # krok z innej roli (BOK) odrzucony
    r = post(client, "/samouczek", "/samouczek/krok", {"krok": "b-nip", "zrobione": "1"})
    assert r.status_code == 400
    # „Nie teraz” chowa zaproszenie i wraca na tę samą stronę, nie na obcy adres
    login(client, "olek@firma.pl")
    assert "Pierwszy raz w platformie?" in client.get("/klienci").text
    r = post(client, "/klienci", "/samouczek/ukryj", {"wroc": "//zly.example/x"})
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert "Pierwszy raz w platformie?" not in client.get("/klienci").text


def test_kazda_rola_widzi_swoje_kroki_a_wlasciciel_tez_kroki_bok(client):
    _setup(client)
    login(client, "kris@firma.pl")
    page = client.get("/samouczek").text
    assert "Zagraj BOK" in page and "Odpowiedz na NIP" in page and "Reguły spółek" in page and "Twój NIP testowy" in page
    login(client, "hania@firma.pl")
    page = client.get("/samouczek").text
    assert "Dodaj klienta testowego" in page and "Odpowiedz na NIP" not in page and "Reguły spółek" not in page
    login(client, "marek@firma.pl")
    assert "Przeczytaj zespół" in client.get("/samouczek").text
    login(client, "basia@firma.pl")
    page = client.get("/samouczek").text
    assert "Pobierz i zarchiwizuj faktury" in page and "Twój NIP testowy" not in page  # BOK nie zakłada klientów


def test_uwagi_zapis_lista_i_uprawnienia(client):
    _setup(client)
    login(client, "hania@firma.pl")
    page = client.get("/klienci").text
    assert "Zgłoś uwagę do tej strony" in page and "/uwagi?strona=/klienci" in page
    assert 'name="strona" value="/klienci"' in client.get("/uwagi?strona=/klienci").text
    r = post(client, "/uwagi?strona=/klienci", "/uwagi", {"strona": "/klienci", "uwaga": "Nie widzę przycisku dodawania klienta."})
    assert r.status_code == 303 and r.headers["location"] == "/klienci"
    r = post(client, "/uwagi", "/uwagi", {"strona": "/klienci", "uwaga": "x"})
    assert r.status_code == 400 and "co najmniej kilka słów" in r.text
    r = post(client, "/uwagi", "/uwagi", {"strona": "https://zly.example/", "uwaga": "Adres z zewnątrz"})
    assert r.headers["location"] == "/"
    with SessionLocal() as db:
        rows = db.query(Feedback).order_by(Feedback.id).all()
        assert [f.url for f in rows] == ["/klienci", "/"] and rows[0].role == "handlowiec"
    assert client.get("/konto/uwagi").status_code == 403  # handlowiec nie czyta cudzych uwag
    login(client, "kris@firma.pl")
    page = client.get("/konto/uwagi").text
    assert "Nie widzę przycisku dodawania klienta." in page and "Hania Handlowiec" in page and "nowych 2" in page
    fid = rows[0].id
    r = post(client, "/konto/uwagi", f"/konto/uwagi/{fid}/status", {"status": "zalatwiona"})
    assert r.status_code == 303 and "nowych 1" in client.get("/konto/uwagi").text


def test_przejscie_samouczka_handlowca_krok_po_kroku(client):
    """Kroki z samouczka wykonane dokładnie tak, jak są opisane: NIP testowy, punkt, dwie faktury, NIP do BOK, odpowiedź BOK, oferta."""
    _setup(client)
    login(client, "hania@firma.pl")
    with SessionLocal() as db:
        nip = sm.test_nip(db, db.query(User).filter_by(email="hania@firma.pl").one())
    # h-lead: nazwa, telefon, NIP testowy, źródło
    r = post(client, "/klienci/nowy", "/klienci/nowy", {"nazwa": "TEST Hania Sp. z o.o.", "nip": nip, "telefon": "600100200", "zrodlo": "Polecenie"})
    assert r.status_code == 303, r.text
    cid = int(r.headers["location"].rsplit("/", 1)[1])
    page = client.get(f"/klienci/{cid}").text
    for etap in ("1. Kontakt", "2. Dane", "3. Teren", "4. Oferta i umowa"):
        assert etap in page
    # h-rozmowa
    r = post(client, f"/klienci/{cid}", f"/klienci/{cid}/dzialanie", {
        "rodzaj": "telefon", "wynik": "Rozmowa wstępna", "etap": "kontakt", "powod": "", "krok": "oddzwonić z ofertą",
        "krok_data": (date.today() + timedelta(days=1)).isoformat()})
    assert r.status_code == 303, r.text
    assert "oddzwonić z ofertą" in client.get(f"/klienci/{cid}").text
    # h-punkt: punkt poboru i dwie faktury dokładnie jak w opisie
    r = post(client, f"/klienci/{cid}", f"/klienci/{cid}/punkty", {
        "ppe": "PL0001", "adres": "", "grupa": "C11", "sprzedawca": "Obecna Energia",
        "koniec": (date.today() + timedelta(days=365)).isoformat(), "wypowiedzenie": "3"})
    assert r.status_code == 303
    with SessionLocal() as db:
        pid = db.query(MeteringPoint).one().id
    for od, do, l_od, l_do in (("2025-01-01", "2025-02-28", "10000", "12000"), ("2025-11-01", "2025-12-31", "28000", "30000")):
        r = post(client, f"/klienci/{cid}", f"/klienci/{cid}/punkty/{pid}/faktura",
                 {"punkt": str(pid), "od": od, "do": do, "licznik_od": l_od, "licznik_do": l_do, "zuzycie": ""})
        assert r.status_code == 303, r.text
    page = client.get(f"/klienci/{cid}").text
    assert "20,055" in page and "wypowiedzenie najpóźniej" in page  # „około 20,055 MWh” z opisu kroku
    # h-nip: dwie spółki do BOK
    r = post(client, f"/klienci/{cid}", f"/klienci/{cid}/bok", {"spolka": ["1", "2"]})
    assert r.status_code == 303
    page = client.get(f"/klienci/{cid}").text
    assert "czeka na bok" in page.lower()
    # BOK (rola grana przez właściciela albo BOK) odpowiada
    login(client, "kris@firma.pl")
    assert "NIP-y do sprawdzenia: 2" in client.get("/bok").text
    with SessionLocal() as db:
        k1 = db.query(NipCheck).order_by(NipCheck.id).first().id
    r = post(client, "/bok", f"/bok/{k1}", {"wynik": "zarezerwowany", "do": (date.today() + timedelta(days=30)).isoformat(), "uwagi": ""})
    assert r.status_code == 303
    # h-odp: handlowiec widzi odpowiedź w „Mój dzień”, w „Od BOK”
    login(client, "hania@firma.pl")
    dzien = client.get("/dzien").text
    assert "Od BOK" in dzien and "zarezerwowany" in dzien.lower()
    # h-kalk: wolumen i grupa z karty trafiają do kalkulatora; policz z ceną dla klienta
    page = client.get(f"/klienci/{cid}").text
    link = re.search(r'href="(/klienci/%d/kalkulator[^"]*)"' % cid, page).group(1).replace("&amp;", "&")
    assert "wolumen=20.055" in link and "grupa=C11" in link
    calc = client.get(f"{link}&start=2027-01&okres=36&cena_1=650&wszystkie=1")
    assert calc.status_code == 200 and "Audax" in calc.text or "Spółka A" in calc.text
    # h-oferta: w spółce, w której NIP jest wolny
    r = post(client, f"/klienci/{cid}", f"/klienci/{cid}/oferta", {
        "spolka": "1", "produkt": "fix", "medium": "energia", "cena_bazowa": "500", "marza": "100",
        "wolumen": "20,055", "okres": "36", "wyslana": date.today().isoformat(), "wazna_do": (date.today() + timedelta(days=7)).isoformat()})
    assert r.status_code == 303, r.text
    page = client.get(f"/klienci/{cid}").text
    assert "Klient podpisał: zapisz umowę" in page
    oid = re.search(r"/umowy/nowa\?klient=%d&(?:amp;)?oferta=(\d+)" % cid, page).group(1)
    assert client.get(f"/umowy/nowa?klient={cid}&oferta={oid}").status_code == 200  # h-umowa
