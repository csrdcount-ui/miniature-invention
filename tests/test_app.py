"""Testy przepływu: właściciel ustawia reguły, ludzie sprzedają, każdy widzi tylko swoje."""
import re

from app.db import SessionLocal
from app.models import Contract, User

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
    assert "Przychód spółki" not in page
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
    assert "38 500" not in page and "Przychód spółki" not in page and "77%" not in page
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
    assert "Przychód spółki" in page
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
    assert "Historia statusów (" in page and "Wpisał(a): Hania Handlowiec" in page


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


# --------------------------------------------------------------------------
# Architektura: warstwy nie mieszają się
# --------------------------------------------------------------------------

def test_logika_biznesowa_nie_zalezy_od_warstwy_stron():
    """Silnik prowizji i usługi nie mogą importować FastAPI ani modułów stron.
    Dzięki temu da się je kiedyś wydzielić albo użyć w procesie w tle."""
    import ast
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent / "app"
    for name in ["engine.py", "services.py", "models.py", "migrate.py"]:
        tree = ast.parse((root / name).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = ("." * node.level) + (node.module or "")
                assert not mod.startswith(("fastapi", "starlette", ".web", ".routes")), (name, mod)
            if isinstance(node, ast.Import):
                assert not any(a.name.startswith(("fastapi", "starlette")) for a in node.names), name


# --------------------------------------------------------------------------
# Biuro obsługi (BOK) i przełączniki uprawnień właściciela
# --------------------------------------------------------------------------

def _firma_z_bok_i_umowa(client) -> str:
    setup_company(client)
    login(client, "hania@firma.pl")
    r = post(client, "/umowy/nowa", "/umowy/nowa", CONTRACT)
    cid = r.headers["location"].rsplit("/", 1)[1]
    login(client, "kris@firma.pl")
    r = post(client, "/zespol/nowa", "/zespol", {
        "imie": "Beata", "nazwisko": "Biuro", "email": "bok@firma.pl", "haslo": PW, "rola": "bok", "udzial": "",
    })
    assert r.status_code == 303, r.text
    return cid


def _ustaw_bok(client, **flags):
    """Zapisuje formularz uprawnień; niewymienione przełączniki zostają przy wartościach domyślnych."""
    from app.models import BOK_PERMISSIONS
    login(client, "kris@firma.pl")
    values = {k: d[2] for k, d in BOK_PERMISSIONS.items()} | flags
    data = {k: "1" for k, v in values.items() if v}
    r = post(client, "/konto", "/konto/uprawnienia-bok", data)
    assert r.status_code == 303


def test_bok_bez_stawek_i_poza_listami_sprzedawcow(client):
    _firma_z_bok_i_umowa(client)
    from app.models import User, UserRate
    with SessionLocal() as db:
        b = db.query(User).filter_by(email="bok@firma.pl").one()
        assert b.role == "bok" and db.query(UserRate).filter_by(user_id=b.id).count() == 0
    html = client.get("/zespol").text
    assert "Beata Biuro" in html and "Biuro obsługi (BOK)" in html
    # BOK nie jest do wyboru jako handlowiec przy nowej umowie
    assert 'Beata Biuro</option>' not in client.get("/umowy/nowa").text


def test_bok_widzi_wszystkie_umowy_bez_warunkow_wlasciciela(client):
    cid = _firma_z_bok_i_umowa(client)
    login(client, "bok@firma.pl")
    menu = _menu(client.get("/pulpit").text)
    assert "<span>Spółki</span>" not in menu and "<span>Zespół</span>" not in menu
    assert client.get("/spolki").status_code == 403
    assert client.get("/zespol").status_code == 403
    page = client.get(f"/umowy/{cid}").text
    assert "Piekarnia Kowalski" in page
    for secret in ["Spółka obrotu → broker", "Przychód spółki", "udział brokera", "Udział brokera"]:
        assert secret not in page, secret
    # domyślnie bez prowizji handlowców
    assert "Prowizja handlowca" not in page and "20\u00a0000,00\u00a0zł" not in page
    pulpit = client.get("/pulpit").text
    assert "Przychód spółki" not in pulpit and "Prowizje handlowców" not in pulpit


def test_wlasciciel_wlacza_bokowi_prowizje(client):
    cid = _firma_z_bok_i_umowa(client)
    _ustaw_bok(client, bok_can_change_status=True, bok_sees_commissions=True)
    login(client, "bok@firma.pl")
    page = client.get(f"/umowy/{cid}").text
    assert "Prowizja handlowca: Hania Handlowiec" in page
    assert "20\u00a0000,00\u00a0zł" in page  # twarda spacja w tysiącach
    assert "Override menedżera: 5%" in page and "Twój override" not in page
    assert "Spółka obrotu → broker" not in page and "Przychód spółki" not in page
    assert "Prowizje handlowców" in client.get("/pulpit").text


def test_bok_zmienia_status_tylko_gdy_wlaczone(client):
    cid = _firma_z_bok_i_umowa(client)
    login(client, "bok@firma.pl")  # domyślnie włączone
    r = post(client, f"/umowy/{cid}", f"/umowy/{cid}/status", {"status": "Weryfikacja spółki"})
    assert r.status_code == 303
    assert "Wpisał(a): Beata Biuro" in client.get(f"/umowy/{cid}").text
    _ustaw_bok(client, bok_can_change_status=False)
    login(client, "bok@firma.pl")
    page = client.get(f"/umowy/{cid}").text
    assert f'action="/umowy/{cid}/status"' not in page and "Zmiana statusu jest wyłączona" in page
    r = post(client, "/umowy/nowa", f"/umowy/{cid}/status", {"status": "Start dostaw"})
    assert r.status_code == 400 and "Nie możesz zmienić statusu" in r.text


def test_bok_wpisuje_umowe_za_handlowca(client):
    _firma_z_bok_i_umowa(client)
    login(client, "bok@firma.pl")
    from app.models import User
    with SessionLocal() as db:
        hania = db.query(User).filter_by(email="hania@firma.pl").one().id
    r = post(client, "/umowy/nowa", "/umowy/nowa", {**CONTRACT, "klient": "Sklep Nowak", "handlowiec": str(hania)})
    assert r.status_code == 303
    with SessionLocal() as db:
        c = db.query(Contract).filter_by(client_name="Sklep Nowak").one()
        assert c.trader_id == hania and c.trader_share_pct > 0
    # przypisać umowy samemu BOK się nie da
    with SessionLocal() as db:
        bok = db.query(User).filter_by(email="bok@firma.pl").one().id
    r = post(client, "/umowy/nowa", "/umowy/nowa", {**CONTRACT, "klient": "Sklep X", "handlowiec": str(bok)})
    assert r.status_code == 400


def test_zmiany_uprawnien_maja_historie_i_tylko_wlasciciel(client):
    _firma_z_bok_i_umowa(client)
    _ustaw_bok(client, bok_can_change_status=True, bok_sees_commissions=True)
    page = client.get("/konto").text
    assert "Historia zmian uprawnień" in page
    assert "Widzi prowizje handlowców i override menedżerów, włączone, zmienił(a): Kris Właściciel" in page
    assert "Zacznie działać razem z modułem rezerwacji NIP." in page
    from app.models import PermissionChange
    with SessionLocal() as db:
        assert db.query(PermissionChange).count() == 1  # zmieniło się tylko jedno ustawienie
    for who in ["bok@firma.pl", "marek@firma.pl", "hania@firma.pl"]:
        login(client, who)
        assert "uprawnienia-bok" not in client.get("/konto").text
        r = post(client, "/konto", "/konto/uprawnienia-bok", {"bok_sees_commissions": "1"})
        assert r.status_code == 403, who


def test_migracja_dodaje_przelaczniki_z_domyslnymi(client):
    from sqlalchemy import inspect
    from app.db import engine
    cols = {c["name"] for c in inspect(engine).get_columns("company")}
    assert {"bok_can_change_status", "bok_sees_commissions", "bok_can_reserve_nip", "bok_can_reassign_clients"} <= cols


# --------------------------------------------------------------------------
# Strona /wersja
# --------------------------------------------------------------------------

def test_wersja_bez_logowania_pokazuje_commit_z_rendera(client, monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "c500d79abcdef0123456789")
    monkeypatch.setenv("RENDER_GIT_BRANCH", "main")
    r = client.get("/wersja", follow_redirects=False)
    assert r.status_code == 200
    assert "Działa wersja <strong>c500d79</strong> z gałęzi main." in r.text
    assert "Menu główne" not in r.text  # bez nawigacji dla niezalogowanych


def test_wersja_lokalnie_bez_numeru(client, monkeypatch):
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    r = client.get("/wersja")
    assert r.status_code == 200 and "Numer wersji jest nieznany" in r.text


def test_nieistniejacy_adres_po_polsku(client):
    r = client.get("/nie-ma-takiej-strony")
    assert r.status_code == 404
    assert "Nie znaleziono strony." in r.text and 'lang="pl"' in r.text and '"detail"' not in r.text


# --------------------------------------------------------------------------
# Reset hasła przez właściciela i wskazówka odzyskiwania na stronie logowania
# --------------------------------------------------------------------------

def test_logowanie_ma_wskazowke_odzyskiwania_hasla(client):
    setup_company(client)
    page = client.get("/logowanie").text
    assert "Nie pamiętasz hasła?" in page and "właściciela" in page


def test_wlasciciel_resetuje_haslo_osoby(client):
    setup_company(client)
    login(client, "kris@firma.pl")
    with SessionLocal() as db:
        hania_id = db.query(User).filter_by(email="hania@firma.pl").one().id
    r = post(client, f"/zespol/{hania_id}", f"/zespol/{hania_id}/reset-hasla", {})
    assert r.status_code == 200
    assert "Nowe hasło zostało zmienione" in r.text or "Hasło zostało zmienione" in r.text
    assert "Login: hania@firma.pl" in r.text
    m = re.search(r"Hasło: <code>([^<]+)</code>", r.text)
    assert m and re.fullmatch(r"[a-z2-9]{4}-[a-z2-9]{4}-[a-z2-9]{4}", m.group(1))
    new_password = m.group(1)
    # stare hasło już nie działa, nowe działa
    r = post(client, "/logowanie", "/logowanie", {"email": "hania@firma.pl", "haslo": PW})
    assert r.status_code == 401
    r = post(client, "/logowanie", "/logowanie", {"email": "hania@firma.pl", "haslo": new_password})
    assert r.status_code == 303 and r.headers["location"] == "/pulpit"


def test_reset_hasla_tylko_dla_wlasciciela(client):
    setup_company(client)
    with SessionLocal() as db:
        hania_id = db.query(User).filter_by(email="hania@firma.pl").one().id
    for who in ["marek@firma.pl", "hania@firma.pl"]:
        login(client, who)
        r = post(client, "/umowy/nowa", f"/zespol/{hania_id}/reset-hasla", {})
        assert r.status_code == 403


# --------------------------------------------------------------------------
# Dostęp BOK do zespołu i resetu hasła zależny od uprawnienia bok_sees_commissions,
# ostatnie logowanie, wylogowanie wszystkich innych urządzeń
# --------------------------------------------------------------------------

def _dodaj_bok(client) -> int:
    login(client, "kris@firma.pl")
    r = post(client, "/zespol/nowa", "/zespol", {
        "imie": "Beata", "nazwisko": "Biuro", "email": "bok@firma.pl", "haslo": PW, "rola": "bok", "udzial": "",
    })
    assert r.status_code == 303, r.text
    with SessionLocal() as db:
        return db.query(User).filter_by(email="bok@firma.pl").one().id


def _ustaw_bok_widzi_prowizje(client, on: bool):
    from app.models import BOK_PERMISSIONS
    login(client, "kris@firma.pl")
    values = {k: d[2] for k, d in BOK_PERMISSIONS.items()} | {"bok_sees_commissions": on}
    data = {k: "1" for k, v in values.items() if v}
    r = post(client, "/konto", "/konto/uprawnienia-bok", data)
    assert r.status_code == 303


def test_bok_bez_prowizji_nie_widzi_zespolu_ani_nie_resetuje_hasel(client):
    setup_company(client)
    _dodaj_bok(client)
    with SessionLocal() as db:
        hania_id = db.query(User).filter_by(email="hania@firma.pl").one().id
    login(client, "bok@firma.pl")
    assert "Zespół" not in _menu(client.get("/pulpit").text)
    assert client.get("/zespol").status_code == 403
    assert client.get(f"/zespol/{hania_id}").status_code == 403
    r = post(client, "/konto", f"/zespol/{hania_id}/reset-hasla", {})
    assert r.status_code == 403


def test_bok_z_prowizjami_resetuje_haslo_handlowca_ale_nie_wlasciciela(client):
    setup_company(client)
    bok_id = _dodaj_bok(client)
    _ustaw_bok_widzi_prowizje(client, True)
    with SessionLocal() as db:
        hania_id = db.query(User).filter_by(email="hania@firma.pl").one().id
        kris_id = db.query(User).filter_by(email="kris@firma.pl").one().id
    login(client, "bok@firma.pl")
    assert "Zespół" in _menu(client.get("/pulpit").text)
    page = client.get("/zespol").text
    assert "Hania Handlowiec" in page and "Kris Właściciel" not in page and "Beata Biuro" not in page
    # reset handlowca: działa
    r = post(client, f"/zespol/{hania_id}", f"/zespol/{hania_id}/reset-hasla", {})
    assert r.status_code == 200 and "Login: hania@firma.pl" in r.text
    # właściciela i siebie samego (innego BOK) BOK nie widzi i nie resetuje — 404, nie 403
    assert client.get(f"/zespol/{kris_id}").status_code == 404
    assert client.get(f"/zespol/{bok_id}").status_code == 404
    r = post(client, "/konto", f"/zespol/{kris_id}/reset-hasla", {})
    assert r.status_code == 404
    # BOK nie widzi ani nie edytuje stawek/ustawień konta na stronie handlowca
    page = client.get(f"/zespol/{hania_id}").text
    assert "Zmień stawki" not in page and "Ustawienia konta" not in page
    assert "Udział w całej masie marży" in page  # odczyt stawki zostaje


def test_ostatnie_logowanie_i_wylogowanie_wszystkich_urzadzen(client):
    setup_company(client)
    with SessionLocal() as db:
        hania = db.query(User).filter_by(email="hania@firma.pl").one()
        assert hania.last_login_at is None
    login(client, "hania@firma.pl")
    with SessionLocal() as db:
        assert db.query(User).filter_by(email="hania@firma.pl").one().last_login_at is not None
    assert "Ostatnie logowanie:" in client.get("/konto").text
    assert "to Twoje pierwsze logowanie" not in client.get("/konto").text

    # drugie „urządzenie”: osobny klient tego samego konta
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as drugie:
        login(drugie, "hania@firma.pl")
        assert drugie.get("/pulpit").status_code == 200

        r = post(client, "/konto", "/konto/wyloguj-wszystkie", {})
        assert r.status_code == 303
        # to urządzenie (client) zostaje zalogowane
        assert client.get("/pulpit").status_code == 200
        # drugie urządzenie jest wylogowane
        assert drugie.get("/pulpit", follow_redirects=False).headers["location"] == "/logowanie"


def test_stare_sesje_bez_klucza_sv_nie_sa_wylogowywane(client):
    """Cookie z wersji aplikacji sprzed tej zmiany nie ma klucza "sv" — taka sesja
    ma działać dalej, a nie wylogowywać wszystkich od razu po wdrożeniu."""
    import json
    from base64 import b64decode, b64encode

    import itsdangerous

    setup_company(client)
    login(client, "hania@firma.pl")
    signer = itsdangerous.TimestampSigner("test-secret")
    raw = client.cookies.get("session").encode()
    payload = json.loads(b64decode(signer.unsign(raw, max_age=60 * 60 * 12)))
    assert "sv" in payload
    del payload["sv"]
    stripped = signer.sign(b64encode(json.dumps(payload).encode())).decode()
    client.cookies.set("session", stripped)
    assert client.get("/pulpit").status_code == 200


# --------------------------------------------------------------------------
# Produkt cenowy (SPOT/FIX/TRANZA) i filtry na liście umów
# --------------------------------------------------------------------------

def _umowa(client, **over):
    data = {**CONTRACT, **over}
    r = post(client, "/umowy/nowa", "/umowy/nowa", data)
    assert r.status_code == 303, r.text
    return int(r.headers["location"].rsplit("/", 1)[1])


def test_nowa_umowa_bez_produktu_dostaje_domyslnie_fix(client):
    setup_company(client)
    login(client, "hania@firma.pl")
    cid = _umowa(client)
    page = client.get(f"/umowy/{cid}").text
    assert '<span class="produkt produkt-fix">FIX</span>' in page
    assert client.get("/umowy").text.count('class="produkt produkt-fix"') == 1


def test_wybor_produktu_zapisuje_sie_i_pokazuje_plakietke(client):
    setup_company(client)
    login(client, "hania@firma.pl")
    cid = _umowa(client, produkt="spot", klient="Firma SPOT")
    page = client.get(f"/umowy/{cid}").text
    assert '<span class="produkt produkt-spot">SPOT (RDN)</span>' in page
    with SessionLocal() as db:
        assert db.get(Contract, cid).pricing_product == "spot"


def test_niepoprawny_produkt_z_formularza_zostaje_fix(client):
    setup_company(client)
    login(client, "hania@firma.pl")
    cid = _umowa(client, produkt="ropa-naftowa")
    with SessionLocal() as db:
        assert db.get(Contract, cid).pricing_product == "fix"


def test_filtr_po_produkcie_zaweza_liste(client):
    setup_company(client)
    login(client, "hania@firma.pl")
    _umowa(client, produkt="spot", klient="Klient SPOT")
    _umowa(client, produkt="fix", klient="Klient FIX")
    _umowa(client, produkt="tranza", klient="Klient Transza")
    client.get("/umowy")  # strąca komunikat „Zapisano umowę…” po ostatnim zapisie

    page = client.get("/umowy?produkt=spot").text
    assert "Klient SPOT" in page and "Klient FIX" not in page and "Klient Transza" not in page

    page = client.get("/umowy?produkt=spot&produkt=tranza").text
    assert "Klient SPOT" in page and "Klient Transza" in page and "Klient FIX" not in page

    page = client.get("/umowy").text
    assert all(k in page for k in ("Klient SPOT", "Klient FIX", "Klient Transza"))
    assert "Wyczyść filtry" not in page


def test_filtry_zakresow_dat_i_wolumenu_oraz_sortowanie(client):
    setup_company(client)
    login(client, "hania@firma.pl")
    _umowa(client, klient="Mala", wolumen="10", podpisana="2026-01-05")
    _umowa(client, klient="Duza", wolumen="900", podpisana="2026-06-01")

    page = client.get("/umowy?wolumen_min=500").text
    assert "Duza" in page and "Mala" not in page

    page = client.get("/umowy?od=2026-05-01").text
    assert "Duza" in page and "Mala" not in page

    page = client.get("/umowy?sort=wolumen_asc").text
    assert page.index("Mala") < page.index("Duza")
    page = client.get("/umowy?sort=wolumen_desc").text
    assert page.index("Duza") < page.index("Mala")

    assert "Wyczyść filtry" in client.get("/umowy?wolumen_min=500").text


def test_filtr_po_niepoprawnej_wartosci_nie_wywraca_strony(client):
    setup_company(client)
    login(client, "hania@firma.pl")
    _umowa(client)
    r = client.get("/umowy?wolumen_min=abc&od=nie-data&spolka=xyz&sort=cokolwiek&produkt=benzyna")
    assert r.status_code == 200
    assert "Wyczyść filtry" not in r.text  # żaden filtr się nie przyjął


def test_handlowiec_nie_widzi_filtra_po_handlowcu(client):
    setup_company(client)
    login(client, "hania@firma.pl")
    _umowa(client)
    assert 'id="f-handlowiec"' not in client.get("/umowy").text
    login(client, "marek@firma.pl")
    assert 'id="f-handlowiec"' in client.get("/umowy").text


def test_demo_umowy_maja_produkt_fix_domyslnie(client):
    setup_company(client)
    login(client, "kris@firma.pl")
    from .test_import import _demo_preview
    bid = _demo_preview(client)
    r = post(client, f"/konto/import/{bid}", f"/konto/import/{bid}/zatwierdz", {})
    assert r.status_code == 200
    with SessionLocal() as db:
        demo = db.query(Contract).filter(Contract.import_batch_id.isnot(None)).all()
        assert all(c.pricing_product == "fix" for c in demo)


# --------------------------------------------------------------------------
# Nazewnictwo marży, sprzedaż miesiąca vs target, polityka transzy B,
# zakładka Zespół menedżera
# --------------------------------------------------------------------------

def _dzis_umowa(client, **over):
    from datetime import date
    return _umowa(client, podpisana=date.today().isoformat(), **over)


def test_nazewnictwo_marza_i_przychod_spolki(client):
    setup_company(client)
    login(client, "kris@firma.pl")
    _dzis_umowa(client)
    page = client.get("/pulpit").text
    assert "Całkowita masa marży" in page and "Przychód spółki" in page
    assert "narzut" not in page.lower().replace('name="narzut', "")


def test_handlowiec_widzi_sprzedaz_miesiaca_i_target(client):
    from datetime import date
    setup_company(client)
    login(client, "hania@firma.pl")
    _dzis_umowa(client)  # 100 MWh x 5 lat x 100 zł = 50 000 zł masy marży
    page = client.get("/pulpit").text
    assert "Twoja sprzedaż" in page and "nie ustawiony" in page
    # menedżer Hani ustawia jej target na bieżący miesiąc
    login(client, "marek@firma.pl")
    with SessionLocal() as db:
        hania = db.query(User).filter_by(email="hania@firma.pl").one().id
    miesiac = date.today().strftime("%Y-%m")
    r = post(client, f"/zespol/{hania}", f"/zespol/{hania}/target", {"miesiac": miesiac, "kwota": "200000"})
    assert r.status_code == 303, r.text
    login(client, "hania@firma.pl")
    page = client.get("/pulpit").text
    assert "<strong>25% targetu</strong>" in page  # 50 000 z 200 000
    assert "Twoja transza A z tych umów" in page


def test_menedzer_ma_zakladke_zespol_tylko_ze_swoimi_ludzmi(client):
    setup_company(client)
    login(client, "marek@firma.pl")
    assert "<span>Zespół</span>" in _menu(client.get("/pulpit").text)
    page = client.get("/zespol").text
    assert "Hania Handlowiec" in page and "Olek Obcy" not in page and "Kris Właściciel" not in page
    with SessionLocal() as db:
        olek = db.query(User).filter_by(email="olek@firma.pl").one().id
        hania = db.query(User).filter_by(email="hania@firma.pl").one().id
    assert client.get(f"/zespol/{olek}").status_code == 404
    page = client.get(f"/zespol/{hania}").text
    # menedżer nie edytuje stawek, nie resetuje haseł
    assert "Zmień stawki" not in page and "Nadaj nowe hasło" not in page and "Target masy marży" in page
    r = post(client, f"/zespol/{hania}", f"/zespol/{hania}/reset-hasla", {})
    assert r.status_code == 403
    r = post(client, f"/zespol/{hania}", f"/zespol/{olek}/target", {"miesiac": "2026-11", "kwota": "1"})
    assert r.status_code == 404
    assert client.get("/zespol/nowa").status_code == 403


def test_handlowiec_nie_ustawia_targetu(client):
    setup_company(client)
    login(client, "hania@firma.pl")
    with SessionLocal() as db:
        hania = db.query(User).filter_by(email="hania@firma.pl").one().id
    assert client.get("/zespol").status_code == 403
    r = post(client, "/konto", f"/zespol/{hania}/target", {"miesiac": "2026-11", "kwota": "999999"})
    assert r.status_code == 403


def test_polityka_ukrywa_transze_b_handlowcowi(client):
    setup_company(client)
    login(client, "hania@firma.pl")
    cid = _dzis_umowa(client)
    assert "Prognoza transzy B" in client.get("/pulpit").text
    assert "Podział prowizji z całego okresu" in client.get(f"/umowy/{cid}").text
    login(client, "kris@firma.pl")
    r = post(client, "/konto", "/konto/polityka", {})  # odznaczone = wyłączone
    assert r.status_code == 303
    assert "Handlowcy widzą prognozę transzy B, wyłączone" in client.get("/konto").text
    login(client, "hania@firma.pl")
    page = client.get("/pulpit").text
    assert "Prognoza transzy B" not in page and "Transza A z Twoich umów" in page
    page = client.get(f"/umowy/{cid}").text
    assert "Podział prowizji z całego okresu" not in page and "Twoja transza A" in page
    # menedżer i właściciel dalej widzą pełny podział
    login(client, "marek@firma.pl")
    assert "Podział prowizji z całego okresu" in client.get(f"/umowy/{cid}").text


def test_cofniecie_demo_usuwa_targety(client):
    from datetime import date
    setup_company(client)
    login(client, "kris@firma.pl")
    from .test_import import _demo_preview
    bid = _demo_preview(client)
    post(client, f"/konto/import/{bid}", f"/konto/import/{bid}/zatwierdz", {})
    with SessionLocal() as db:
        anna = db.query(User).filter(User.last_name == "Kowalczyk").one().id
    post(client, f"/zespol/{anna}", f"/zespol/{anna}/target", {"miesiac": date.today().strftime("%Y-%m"), "kwota": "150000"})
    r = post(client, "/konto/import", f"/konto/import/{bid}/cofnij", {"potwierdzam": "1"})
    assert r.status_code == 303
    from app.models import SalesTarget
    with SessionLocal() as db:
        assert db.query(SalesTarget).count() == 0


def test_wlasciciel_nie_resetuje_wlasnego_hasla_losowym_przyciskiem(client):
    setup_company(client)
    login(client, "kris@firma.pl")
    with SessionLocal() as db:
        kris_id = db.query(User).filter_by(email="kris@firma.pl").one().id
    page = client.get(f"/zespol/{kris_id}").text
    assert "Nadaj nowe hasło" not in page and "Zmień hasło" in page
    r = post(client, f"/zespol/{kris_id}", f"/zespol/{kris_id}/reset-hasla", {})
    assert r.status_code == 303 and r.headers["location"] == f"/zespol/{kris_id}"
    # hasło nie zostało zmienione: stare dalej działa
    login(client, "kris@firma.pl")
    assert client.get("/pulpit").status_code == 200


# --------------------------------------------------------------------------
# Pulpit sprzedażowy: oferty złożone, statystyki po miesiącach, filtry z licznikiem
# --------------------------------------------------------------------------

def test_oferty_zlozone_na_pulpicie_menedzera_i_poza_portfelem(client):
    setup_company(client)
    login(client, "hania@firma.pl")
    _dzis_umowa(client)  # podpisana: 50 000 zł masy marży
    _dzis_umowa(client, klient="Wózki Widłowe Michalski", status="Oferta", wolumen="200")  # 100 000 zł
    page = client.get("/pulpit").text.replace("\u00a0", " ")
    assert "Oferty złożone" in page and "Twoje oferty: 1 oferta" in page and "Wózki Widłowe Michalski" in page
    # oferta nie zawyża sprzedaży miesiąca ani portfela
    sales = page.split("Sprzedaż:", 1)[1].split("Oferty złożone", 1)[0]
    assert "50 000,00 zł" in sales and "150 000" not in sales
    assert "Masa marży, jeśli wszystkie się zamkną</dt><dd>100 000,00 zł" in page
    # menedżer widzi oferty zespołu pogrupowane po handlowcach, ale bez przychodu spółki
    login(client, "marek@firma.pl")
    page = client.get("/pulpit").text
    assert "Hania Handlowiec: 1 oferta" in page and "Wózki Widłowe Michalski" in page
    assert "Przychód spółki" not in page
    # właściciel widzi przychód spółki z ofert
    login(client, "kris@firma.pl")
    page = client.get("/pulpit").text
    assert "Przychód spółki, jeśli wszystkie się zamkną" in page


def test_oferty_handlowca_niewidoczne_dla_innego_handlowca(client):
    setup_company(client)
    login(client, "hania@firma.pl")
    _dzis_umowa(client, klient="Wózki Widłowe Michalski", status="Oferta")
    login(client, "olek@firma.pl")
    page = client.get("/pulpit").text
    assert "Wózki Widłowe Michalski" not in page and "Brak otwartych ofert" in page


def test_statystyki_sprzedazy_po_miesiacach(client):
    from datetime import date
    setup_company(client)
    login(client, "hania@firma.pl")
    _dzis_umowa(client)
    page = client.get("/pulpit").text
    assert 'id="statystyki"' in page and "Statystyki sprzedaży" in page
    assert '<details class="zwijane" id="statystyki">' in page  # domyślnie zwinięte
    m = date.today().strftime("%Y-%m")
    page = client.get(f"/pulpit?od_mies={m}&do_mies={m}").text.replace("\u00a0", " ")
    assert '<details class="zwijane" id="statystyki" open>' in page  # po filtrowaniu rozwinięte
    assert "Razem: 1 umowa, masa marży 50 000,00 zł" in page
    # śmieci w adresie nie wywracają strony
    assert client.get("/pulpit?od_mies=abc&do_mies=2026-99").status_code == 200


def test_licznik_wynikow_filtra_respektuje_widocznosc(client):
    setup_company(client)
    login(client, "hania@firma.pl")
    _dzis_umowa(client)
    _dzis_umowa(client, klient="Druga", status="Oferta")
    r = client.get("/umowy/liczba")
    assert r.json() == {"count": 2, "text": "2 umowy"} and r.headers["cache-control"] == "no-store"
    assert client.get("/umowy/liczba?status=Oferta").json()["count"] == 1
    assert client.get("/umowy/liczba?produkt=spot").json()["text"] == "0 umów"
    login(client, "olek@firma.pl")  # cudze umowy się nie liczą
    assert client.get("/umowy/liczba").json()["count"] == 0
    client.cookies.clear()
    assert client.get("/umowy/liczba", follow_redirects=False).status_code in (303, 401)


def test_lista_umow_filtry_zwiniete_z_licznikiem_i_czyszczeniem(client):
    setup_company(client)
    login(client, "hania@firma.pl")
    _dzis_umowa(client)
    page = client.get("/umowy").text
    assert '<details class="panel" id="panel-filtrow">' in page and "Pasuje: 1 umowa." in page
    assert "Wyczyść filtry" not in page
    page = client.get("/umowy?produkt=fix&medium=energia").text
    assert "Filtry (2)" in page and "Wyczyść filtry" in page
    assert '<details class="panel" id="panel-filtrow">' in page  # po filtrowaniu panel zwinięty, widać wyniki
    assert "/static/filtry.js" in page


def test_odmiana_liczebnikow():
    from app.services import plural_oferty, plural_umowy
    assert [plural_umowy(n) for n in (0, 1, 2, 5, 12, 22, 25)] == ["0 umów", "1 umowa", "2 umowy", "5 umów", "12 umów", "22 umowy", "25 umów"]
    assert plural_oferty(1) == "1 oferta" and plural_oferty(3) == "3 oferty" and plural_oferty(14) == "14 ofert"


def test_statystyki_osoby_ranking_i_rytm_w_zespole(client):
    from datetime import date
    setup_company(client)
    login(client, "hania@firma.pl")
    _dzis_umowa(client)
    login(client, "marek@firma.pl")
    with SessionLocal() as db:
        hania = db.query(User).filter_by(email="hania@firma.pl").one().id
    post(client, f"/zespol/{hania}", f"/zespol/{hania}/target", {"miesiac": date.today().strftime("%Y-%m"), "kwota": "100000"})
    page = client.get("/zespol").text
    assert "Ranking:" in page and "<strong>50% targetu</strong>" in page
    assert "Rytm: umowy w 1 z ostatnich 6 miesięcy" in page and "nieregularnie" in page
    page = client.get(f"/zespol/{hania}").text
    assert "Statystyki sprzedaży: umowy w 1 z 12 miesięcy" in page and "brak umów" in page
    assert "50% targetu" in page
    assert client.get(f"/zespol/{hania}?od_mies=xx").status_code == 200


def test_stara_oferta_jest_wyrozniona(client):
    from datetime import date, timedelta
    setup_company(client)
    login(client, "hania@firma.pl")
    _umowa(client, klient="Stara oferta", status="Oferta", podpisana=(date.today() - timedelta(days=20)).isoformat())
    page = client.get("/pulpit").text
    assert "Czeka 20 dni" in page and "czeka ponad 14 dni: 1" in page
