"""Testy przepływu: właściciel ustawia reguły, ludzie sprzedają, każdy widzi tylko swoje."""
from app.db import SessionLocal
from app.models import Contract

from .conftest import login, post

PW = "haslo-testowe-123"


def setup_company(client):
    # pierwsze uruchomienie: konto właściciela
    r = client.get("/logowanie", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/start"
    r = post(client, "/start", "/start", {"imie": "Kris Właściciel", "email": "kris@firma.pl", "haslo": PW})
    assert r.status_code == 303

    # dwie spółki z różnymi warunkami
    post(client, "/spolki", "/spolki", {"nazwa": "Spółka A"})
    post(client, "/spolki", "/spolki", {"nazwa": "Spółka B"})
    r = post(client, "/spolki/1", "/spolki/1/reguly", {
        "od": "2020-01-01", "udzial": "77", "transza": "30", "wyzwalacz": "weryfikacja",
        "limit": "200", "nowe_msc": "12", "korekta": "proporcjonalna",
    })
    assert r.status_code == 303, r.text
    r = post(client, "/spolki/2", "/spolki/2/reguly", {
        "od": "2020-01-01", "udzial": "70,5", "transza": "50", "wyzwalacz": "start_dostaw",
        "limit": "", "nowe_msc": "12", "korekta": "proporcjonalna",
    })
    assert r.status_code == 303, r.text

    # menedżer i dwóch handlowców (jeden w zespole, drugi poza)
    r = post(client, "/zespol", "/zespol", {
        "imie": "Marek Menedżer", "email": "marek@firma.pl", "haslo": PW, "rola": "menedzer",
        "menedzer": "", "udzial": "45", "override": "5", "baza": "narzut",
    })
    assert r.status_code == 303, r.text
    post(client, "/zespol", "/zespol", {
        "imie": "Hania Handlowiec", "email": "hania@firma.pl", "haslo": PW, "rola": "handlowiec",
        "menedzer": "2", "udzial": "40", "override": "", "baza": "narzut",
    })
    post(client, "/zespol", "/zespol", {
        "imie": "Olek Obcy", "email": "olek@firma.pl", "haslo": PW, "rola": "handlowiec",
        "menedzer": "", "udzial": "35", "override": "", "baza": "narzut",
    })


CONTRACT = {
    "klient": "Piekarnia Kowalski", "nip": "", "spolka": "1", "medium": "energia",
    "podpisana": "2026-10-01", "start": "", "okres": "60", "wolumen": "100",
    "cena_bazowa": "500", "narzut": "100", "status": "Umowa podpisana",
}


def test_pelny_przeplyw_i_poufnosc(client):
    setup_company(client)

    # Hania zapisuje umowę sama
    login(client, "hania@firma.pl")
    r = post(client, "/umowy/nowa", "/umowy/nowa", CONTRACT)
    assert r.status_code == 303, r.text
    cid = r.headers["location"].rsplit("/", 1)[1]
    page = client.get(f"/umowy/{cid}").text
    assert "Twoja prowizja" in page
    assert "20 000,00 zł" in page  # 40% z 50 000
    assert "6 000,00 zł" in page  # transza 30% spółki A
    assert "600,00 zł/MWh" in page  # cena dla klienta
    # poufne: udział brokera (38 500), marża właściciela, procent spółki
    assert "38 500" not in page
    assert "Marża właściciela" not in page
    assert "77%" not in page
    assert "Udział brokera" not in page
    assert client.get("/spolki").status_code == 403
    assert client.get("/zespol").status_code == 403

    # Menedżer widzi umowę zespołu, prowizję Hani i swój override, ale nie warunki spółki
    login(client, "marek@firma.pl")
    page = client.get(f"/umowy/{cid}").text
    assert "Prowizja handlowca: Hania Handlowiec" in page
    assert "Twój override" in page
    assert "2 500,00 zł" in page  # 5% z 50 000
    assert "38 500" not in page and "Marża właściciela" not in page and "77%" not in page
    assert client.get("/spolki/1").status_code == 403

    # Handlowiec spoza zespołu nie widzi cudzej umowy (404, nie zdradzamy istnienia)
    login(client, "olek@firma.pl")
    assert client.get(f"/umowy/{cid}").status_code == 404
    assert "Piekarnia" not in client.get("/umowy").text

    # Właściciel widzi wszystko
    login(client, "kris@firma.pl")
    page = client.get(f"/umowy/{cid}").text
    assert "Spółka obrotu → broker" in page
    assert "38 500,00 zł" in page
    assert "Marża właściciela" in page
    assert "16 000,00 zł" in page  # 38 500 − 20 000 − 2 500


def test_zmiana_regul_nie_zmienia_starych_umow(client):
    setup_company(client)
    login(client, "hania@firma.pl")
    r = post(client, "/umowy/nowa", "/umowy/nowa", CONTRACT)
    cid = int(r.headers["location"].rsplit("/", 1)[1])

    login(client, "kris@firma.pl")
    post(client, "/spolki/1", "/spolki/1/reguly", {
        "od": "2026-10-15", "udzial": "65", "transza": "50", "wyzwalacz": "weryfikacja",
        "limit": "200", "nowe_msc": "12", "korekta": "proporcjonalna",
    })
    post(client, "/zespol/3", "/zespol/3/stawki", {"od": "2026-10-15", "udzial": "30"})

    with SessionLocal() as db:
        c = db.get(Contract, cid)
        assert str(c.broker_share_pct).startswith("77")
        assert str(c.trader_share_pct).startswith("40")

    # nowa umowa po zmianie dostaje nowe reguły
    login(client, "hania@firma.pl")
    r = post(client, "/umowy/nowa", "/umowy/nowa", {**CONTRACT, "podpisana": "2026-11-01"})
    cid2 = int(r.headers["location"].rsplit("/", 1)[1])
    with SessionLocal() as db:
        c2 = db.get(Contract, cid2)
        assert str(c2.broker_share_pct).startswith("65")
        assert str(c2.trader_share_pct).startswith("30")


def test_limit_narzutu_spolki(client):
    setup_company(client)
    login(client, "hania@firma.pl")
    r = post(client, "/umowy/nowa", "/umowy/nowa", {**CONTRACT, "narzut": "250"})
    assert r.status_code == 400
    assert "przekracza limit" in r.text
    # spółka B nie ma limitu
    r = post(client, "/umowy/nowa", "/umowy/nowa", {**CONTRACT, "spolka": "2", "narzut": "250"})
    assert r.status_code == 303


def test_handlowiec_nie_przypisze_umowy_innemu(client):
    setup_company(client)
    login(client, "hania@firma.pl")
    r = post(client, "/umowy/nowa", "/umowy/nowa", {**CONTRACT, "handlowiec": "4"})
    assert r.status_code == 400


def test_brak_regul_blokuje_umowe(client):
    setup_company(client)
    post(client, "/spolki", "/spolki", {"nazwa": "Spółka C"})
    login(client, "hania@firma.pl")
    r = post(client, "/umowy/nowa", "/umowy/nowa", {**CONTRACT, "spolka": "3"})
    assert r.status_code == 400
    assert "nie ma reguł" in r.text


def test_csrf_wymagany(client):
    setup_company(client)
    login(client, "hania@firma.pl")
    r = client.post("/umowy/nowa", data=CONTRACT, follow_redirects=False)
    assert r.status_code == 400


def test_bledne_haslo(client):
    setup_company(client)
    client.cookies.clear()
    r = post(client, "/logowanie", "/logowanie", {"email": "hania@firma.pl", "haslo": "zle"})
    assert r.status_code == 401


def test_niezalogowany_przekierowany(client):
    setup_company(client)
    client.cookies.clear()
    r = client.get("/umowy", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/logowanie"


def test_strony_renderuja_sie(client):
    setup_company(client)
    login(client, "hania@firma.pl")
    post(client, "/umowy/nowa", "/umowy/nowa", {**CONTRACT, "nowe_przylacze": "1"})
    login(client, "kris@firma.pl")
    for url in ["/pulpit", "/umowy", "/umowy/nowa", "/umowy/1", "/spolki", "/spolki/1", "/zespol", "/zespol/2", "/haslo"]:
        r = client.get(url)
        assert r.status_code == 200, url
        assert 'lang="pl"' in r.text
