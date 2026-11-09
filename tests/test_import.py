"""Import z Excela: szablon, dane demonstracyjne, podgląd, zatwierdzenie, cofnięcie, poufność."""
import re
from io import BytesIO

from openpyxl import Workbook, load_workbook

from app.db import SessionLocal
from app.models import Contract, ContractStatusEvent, ImportBatch, Supplier, User

from .conftest import login, post
from .test_app import CONTRACT, setup_company


def _demo_preview(client) -> int:
    r = post(client, "/konto/import", "/konto/import/demo", {})
    assert r.status_code == 303, r.text
    return int(r.headers["location"].rsplit("/", 1)[1])


def _commit(client, bid):
    return post(client, f"/konto/import/{bid}", f"/konto/import/{bid}/zatwierdz", {})


def _counts():
    with SessionLocal() as db:
        return {
            "umowy": db.query(Contract).count(), "osoby": db.query(User).count(),
            "spolki": db.query(Supplier).count(), "zdarzenia": db.query(ContractStatusEvent).count(),
        }


def test_import_tylko_dla_wlasciciela(client):
    setup_company(client)
    login(client, "kris@firma.pl")
    assert '<a href="/konto/import">Import danych</a>' in client.get("/konto").text
    assert client.get("/konto/import").status_code == 200
    for who in ["marek@firma.pl", "hania@firma.pl"]:
        login(client, who)
        assert "/konto/import" not in client.get("/konto").text
        assert client.get("/konto/import").status_code == 403
        assert client.get("/konto/import/demo.xlsx").status_code == 403
        r = post(client, "/konto", "/konto/import/demo", {})
        assert r.status_code == 403


def test_szablon_ma_readme_i_arkusze(client):
    setup_company(client)
    login(client, "kris@firma.pl")
    r = client.get("/konto/import/szablon.xlsx")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    wb = load_workbook(BytesIO(r.content))
    assert wb.sheetnames == ["README", "zespol", "spolki", "umowy", "historia_statusow"]
    assert wb["README"]["A1"].value == "standard" and wb["README"]["B1"].value == "1.0"
    assert [c.value for c in wb["umowy"][1]][:3] == ["id_zewn", "klient_nazwa", "klient_nip"]


def test_demo_podglad_niczego_nie_zapisuje_a_zatwierdzenie_tak(client):
    setup_company(client)
    login(client, "kris@firma.pl")
    before = _counts()
    bid = _demo_preview(client)
    page = client.get(f"/konto/import/{bid}").text
    assert "Plik jest poprawny" in page and "Umowy: 100" in page and "Osoby: 9" in page
    assert _counts() == before
    r = _commit(client, bid)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert "Te hasła widzisz tylko teraz" in r.text
    after = _counts()
    assert after["umowy"] == before["umowy"] + 100 and after["osoby"] == before["osoby"] + 9
    assert after["spolki"] == before["spolki"] + 12
    # hasła czytelne: trzy grupy po cztery znaki
    passwords = re.findall(r"Login: ([^<]+)</p>\s*<p>Hasło: <code>([^<]+)</code>", r.text)
    assert len(passwords) == 9
    assert all(re.fullmatch(r"[a-z2-9]{4}-[a-z2-9]{4}-[a-z2-9]{4}", p) for _, p in passwords)
    # baner demo dla zalogowanych
    assert "Dane demonstracyjne." in client.get("/pulpit").text
    # handlowiec demo loguje się hasłem z raportu i nie widzi warunków właściciela
    email, pw = next((e, p) for e, p in passwords if e.startswith("anna.kowalczyk"))
    login(client, email, pw)
    html = client.get("/umowy").text
    assert "Dane demonstracyjne." in html
    with SessionLocal() as db:
        anna = db.query(User).filter_by(email=email).one()
        cid = db.query(Contract).filter_by(trader_id=anna.id).first().id
    page = client.get(f"/umowy/{cid}").text
    assert "Twoja prowizja" in page
    for secret in ["Spółka obrotu → broker", "Przychód spółki", "Udział brokera"]:
        assert secret not in page


def test_demo_scenariusze_i_historia(client):
    setup_company(client)
    login(client, "kris@firma.pl")
    _commit(client, _demo_preview(client))
    with SessionLocal() as db:
        demo = db.query(Contract).filter(Contract.import_batch_id.isnot(None)).all()
        statuses = [c.status for c in demo]
        assert statuses.count("Zerwana") == 9 and statuses.count("Weryfikacja spółki") == 6
        assert statuses.count("Zakończona") == 5 and statuses.count("Umowa podpisana") == 8
        # najgorszy portfel: Paweł Kamiński ma co najmniej 4 zerwania
        pawel = db.query(User).filter(User.last_name == "Kamiński").one()
        assert sum(1 for c in demo if c.trader_id == pawel.id and c.status == "Zerwana") >= 4
        # zerwania mają powód w historii
        for c in demo:
            if c.status == "Zerwana":
                assert c.events[-1].note
        # Axpo: dwa zestawy reguł, umowy sprzed zmiany zachowują 74%
        axpo = db.query(Supplier).filter_by(name="Axpo").one()
        assert len(axpo.rule_sets) == 2
        for c in demo:
            if c.supplier_id == axpo.id:
                expected = 70 if c.signed_date >= axpo.rule_sets[0].valid_from else 74
                assert c.broker_share_pct == expected
        # spółki z prawdziwymi nazwami, bez NIP-ów klientów
        names = {s.name for s in db.query(Supplier)}
        assert {"e2V (Ekovoltis)", "ENGIE", "Enefit", "Polenergia", "Respect Energy", "Axpo", "Audax"} <= names
        assert all(c.client_nip == "" for c in demo)


def test_cofniecie_demo_zostawia_prawdziwe_dane(client):
    setup_company(client)
    login(client, "kris@firma.pl")
    post(client, "/umowy/nowa", "/umowy/nowa", CONTRACT)
    before = _counts()
    bid = _demo_preview(client)
    _commit(client, bid)
    r = post(client, f"/konto/import/{bid}", f"/konto/import/{bid}/cofnij", {})
    assert r.status_code == 303  # bez potwierdzenia nic się nie dzieje
    assert _counts()["umowy"] == before["umowy"] + 100
    r = post(client, f"/konto/import/{bid}", f"/konto/import/{bid}/cofnij", {"potwierdzam": "1"})
    assert r.status_code == 303
    assert _counts() == before
    assert "Dane demonstracyjne." not in client.get("/pulpit").text
    with SessionLocal() as db:
        assert db.get(ImportBatch, bid).status == "cofniety"


def test_cofniecie_blokowane_gdy_prawdziwa_umowa_uzywa_osoby_z_demo(client):
    setup_company(client)
    login(client, "kris@firma.pl")
    bid = _demo_preview(client)
    _commit(client, bid)
    with SessionLocal() as db:
        anna = db.query(User).filter(User.last_name == "Kowalczyk").one().id
    post(client, "/umowy/nowa", "/umowy/nowa", {**CONTRACT, "klient": "Prawdziwy klient", "handlowiec": str(anna)})
    page = client.get(f"/konto/import/{bid}").text
    assert "Tego importu nie można teraz cofnąć" in page and "1 umów spoza tej paczki" in page
    r = post(client, "/konto/import", f"/konto/import/{bid}/cofnij", {"potwierdzam": "1"})
    assert r.status_code == 303
    with SessionLocal() as db:
        assert db.get(ImportBatch, bid).status == "zatwierdzony"


def test_ponowny_import_tego_samego_nie_dubluje(client):
    setup_company(client)
    login(client, "kris@firma.pl")
    _commit(client, _demo_preview(client))
    before = _counts()
    bid = _demo_preview(client)
    page = client.get(f"/konto/import/{bid}").text
    assert "Plik ma błędy" in page and "już istnieje" in page
    r = _commit(client, bid)
    assert r.status_code == 303
    assert _counts() == before


def _xlsx(sheets: dict) -> bytes:
    wb = Workbook()
    wb.active.title = "README"
    wb["README"].append(["standard", "1.0"])
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _upload(client, content: bytes, name="plik.xlsx"):
    from .conftest import csrf_of
    token = csrf_of(client.get("/konto/import").text)
    return client.post("/konto/import", data={"csrf": token}, files={"plik": (name, content)}, follow_redirects=False)


def test_raport_bledow_wiersz_po_wierszu(client):
    setup_company(client)
    login(client, "kris@firma.pl")
    head = ["id_zewn", "klient_nazwa", "klient_nip", "medium", "spolka", "handlowiec_email", "data_podpisania",
            "okres_miesiace", "wolumen_roczny_mwh", "narzut_zl_mwh", "status"]
    content = _xlsx({"umowy": [
        head,
        ["X1", "Firma A", "1234567890", "energia", "Spółka A", "hania@firma.pl", "2026-01-10", 12, "100", "50", "Umowa podpisana"],
        ["X2", "Firma B", "", "energia", "Nieznana", "hania@firma.pl", "10.01.2026", 12, "100", "50", "Umowa podpisana"],
        ["X3", "Firma C", "", "prąd", "Spółka A", "hania@firma.pl", "2026-01-10", 12, "abc", "50", "Umowa podpisana"],
        ["X4", "Firma D", "", "energia", "Spółka A", "hania@firma.pl", "2026-01-10", 12, "100", "50", "Umowa podpisana"],
    ]})
    r = _upload(client, content)
    assert r.status_code == 303
    page = client.get(r.headers["location"]).text
    assert "Plik ma błędy" in page
    assert "Arkusz umowy, wiersz 2, kolumna klient_nip: NIP ma niepoprawną sumę kontrolną." in page
    assert "Arkusz umowy, wiersz 3, kolumna spolka: nie ma spółki Nieznana" in page
    assert "Arkusz umowy, wiersz 4, kolumna medium: wartość „prąd” spoza listy" in page
    assert "Arkusz umowy, wiersz 4, kolumna wolumen_roczny_mwh: to nie jest liczba" in page
    assert "Umowy: 1" in page  # tylko wiersz 5 jest poprawny
    assert "Zatwierdź i zapisz" not in page


def test_zly_plik_i_brak_kolumn(client):
    setup_company(client)
    login(client, "kris@firma.pl")
    page = client.get(_upload(client, b"to nie jest excel").headers["location"]).text
    assert "Nie udało się otworzyć pliku" in page
    page = client.get(_upload(client, _xlsx({"umowy": [["klient_nazwa"], ["Firma"]]})).headers["location"]).text
    assert "brakuje wymaganych kolumn" in page
    r = _upload(client, b"x", name="plik.csv")
    assert r.status_code == 303 and r.headers["location"] == "/konto/import"


def test_historia_statusow_z_pliku_i_zgodnosc_statusu(client):
    setup_company(client)
    login(client, "kris@firma.pl")
    head = ["id_zewn", "klient_nazwa", "medium", "spolka", "handlowiec_email", "data_podpisania",
            "okres_miesiace", "wolumen_roczny_mwh", "narzut_zl_mwh", "status"]
    hist = ["umowa_id_zewn", "status", "data_zdarzenia", "notatka"]
    content = _xlsx({
        "umowy": [head,
                  ["H1", "Firma H", "energia", "Spółka A", "hania@firma.pl", "2026-01-10", 24, 100, 50, "Start dostaw"],
                  ["H2", "Firma I", "energia", "Spółka A", "hania@firma.pl", "2026-01-10", 24, 100, 50, "Zerwana"]],
        "historia_statusow": [hist,
                              ["H1", "Umowa podpisana", "2026-01-10", ""],
                              ["H1", "Weryfikacja spółki", "2026-01-15", "Wysłane"],
                              ["H1", "Start dostaw", "2026-03-01", ""],
                              ["H2", "Umowa podpisana", "2026-01-10", ""],
                              ["H2", "Zerwana", "2026-02-01", ""]],
    })
    page = client.get(_upload(client, content).headers["location"]).text
    assert "Przy statusie „Zerwana” podaj powód" in page
    assert "Umowy: 1" in page and "Zmiany statusów z historii: 2" in page


def test_logika_importu_nie_zalezy_od_warstwy_stron():
    import ast
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent / "app" / "exchange"
    for f in root.glob("*.py"):
        tree = ast.parse(f.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = ("." * node.level) + (node.module or "")
                assert not mod.startswith(("fastapi", "starlette", "..web", "..routes")), (f.name, mod)


def test_migracja_najpierw_kolumny_potem_dane(client, monkeypatch):
    """Regresja: kroki danych (zapytania ORM) dopiero po dodaniu wszystkich kolumn.
    Odwrotna kolejność wywracała start aplikacji na bazie sprzed wdrożenia."""
    from app import migrate
    from app.db import engine
    calls = []
    monkeypatch.setattr(migrate, "_add_column", lambda e, t, c, d: calls.append(("schemat", t, c)))
    monkeypatch.setattr(migrate, "_split_names", lambda e: calls.append(("dane", "users", "")))
    monkeypatch.setattr(migrate, "_baseline_status_history", lambda e: calls.append(("dane", "historia", "")))
    migrate.run(engine)
    kinds = [k for k, _, _ in calls]
    assert "dane" in kinds and kinds.index("dane") > max(i for i, k in enumerate(kinds) if k == "schemat")
    assert ("schemat", "users", "import_batch_id") in calls and ("schemat", "contracts", "ext_id") in calls


def test_czysty_start_kasuje_wszystko_raz_a_potem_nie_rusza_danych(client):
    """Symulacja wdrożenia na bazie z danymi: pierwszy start po wdrożeniu czyści,
    drugi (kolejne wdrożenie) już nie."""
    from app import migrate
    from app.db import engine
    from app.models import Company, SystemFlag
    setup_company(client)
    login(client, "kris@firma.pl")
    post(client, "/umowy/nowa", "/umowy/nowa", CONTRACT)
    assert _counts()["umowy"] == 1 and _counts()["osoby"] >= 2
    # cofamy znacznik, jakby to był serwer sprzed tego wdrożenia
    with SessionLocal() as db:
        db.query(SystemFlag).delete()
        db.commit()
    migrate.run(engine)
    c = _counts()
    assert c == {"umowy": 0, "osoby": 0, "spolki": 0, "zdarzenia": 0}
    with SessionLocal() as db:
        assert db.query(Company).count() == 0
        assert db.get(SystemFlag, migrate.CLEAN_START_FLAG) is not None
    # drugie uruchomienie nic nie kasuje: tworzymy konto od zera i sprawdzamy, że przetrwa
    client.cookies.clear()
    r = post(client, "/start", "/start", {"firma": "Nowa Firma sp. z o.o.", "imie": "Ewa", "nazwisko": "Nowa", "email": "ewa@firma.pl", "haslo": "haslo-testowe-123"})
    assert r.status_code == 303
    migrate.run(engine)
    with SessionLocal() as db:
        assert db.query(User).count() == 1 and db.query(Company).count() == 1
    # pierwsze uruchomienie przebiega od nowa: /logowanie przy braku kont odsyła na /start
    with SessionLocal() as db:
        db.query(User).delete()
        db.query(Company).delete()
        db.commit()
    client.cookies.clear()
    r = client.get("/logowanie", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/start"


def test_demo_struktura_portfela_i_marze_w_widelkach(client):
    """Proporcje i marże z wytycznych właścicielki (10.11.2026): 17% do 50 MWh, 49% 50–300,
    11% 300–1000 MWh, 23% powyżej 1 GWh; marże zależne od wolumenu."""
    from app.exchange.demo import demo_rows
    rows = demo_rows()
    umowy = rows["umowy"]
    assert len(umowy) == 100
    vol = [float(u["wolumen_roczny_mwh"]) for u in umowy]
    assert sum(v <= 50 for v in vol) == 17
    assert sum(50 < v <= 300 for v in vol) == 49
    assert sum(300 < v <= 1000 for v in vol) == 11
    assert sum(v > 1000 for v in vol) == 23
    for u in umowy:
        v, m = float(u["wolumen_roczny_mwh"]), float(u["narzut_zl_mwh"])
        if v <= 50:
            assert 100 <= m <= 150, u
        elif v <= 500:
            assert 90 <= m <= 120, u
        elif v <= 1000:
            assert 60 <= m <= 70, u
        elif v <= 10000:
            assert 30 <= m <= 50, u
        else:
            assert 8 <= m <= 15, u
    assert sum(v > 10000 for v in vol) >= 1  # jest co najmniej jedna bardzo duża umowa
    assert len({u["klient_nazwa"] for u in umowy}) == 100  # klienci się nie powtarzają
    # zespół: menedżer Michał Lex, 6 handlowców, 2 osoby BOK (Jessica na pierwszym miejscu)
    team = rows["zespol"]
    assert [(p["imie"], p["nazwisko"]) for p in team if p["rola"] == "menedzer"] == [("Michał", "Lex")]
    assert len([p for p in team if p["rola"] == "handlowiec"]) == 6
    assert [(p["imie"], p["nazwisko"]) for p in team if p["rola"] == "bok"] == [("Jessica", "Kowal"), ("Joanna", "Dąbrowska")]
    # każdy sprzedawca ma co najmniej jedną umowę, a najgorszy portfel to Paweł Kamiński
    per = {}
    for u in umowy:
        per.setdefault(u["handlowiec_email"], []).append(u["status"])
    assert all(len(v) >= 1 for v in per.values()) and len(per) == 7
    worst = max(per, key=lambda e: per[e].count("Zerwana"))
    assert worst.startswith("pawel.kaminski")


def test_wynik_importu_ma_plik_z_haslami_do_pobrania(client):
    """Hasła pokazują się raz, ale właścicielka może je od razu zapisać do pliku
    (link z danymi w samej stronie, serwer niczego nie przechowuje)."""
    from urllib.parse import unquote
    setup_company(client)
    login(client, "kris@firma.pl")
    bid = _demo_preview(client)
    r = _commit(client, bid)
    m = re.search(r'<a download="hasla-kont-\d+\.txt" href="data:text/plain;charset=utf-8,([^"]+)">Pobierz hasła', r.text)
    assert m, "brak linku do pobrania haseł"
    plik = unquote(m.group(1))
    for email, pw in re.findall(r"Login: ([^<]+)</p>\s*<p>Hasło: <code>([^<]+)</code>", r.text):
        assert f"Login: {email}\nHasło: {pw}\n" in plik
    assert "jessica.kowal@demo.invalid" in plik and "michal.lex@demo.invalid" in plik
    # po odświeżeniu haseł nie ma nigdzie na serwerze
    assert "Hasło:" not in client.get(f"/konto/import/{bid}").text
