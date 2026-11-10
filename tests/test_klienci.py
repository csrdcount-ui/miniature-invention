"""Lejek sprzedaży: karta klienta, NIP do BOK, oferta, Mój dzień, alarm lejka, umowa z oferty."""
from datetime import date, timedelta

from app.db import SessionLocal
from app.models import Client, ClientOffer, Contract, NipCheck, User

from .conftest import login, post
from .test_app import PW, setup_company

NIP_A = "5260250274"  # poprawna suma kontrolna
NIP_B = "7740001454"


def _bok(client):
    login(client, "kris@firma.pl")
    post(client, "/zespol/nowa", "/zespol", {"imie": "Basia", "nazwisko": "Bok", "email": "basia@firma.pl",
                                              "haslo": PW, "rola": "bok", "menedzer": "", "udzial": "", "override": "", "baza": "narzut"})


def _klient(client, **over) -> int:
    data = {"nazwa": "Wózki Widłowe Michalski", "nip": NIP_A, "telefon": "600100200", "zrodlo": "Polecenie", **over}
    r = post(client, "/klienci/nowy", "/klienci/nowy", data)
    assert r.status_code == 303, r.text
    return int(r.headers["location"].rsplit("/", 1)[1])


def test_handlowiec_zaczyna_od_dnia_bok_od_kolejki(client):
    setup_company(client)
    _bok(client)
    r = post(client, "/logowanie", "/logowanie", {"email": "hania@firma.pl", "haslo": PW})
    assert r.headers["location"] == "/dzien"
    r = post(client, "/logowanie", "/logowanie", {"email": "basia@firma.pl", "haslo": PW})
    assert r.headers["location"] == "/bok"
    r = post(client, "/logowanie", "/logowanie", {"email": "kris@firma.pl", "haslo": PW})
    assert r.headers["location"] == "/pulpit"


def test_karta_klienta_duplikat_nip_bez_szczegolow(client):
    setup_company(client)
    login(client, "hania@firma.pl")
    cid = _klient(client)
    page = client.get(f"/klienci/{cid}").text
    assert "Zimny lead" in page and "Pierwszy telefon" in page
    # ten sam NIP u kolegi: tylko komunikat, bez nazwiska opiekuna
    login(client, "olek@firma.pl")
    r = post(client, "/klienci/nowy", "/klienci/nowy", {"nazwa": "Inna nazwa", "nip": NIP_A})
    assert r.status_code == 400 and "NIP obsługuje już Twój kolega z biura. Zapytaj BOK o szczegóły." in r.text
    assert "Hania" not in r.text.split("<main", 1)[1].split("</main>")[0].replace("hania", "")
    # kolega nie widzi cudzej karty
    assert client.get(f"/klienci/{cid}").status_code == 404
    # zła suma kontrolna
    r = post(client, "/klienci/nowy", "/klienci/nowy", {"nazwa": "Firma", "nip": "1234567890"})
    assert r.status_code == 400 and "sumę kontrolną" in r.text


def test_nip_do_bok_tylko_wskazane_spolki_i_odpowiedz(client):
    setup_company(client)
    _bok(client)
    login(client, "hania@firma.pl")
    cid = _klient(client)
    r = post(client, f"/klienci/{cid}", f"/klienci/{cid}/bok", {"spolka": "2"})
    assert r.status_code == 303
    with SessionLocal() as db:
        checks = db.query(NipCheck).all()
        assert [(k.supplier_id, k.result) for k in checks] == [(2, "do_sprawdzenia")]
        kid = checks[0].id
    login(client, "basia@firma.pl")
    page = client.get("/bok").text
    assert "Do sprawdzenia: 1" in page and "Wózki Widłowe Michalski" in page and "Spółka B: wpisz wynik" in page
    assert "Spółka A: wpisz wynik" not in page  # BOK sprawdza tylko wskazane
    until = (date.today() + timedelta(days=5)).isoformat()
    r = post(client, "/bok", f"/bok/{kid}", {"wynik": "zarezerwowany", "do": until, "uwagi": "Rezerwacja przez portal"})
    assert r.status_code == 303
    assert "Do sprawdzenia: 0" in client.get("/bok").text
    login(client, "hania@firma.pl")
    page = client.get("/dzien").text
    assert "Od BOK" in page and "wolny, zarezerwowany dla nas" in page
    assert "rezerwacja wygasa" in page  # 5 dni: ostrzeżenie w Pilne
    # handlowiec nie ma dostępu do kolejki BOK
    assert client.get("/bok").status_code == 403


def test_oferta_tylko_w_spolce_z_rezerwacja_i_telefon_po_3_dniach(client):
    setup_company(client)
    _bok(client)
    login(client, "hania@firma.pl")
    cid = _klient(client)
    offer = {"spolka": "1", "produkt": "fix", "medium": "energia", "cena_bazowa": "500", "marza": "100",
             "wolumen": "200", "okres": "24", "wyslana": (date.today() - timedelta(days=4)).isoformat()}
    r = post(client, f"/klienci/{cid}", f"/klienci/{cid}/oferta", offer)
    assert r.status_code == 400 and "nie masz potwierdzonej rezerwacji" in r.text
    post(client, f"/klienci/{cid}", f"/klienci/{cid}/bok", {"spolka": "1"})
    login(client, "basia@firma.pl")
    with SessionLocal() as db:
        kid = db.query(NipCheck).one().id
    post(client, "/bok", f"/bok/{kid}", {"wynik": "zarezerwowany", "do": (date.today() + timedelta(days=60)).isoformat()})
    login(client, "hania@firma.pl")
    r = post(client, f"/klienci/{cid}", f"/klienci/{cid}/oferta", {**offer, "marza": "250"})
    assert r.status_code == 400 and "przekracza limit" in r.text  # limit spółki A: 200
    r = post(client, f"/klienci/{cid}", f"/klienci/{cid}/oferta", offer)
    assert r.status_code == 303
    with SessionLocal() as db:
        c = db.get(Client, cid)
        o = db.query(ClientOffer).one()
        assert c.stage == "oferta" and o.valid_until == o.sent_date + timedelta(days=7)
        assert c.next_step_date == o.sent_date + timedelta(days=3)
    page = client.get("/dzien").text
    assert "zadzwoń w sprawie oferty" in page and "wysłana 4 dni temu" in page
    # po telefonie przypomnienie znika
    post(client, f"/klienci/{cid}", f"/klienci/{cid}/dzialanie", {
        "rodzaj": "telefon", "wynik": "Klient analizuje, decyzja w piątek", "etap": "oferta",
        "krok": "Telefon: decyzja", "krok_data": (date.today() + timedelta(days=2)).isoformat()})
    assert "zadzwoń w sprawie oferty" not in client.get("/dzien").text
    # klient podpisał: umowa z oferty, klient na etapie „Umowa podpisana”
    with SessionLocal() as db:
        oid = db.query(ClientOffer).one().id
    page = client.get(f"/umowy/nowa?klient={cid}&oferta={oid}").text
    assert 'value="Wózki Widłowe Michalski"' in page and 'name="oferta_id"' in page
    r = post(client, f"/umowy/nowa?klient={cid}&oferta={oid}", "/umowy/nowa", {
        "klient": "Wózki Widłowe Michalski", "nip": NIP_A, "spolka": "1", "medium": "energia", "produkt": "fix",
        "podpisana": date.today().isoformat(), "start": "", "okres": "24", "wolumen": "200", "cena_bazowa": "500",
        "narzut": "100", "status": "Umowa podpisana", "klient_id": str(cid), "oferta_id": str(oid)})
    assert r.status_code == 303, r.text
    with SessionLocal() as db:
        assert db.get(Client, cid).stage == "wygrana"
        assert db.get(ClientOffer, oid).status == "przyjeta"
        assert db.query(Contract).count() == 1


def test_alarm_malego_lejka_i_lejek_zespolu_u_menedzera(client):
    setup_company(client)
    login(client, "hania@firma.pl")
    page = client.get("/dzien").text
    assert "Za mało klientów w toku: 0" in page
    for i, nip in enumerate([NIP_A, NIP_B, ""]):
        cid = _klient(client, nazwa=f"Firma {i}", nip=nip)
        post(client, f"/klienci/{cid}", f"/klienci/{cid}/dzialanie", {
            "rodzaj": "telefon", "wynik": "Rozmowa", "etap": "kontakt", "krok": "Telefon",
            "krok_data": date.today().isoformat()})
    page = client.get("/dzien").text
    assert "Za mało klientów w toku" not in page and "Dziś (3)" in page
    login(client, "marek@firma.pl")
    page = client.get("/dzien").text
    assert "Lejek zespołu: 3 w toku" in page and "Hania Handlowiec" in page


def test_przegrana_wymaga_powodu_i_krok_wymagany_w_toku(client):
    setup_company(client)
    login(client, "hania@firma.pl")
    cid = _klient(client)
    r = post(client, f"/klienci/{cid}", f"/klienci/{cid}/dzialanie", {"rodzaj": "telefon", "wynik": "x", "etap": "kontakt", "krok": "", "krok_data": ""})
    assert r.status_code == 400 and "następny krok z datą" in r.text
    r = post(client, f"/klienci/{cid}", f"/klienci/{cid}/dzialanie", {"rodzaj": "telefon", "wynik": "Nie", "etap": "przegrana", "powod": ""})
    assert r.status_code == 400 and "powód" in r.text
    r = post(client, f"/klienci/{cid}", f"/klienci/{cid}/dzialanie", {"rodzaj": "telefon", "wynik": "Nie", "etap": "przegrana", "powod": "Cena"})
    assert r.status_code == 303
    with SessionLocal() as db:
        c = db.get(Client, cid)
        assert c.stage == "przegrana" and c.lost_reason == "Cena" and c.next_step_date is None


def test_listy_wymagan_edytuje_wlasciciel(client):
    setup_company(client)
    login(client, "kris@firma.pl")
    assert "Faktury dystrybucyjne (zawsze)" in client.get("/konto/listy").text
    r = post(client, "/konto/listy", "/konto/listy", {"oferta": "Faktura\nZużycie roczne", "umowa": "Faktury"})
    assert r.status_code == 303
    login(client, "hania@firma.pl")
    assert client.get("/konto/listy").status_code == 403
    cid = _klient(client)
    page = client.get(f"/klienci/{cid}").text
    assert "<li>Zużycie roczne</li>" in page and "Brak potwierdzonej rezerwacji" in page
