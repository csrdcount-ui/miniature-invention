"""Testy przepływu: właściciel ustawia reguły, ludzie sprzedają, każdy widzi tylko swoje."""
import re

from app.db import SessionLocal
from app.models import Contract

from .conftest import login, post

PW = "haslo-testowe-123"


def setup_company(client):
    # pierwsze uruchomienie: konto właściciela
    r = client.get("/logowanie", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/start"
    r = post(client, "/start", "/start", {"firma": "Kris Energia sp. z o.o.", "imie": "Kris", "nazwisko": "Właściciel", "email": "kris@firma.pl", "haslo": PW})
    assert r.status_code == 303

    # dwie spółki z różnymi warunkami
    post(client, "/spolki/nowa", "/spolki", {"nazwa": "Spółka A"})
    post(client, "/spolki/nowa", "/spolki", {"nazwa": "Spółka B"})
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
    r = post(client, "/zespol/nowa", "/zespol", {
        "imie": "Marek", "nazwisko": "Menedżer", "email": "marek@firma.pl", "haslo": PW, "rola": "menedzer",
        "menedzer": "", "udzial": "45", "override": "5", "baza": "narzut",
    })
    assert r.status_code == 303, r.text
    post(client, "/zespol/nowa", "/zespol", {
        "imie": "Hania", "nazwisko": "Handlowiec", "email": "hania@firma.pl", "haslo": PW, "rola": "handlowiec",
        "menedzer": "2", "udzial": "40", "override": "", "baza": "narzut",
    })
    post(client, "/zespol/nowa", "/zespol", {
        "imie": "Olek", "nazwisko": "Obcy", "email": "olek@firma.pl", "haslo": PW, "rola": "handlowiec",
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
    post(client, "/spolki/nowa", "/spolki", {"nazwa": "Spółka C"})
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


# --------------------------------------------------------------------------
# Nawigacja: zakładki główne, podsekcje, osobne strony formularzy
# --------------------------------------------------------------------------

def _menu(html: str) -> str:
    start = html.index('aria-label="Menu główne"')
    return html[start:html.index("</nav>", start)]


def test_zakladki_wlasciciela(client):
    setup_company(client)
    login(client, "kris@firma.pl")
    menu = _menu(client.get("/pulpit").text)
    for label in ["Portfel", "Spółki", "Zespół", "Raporty", "Konto"]:
        assert f"<span>{label}</span>" in menu, label
    # stare, długie menu zniknęło z każdej strony
    html = client.get("/pulpit").text
    assert "Zalogowano:" not in html
    assert 'action="/wyloguj"' not in html


def test_zakladki_handlowca_bez_spolek_i_zespolu(client):
    setup_company(client)
    login(client, "hania@firma.pl")
    menu = _menu(client.get("/pulpit").text)
    assert "<span>Portfel</span>" in menu and "<span>Konto</span>" in menu
    assert "<span>Spółki</span>" not in menu and "<span>Zespół</span>" not in menu


def test_biezaca_zakladka_i_podsekcja(client):
    setup_company(client)
    login(client, "kris@firma.pl")
    html = client.get("/umowy/nowa").text
    menu = _menu(html)
    assert re.search(r'href="/pulpit" aria-current="page"', menu)
    assert menu.count('aria-current="page"') == 1
    # podsekcja: wygrywa najdłuższe dopasowanie, tylko „Nowa umowa” jest bieżąca
    assert '<a href="/umowy/nowa" aria-current="page">Nowa umowa</a>' in html
    assert '<a href="/umowy">Umowy</a>' in html
    html = client.get("/zespol/2").text
    assert re.search(r'href="/zespol" aria-current="page"', _menu(html))


def test_konto_ma_wylogowanie_i_haslo(client):
    setup_company(client)
    login(client, "hania@firma.pl")
    r = client.get("/konto")
    assert r.status_code == 200
    assert "hania@firma.pl" in r.text and 'action="/wyloguj"' in r.text and 'href="/haslo"' in r.text
    r = post(client, "/konto", "/wyloguj", {})
    assert r.status_code == 303
    assert client.get("/pulpit", follow_redirects=False).headers["location"] == "/logowanie"


def test_formularze_na_osobnych_stronach(client):
    setup_company(client)
    login(client, "kris@firma.pl")
    assert 'action="/spolki"' not in client.get("/spolki").text
    assert 'action="/zespol"' not in client.get("/zespol").text
    assert 'action="/spolki"' in client.get("/spolki/nowa").text
    assert 'action="/zespol"' in client.get("/zespol/nowa").text
    assert client.get("/raporty").status_code == 200
    # błąd wraca na stronę formularza z komunikatem i wpisanymi danymi
    r = post(client, "/spolki/nowa", "/spolki", {"nazwa": "Spółka A"})
    assert r.status_code == 400 and "już istnieje" in r.text and 'role="alert"' in r.text
    r = post(client, "/zespol/nowa", "/zespol", {"imie": "Ala", "nazwisko": "Nowa", "email": "", "haslo": "x", "rola": "handlowiec", "udzial": "10"})
    assert r.status_code == 400 and 'value="Ala"' in r.text and 'value="Nowa"' in r.text


def test_formularze_tylko_dla_wlasciciela(client):
    setup_company(client)
    login(client, "marek@firma.pl")
    assert client.get("/spolki/nowa").status_code == 403
    assert client.get("/zespol/nowa").status_code == 403


# --------------------------------------------------------------------------
# Imię i nazwisko osobno, nazwa firmy w belce, uzupełnianie danych
# --------------------------------------------------------------------------

def test_nazwa_firmy_w_belce_i_tytule(client):
    setup_company(client)
    login(client, "kris@firma.pl")
    html = client.get("/zespol").text
    assert '<p class="marka-nazwa">Kris Energia sp. z o.o.<span class="sekcja">: Zespół</span></p>' in html
    assert "<title>Zespół i stawki – Kris Energia sp. z o.o.</title>" in html
    # handlowiec widzi tę samą nazwę firmy
    login(client, "hania@firma.pl")
    assert "Kris Energia sp. z o.o.<span" in client.get("/pulpit").text


def test_start_wymaga_firmy_imienia_i_nazwiska(client):
    base = {"email": "a@firma.pl", "haslo": PW}
    r = post(client, "/start", "/start", {**base, "firma": "", "imie": "Kris", "nazwisko": "Nowak"})
    assert r.status_code == 400 and "pełną nazwę firmy" in r.text
    r = post(client, "/start", "/start", {**base, "firma": "Firma X sp. z o.o.", "imie": "Kris", "nazwisko": ""})
    assert r.status_code == 400 and "Podaj nazwisko" in r.text
    r = post(client, "/start", "/start", {**base, "firma": "Firma X sp. z o.o.", "imie": "Kris", "nazwisko": "Nowak"})
    assert r.status_code == 303


def test_samo_imie_nie_przechodzi_przy_dodawaniu_osoby(client):
    setup_company(client)
    login(client, "kris@firma.pl")
    r = post(client, "/zespol/nowa", "/zespol", {"imie": "Anna", "nazwisko": "", "email": "anna@firma.pl", "haslo": PW, "rola": "handlowiec", "udzial": "10"})
    assert r.status_code == 400 and "Podaj nazwisko" in r.text


def test_lista_zespolu_sortowana_po_nazwisku(client):
    setup_company(client)
    login(client, "kris@firma.pl")
    html = client.get("/zespol").text
    # handlowcy: Handlowiec (Hania) przed Obcy (Olek)
    assert html.index("Hania Handlowiec") < html.index("Olek Obcy")


def _stare_konto_bez_podzialu(email: str, full: str, role: str = "wlasciciel"):
    """Symuluje konto sprzed podziału: tylko kolumna name."""
    from app.models import User
    from app.security import hash_password
    with SessionLocal() as db:
        db.add(User(email=email, name=full, first_name="", last_name="", password_hash=hash_password(PW), role=role))
        db.commit()


def test_migracja_rozdziela_stare_nazwy(client):
    from app import migrate
    from app.db import engine
    from app.models import User
    _stare_konto_bez_podzialu("boss@firma.pl", "Jan Maria Kowalski")
    _stare_konto_bez_podzialu("solo@firma.pl", "Boss01", role="handlowiec")
    migrate.run(engine)
    migrate.run(engine)  # drugi raz nic nie psuje
    with SessionLocal() as db:
        jan = db.query(User).filter_by(email="boss@firma.pl").one()
        assert (jan.first_name, jan.last_name, jan.name) == ("Jan Maria", "Kowalski", "Jan Maria Kowalski")
        solo = db.query(User).filter_by(email="solo@firma.pl").one()
        assert (solo.first_name, solo.last_name) == ("Boss01", "")
        assert solo.needs_last_name


def test_wlasciciel_bez_firmy_i_nazwiska_musi_uzupelnic(client):
    # stan jak na produkcji: konto Boss01, brak nazwy firmy
    _stare_konto_bez_podzialu("boss@firma.pl", "Boss01")
    from app import migrate
    from app.db import engine
    migrate.run(engine)
    login(client, "boss@firma.pl")
    for url in ["/pulpit", "/zespol", "/konto"]:
        r = client.get(url, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/konto/dane", url
    page = client.get("/konto/dane").text
    assert "Uzupełnij dane" in page and 'name="firma"' in page and 'action="/wyloguj"' in page
    r = post(client, "/konto/dane", "/konto/dane", {"firma": "Energia Lublin sp. z o.o.", "imie": "Boss01", "nazwisko": ""})
    assert r.status_code == 400 and "Podaj nazwisko" in r.text
    r = post(client, "/konto/dane", "/konto/dane", {"firma": "Energia Lublin sp. z o.o.", "imie": "Krystyna", "nazwisko": "Nowak"})
    assert r.status_code == 303
    html = client.get("/pulpit").text
    assert "Energia Lublin sp. z o.o.<span" in html
    assert "Nowak" in client.get("/konto").text


def test_handlowiec_bez_nazwiska_uzupelnia_tylko_swoje_dane(client):
    setup_company(client)
    _stare_konto_bez_podzialu("solo@firma.pl", "Solo", role="handlowiec")
    from app import migrate
    from app.db import engine
    migrate.run(engine)
    login(client, "solo@firma.pl")
    assert client.get("/pulpit", follow_redirects=False).headers["location"] == "/konto/dane"
    page = client.get("/konto/dane").text
    assert 'name="firma"' not in page
    r = post(client, "/konto/dane", "/konto/dane", {"imie": "Solo", "nazwisko": "Sprzedawca", "firma": "Próba przejęcia"})
    assert r.status_code == 303
    assert client.get("/pulpit").status_code == 200
    # nazwa firmy bez zmian — handlowiec nie może jej zmienić
    assert "Kris Energia sp. z o.o.<span" in client.get("/pulpit").text


def test_wlasciciel_poprawia_nazwisko_osoby(client):
    setup_company(client)
    login(client, "kris@firma.pl")
    r = post(client, "/zespol/3", "/zespol/3", {"imie": "Hanna", "nazwisko": "Handlowiec-Nowak", "menedzer": "2", "aktywny": "1"})
    assert r.status_code == 303
    assert "Hanna Handlowiec-Nowak" in client.get("/zespol").text


# --------------------------------------------------------------------------
# Historia statusów umów
# --------------------------------------------------------------------------

def _umowa_hani(client) -> str:
    setup_company(client)
    login(client, "hania@firma.pl")
    r = post(client, "/umowy/nowa", "/umowy/nowa", CONTRACT)
    return r.headers["location"].rsplit("/", 1)[1]


def _events(cid):
    from app.models import ContractStatusEvent
    with SessionLocal() as db:
        return [
            (e.from_status, e.to_status, e.effective_date.isoformat(), e.note, e.baseline)
            for e in db.query(ContractStatusEvent).filter_by(contract_id=int(cid)).order_by(ContractStatusEvent.id)
        ]


def test_nowa_umowa_zapisuje_pierwszy_wpis_historii(client):
    from datetime import date
    cid = _umowa_hani(client)
    ev = _events(cid)
    assert ev == [(None, "Umowa podpisana", "2026-10-01", "Umowa wpisana do systemu.", False)]  # data podpisania
    page = client.get(f"/umowy/{cid}").text
    assert "<h2>Historia statusów</h2>" in page and "Wpisał(a): Hania Handlowiec" in page


def test_zmiana_statusu_z_data_i_notatka(client):
    cid = _umowa_hani(client)
    r = post(client, f"/umowy/{cid}", f"/umowy/{cid}/status",
             {"status": "Weryfikacja spółki", "data": "2026-10-03", "notatka": "Wysłane do spółki."})
    assert r.status_code == 303
    assert _events(cid)[-1] == ("Umowa podpisana", "Weryfikacja spółki", "2026-10-03", "Wysłane do spółki.", False)
    page = client.get(f"/umowy/{cid}").text
    assert "Obecny status: <strong>Weryfikacja spółki</strong>, od 03.10.2026" in page
    assert "Umowa podpisana → Weryfikacja spółki" in page


def test_bledne_zmiany_statusu_nic_nie_zapisuja(client):
    from datetime import date, timedelta
    cid = _umowa_hani(client)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    cases = [
        ({"status": "Umowa podpisana"}, "ma już status"),
        ({"status": "Zerwana", "notatka": ""}, "podaj powód"),
        ({"status": "Start dostaw", "data": tomorrow}, "z przyszłości"),
        ({"status": "Start dostaw", "data": "2001-01-01"}, "lat wstecz"),
        ({"status": "Nieznany"}, "Niepoprawny status"),
    ]
    for data, msg in cases:
        r = post(client, f"/umowy/{cid}", f"/umowy/{cid}/status", data)
        assert r.status_code == 400 and msg in r.text, (data, r.status_code)
    assert len(_events(cid)) == 1
    with SessionLocal() as db:
        assert db.get(Contract, int(cid)).status == "Umowa podpisana"


def test_zerwanie_z_powodem(client):
    cid = _umowa_hani(client)
    r = post(client, f"/umowy/{cid}", f"/umowy/{cid}/status",
             {"status": "Zerwana", "notatka": "Klient przeszedł do innego sprzedawcy."})
    assert r.status_code == 303
    assert _events(cid)[-1][1:2] == ("Zerwana",)
    assert "Klient przeszedł do innego sprzedawcy." in client.get(f"/umowy/{cid}").text


def test_obcy_handlowiec_nie_zmieni_statusu(client):
    cid = _umowa_hani(client)
    login(client, "olek@firma.pl")
    r = post(client, "/umowy/nowa", f"/umowy/{cid}/status", {"status": "Start dostaw"})
    assert r.status_code == 404
    assert len(_events(cid)) == 1


def test_menedzer_zmienia_status_umowy_zespolu(client):
    cid = _umowa_hani(client)
    login(client, "marek@firma.pl")
    r = post(client, f"/umowy/{cid}", f"/umowy/{cid}/status", {"status": "Start dostaw"})
    assert r.status_code == 303
    login(client, "hania@firma.pl")
    assert "Wpisał(a): Marek Menedżer" in client.get(f"/umowy/{cid}").text


def test_migracja_dodaje_stan_poczatkowy_dla_starych_umow(client):
    from app import migrate
    from app.db import engine
    from app.models import ContractStatusEvent
    cid = _umowa_hani(client)
    with SessionLocal() as db:  # symulacja umowy sprzed włączenia historii
        db.query(ContractStatusEvent).delete()
        db.commit()
    migrate.run(engine)
    migrate.run(engine)  # drugi raz nie dubluje
    ev = _events(cid)
    assert len(ev) == 1 and ev[0][1] == "Umowa podpisana" and ev[0][4] is True
    page = client.get(f"/umowy/{cid}").text
    assert "co najmniej od" in page and "Wpis automatyczny." in page


def test_data_zmiany_nie_cofa_sie_przed_poprzednia(client):
    cid = _umowa_hani(client)
    post(client, f"/umowy/{cid}", f"/umowy/{cid}/status", {"status": "Weryfikacja spółki", "data": "2026-10-10"})
    r = post(client, f"/umowy/{cid}", f"/umowy/{cid}/status", {"status": "Start dostaw", "data": "2026-10-05"})
    assert r.status_code == 400 and "wcześniejsza niż poprzednia zmiana" in r.text
    r = post(client, f"/umowy/{cid}", f"/umowy/{cid}/status", {"status": "Start dostaw", "data": "2026-10-10"})
    assert r.status_code == 303
