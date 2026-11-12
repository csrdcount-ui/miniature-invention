"""Cenniki: budowa, formularz BOK, zatwierdzenie, cena bazowa dla okresu umowy, kalkulator."""
from datetime import date, timedelta
from decimal import Decimal as D

import pytest

from app import cenniki as cn
from app.db import SessionLocal
from app.models import NipCheck, PriceItem, PriceList, PriceTemplate

from .conftest import login, post
from .test_app import setup_company
from .test_klienci import NIP_A, _bok, _klient


def _tpl(**kw):
    base = dict(products="fix", periods="2027, 2028, 2027-2028", split="grupy", segments="C11:1, C12a:2",
                oh_mode="z_doplata", max_volume_mwh=D(2000), individual_from_mwh=D(1000))
    base.update(kw)
    return PriceTemplate(**base)


def _list(items):
    pl = PriceList(status="zatwierdzony", valid_from=date(2026, 11, 1))
    pl.items = [PriceItem(kind=k, product=p, period=per, segment=s, zone=z, value=D(v)) for k, p, per, s, z, v in items]
    return pl


PRICES = [
    ("cena", "fix", "2027", "C11", 1, "500"), ("cena", "fix", "2028", "C11", 1, "520"),
    ("cena", "fix", "2027", "C12a", 1, "600"), ("cena", "fix", "2027", "C12a", 2, "450"),
    ("cena", "fix", "2028", "C12a", 1, "610"), ("cena", "fix", "2028", "C12a", 2, "460"),
    ("cena", "fix", "2027-2028", "C11", 1, "505"),
    ("oh", "", "", "C11", 0, "15"),
]


def test_okresy_i_podzial_parsowanie_z_bledami_po_polsku():
    assert [p.label for p in cn.parse_periods("2028, 2027-2029 ,2027")] == ["2027", "2027-2029", "2028"]
    with pytest.raises(cn.BusinessError, match="blok lat"):
        cn.parse_periods("2027/2028")
    segs = cn.parse_segments("wolumen", "300-1000, 0-300")
    assert [s.key for s in segs] == ["0-300", "300-1000"]
    with pytest.raises(cn.BusinessError, match="liczba stref"):
        cn.parse_segments("grupy", "C12a:5")


def test_srednia_wazona_z_lat_i_blok_wygrywa_gdy_pasuje():
    tpl, pl = _tpl(), _list(PRICES)
    # 2027-01..2028-12: blok 2027-2028 pasuje dokładnie
    b = cn.base_for(tpl, pl, product="fix", group="C11", volume=D(100), start=date(2027, 1, 1), months=24)
    assert b.zones == [D(505)] and b.how == "blok 2027-2028" and b.oh == D(15)
    # C12a nie ma bloku: średnia ważona 2027 (6 mies.) i 2028 (6 mies.)
    b = cn.base_for(tpl, pl, product="fix", group="C12a", volume=D(100), start=date(2027, 7, 1), months=12)
    assert b.zones == [D("605.00"), D("455.00")] and "2027 (6 mies.)" in b.how
    # brak roku 2029
    b = cn.base_for(tpl, pl, product="fix", group="C11", volume=D(100), start=date(2028, 7, 1), months=12)
    assert "brak ceny na: 2029" in b.error
    # ponad zakres cennika i podpowiedź o wycenie indywidualnej
    assert "wycena indywidualna" in cn.base_for(tpl, pl, product="fix", group="C11", volume=D(2500), start=date(2027, 1, 1), months=12).error
    assert "wycenę indywidualną" in cn.base_for(tpl, pl, product="fix", group="C11", volume=D(1500), start=date(2027, 1, 1), months=12).warning


def test_przedzialy_wolumenu():
    tpl = _tpl(split="wolumen", segments="0-300, 300-1000", periods="2027")
    pl = _list([("cena", "fix", "2027", "0-300", 1, "525"), ("cena", "fix", "2027", "300-1000", 1, "517")])
    assert cn.base_for(tpl, pl, product="fix", group="", volume=D(300), start=date(2027, 1, 1), months=12).zones == [D(525)]
    assert cn.base_for(tpl, pl, product="fix", group="", volume=D(301), start=date(2027, 1, 1), months=12).zones == [D(517)]


def _budowa(client, **over):
    data = {"produkty": "fix", "okresy": "2027, 2028, 2027-2028", "podzial": "grupy", "segmenty": "C11:1, C12a:2",
            "oh": "z_doplata", "zakres": "2000", "indywidualna": "", "uwagi": ""}
    data.update(over)
    return post(client, "/cenniki/1/budowa", "/cenniki/1/budowa", data)


def _ceny(client, od=None, shift=0):
    data = {"od": (od or date.today()).isoformat(), "do": "", "uwagi": ""}
    for k, p, per, s, z, v in PRICES:
        key = cn.oh_key(s) if k == "oh" else cn.price_key(p, per, s, z)
        data[key] = str(D(v) + shift) if k == "cena" else v
    return post(client, "/cenniki/1/nowy", "/cenniki/1/nowy", data)


def test_bok_ustawia_budowe_wpisuje_ceny_i_zatwierdza(client):
    setup_company(client)
    _bok(client)
    login(client, "hania@firma.pl")
    assert client.get("/cenniki").status_code == 403  # handlowiec nie wpisuje cen
    login(client, "basia@firma.pl")
    page = client.get("/cenniki").text
    assert "Spółka A" in page and "Ustaw budowę cennika" in page
    r = _budowa(client, okresy="2027/2028")
    assert r.status_code == 400 and "blok lat" in r.text
    assert _budowa(client).status_code == 303
    form = client.get("/cenniki/1/nowy").text
    assert "2027, C12a, strefa II, zł/MWh" in form and "Opłata handlowa, C11, zł na miesiąc za punkt poboru" in form
    r = post(client, "/cenniki/1/nowy", "/cenniki/1/nowy", {"od": date.today().isoformat(), cn.price_key("fix", "2027", "C11", 1): "abc"})
    assert r.status_code == 400 and "to nie jest liczba" in r.text
    r = _ceny(client)
    assert r.status_code == 303
    pid = int(r.headers["location"].rsplit("/", 1)[1])
    page = client.get(f"/cenniki/projekt/{pid}").text
    assert "to pierwszy cennik tej spółki" in page and "Zatwierdź cennik" in page
    with SessionLocal() as db:
        assert cn.current_list(db, 1) is None  # projekt nie trafia do kalkulatora
    post(client, f"/cenniki/projekt/{pid}", f"/cenniki/projekt/{pid}/zatwierdz", {})
    with SessionLocal() as db:
        assert cn.current_list(db, 1).id == pid
    # następny cennik: formularz wypełniony poprzednimi cenami, zmiany widoczne przed zatwierdzeniem
    assert 'value="505"' in client.get("/cenniki/1/nowy").text.replace("505,00", "505")
    r = _ceny(client, shift=10)
    pid2 = int(r.headers["location"].rsplit("/", 1)[1])
    page = client.get(f"/cenniki/projekt/{pid2}").text
    assert "zmienionych: 7" in page and "→ <strong>510" in page
    post(client, f"/cenniki/projekt/{pid2}", f"/cenniki/projekt/{pid2}/zatwierdz", {})
    with SessionLocal() as db:
        assert db.get(PriceList, pid).valid_to == date.today()  # poprzedni działa do końca dnia
        assert cn.current_list(db, 1).id == pid2


def test_kalkulator_z_cennika_strefy_oplata_handlowa_i_oferta(client):
    setup_company(client)
    _bok(client)
    login(client, "basia@firma.pl")
    _budowa(client)
    r = _ceny(client)
    pid = int(r.headers["location"].rsplit("/", 1)[1])
    post(client, f"/cenniki/projekt/{pid}", f"/cenniki/projekt/{pid}/zatwierdz", {})
    login(client, "hania@firma.pl")
    cid = _klient(client)
    with SessionLocal() as db:
        db.add(NipCheck(client_id=cid, supplier_id=1, result="zarezerwowany", reserved_until=date.today() + timedelta(days=30)))
        db.commit()
    # C12a, 2 strefy, każda ze swoją marżą; udział 60/40
    url = (f"/klienci/{cid}/kalkulator?produkt=fix&grupa=C12a&wolumen=100&start=2027-01&okres=12"
           "&cena_1=700&udzial_1=60&cena_2=520&udzial_2=40&oh=40&punkty=2")
    page = client.get(url).text.replace(" ", " ")
    assert "Strefa I: cena bazowa 600,00 zł, dla klienta 700,00 zł, marża <strong>100,00 zł/MWh</strong>" in page
    assert "Strefa II: cena bazowa 450,00 zł, dla klienta 520,00 zł, marża <strong>70,00 zł/MWh</strong>" in page
    # marża średnia 88 zł x 100 MWh x 1 rok = 8 800; Hania 40% = 3 520
    # prowizja: 40% z 8 800 = 3 520 plus 40% z dopłaty do OH (960) = 384, razem 3 904
    assert "Masa marży: 8 800,00 zł" in page and "Twoja prowizja: <strong>3 904,00 zł</strong>" in page
    # C12a nie ma OH w cenniku testowym: bazowa 0, dopłata 40 zł x 12 mies. x 2 punkty
    assert "960,00 zł w całym okresie, z tego Twoja prowizja 384,00 zł" in page
    assert "77" not in page.split("Wynik", 1)[1].split("Oferty specjalne", 1)[0]  # bez udziału brokera
    assert "Oferty specjalne" in page
    # ponad limit spółki A (200 zł/MWh)
    page = client.get(url.replace("cena_1=700", "cena_1=900")).text
    assert "Marża ponad limit spółki" in page
    # przepisanie do oferty na karcie klienta
    assert "z_kalkulatora=1&spolka=1" in client.get(url).text
    page = client.get(f"/klienci/{cid}?z_kalkulatora=1&spolka=1&produkt=fix&cena_bazowa=540.00&marza=88.00&wolumen=100&okres=12").text
    assert "Dane przepisane z kalkulatora" in page and 'value="88.00"' in page


def test_kalkulator_bez_cennika_i_cennik_zmieniony_dzis(client):
    setup_company(client)
    _bok(client)
    login(client, "hania@firma.pl")
    cid = _klient(client)
    page = client.get(f"/klienci/{cid}/kalkulator?produkt=fix&wolumen=100&start=2027-01&okres=12&cena_1=600&wszystkie=1").text
    assert "Brak zatwierdzonego cennika" in page
    login(client, "basia@firma.pl")
    _budowa(client)
    for od in (date.today() - timedelta(days=3), date.today()):
        r = _ceny(client, od=od)
        pid = int(r.headers["location"].rsplit("/", 1)[1])
        post(client, f"/cenniki/projekt/{pid}", f"/cenniki/projekt/{pid}/zatwierdz", {})
    login(client, "hania@firma.pl")
    page = client.get(f"/klienci/{cid}/kalkulator?produkt=fix&grupa=C11&wolumen=100&start=2027-01&okres=24&cena_1=600&wszystkie=1").text
    assert "Cennik zmienił się dziś" in page and "blok 2027-2028" in page


def test_demo_ma_cenniki_i_cofniecie_je_usuwa(client):
    from .test_import import _commit, _demo_preview
    setup_company(client)
    login(client, "kris@firma.pl")
    bid = _demo_preview(client)
    assert "Cenniki spółek (ceny fikcyjne): 13" in client.get(f"/konto/import/{bid}").text
    _commit(client, bid)
    with SessionLocal() as db:
        assert db.query(PriceTemplate).count() == 12 and db.query(PriceList).count() == 13
    page = client.get("/cenniki").text
    assert "Brak obowiązującego cennika" in page
    post(client, f"/konto/import/{bid}", f"/konto/import/{bid}/cofnij", {"potwierdzam": "1"})
    with SessionLocal() as db:
        assert db.query(PriceTemplate).count() == 0 and db.query(PriceList).count() == 0 and db.query(PriceItem).count() == 0


def test_ceny_demo_z_rynku_plus_40_45_zl_i_blok_jako_srednia():
    from app.exchange.demo import MARKET_BASE
    assert MARKET_BASE[2027] == D("551.20") and MARKET_BASE[2028] == D("530.00")


def test_dopisanie_cennikow_demo_do_wczesniej_wczytanego_demo(client):
    """Serwer miał demo wczytane przed cennikami: przycisk dopisuje je bez ruszania reszty."""
    from .test_import import _commit, _demo_preview
    from app.models import Contract, Supplier
    setup_company(client)
    login(client, "kris@firma.pl")
    bid = _demo_preview(client)
    _commit(client, bid)
    with SessionLocal() as db:  # stan jak na serwerze: demo bez cenników
        for pl_ in db.query(PriceList): db.delete(pl_)
        for t in db.query(PriceTemplate): db.delete(t)
        db.commit()
        umowy = db.query(Contract).count()
    page = client.get("/konto/import").text
    assert "Dodaj cenniki demo" in page and "12 spółek demo nie ma" in page
    r = post(client, "/konto/import", "/konto/import/demo-cenniki", {})
    assert r.status_code == 303
    with SessionLocal() as db:
        assert db.query(PriceTemplate).count() == 12 and db.query(PriceList).count() == 13
        assert db.query(Contract).count() == umowy
        sup_before = db.query(Supplier).count()
    page = client.get("/konto/import").text
    assert "Dodaj cenniki demo" not in page  # nic do dopisania
    post(client, "/konto/import", "/konto/import/demo-cenniki", {})  # drugi raz: bez duplikatów
    with SessionLocal() as db:
        assert db.query(PriceTemplate).count() == 12 and db.query(PriceList).count() == 13
    post(client, f"/konto/import/{bid}", f"/konto/import/{bid}/cofnij", {"potwierdzam": "1"})
    with SessionLocal() as db:
        assert db.query(PriceTemplate).count() == 0 and db.query(PriceItem).count() == 0


def test_cenniki_demo_sieguja_2_do_5_lat_wiekszosc_3_do_5(client):
    """Zgłoszenie 11.11.2026: po filtrze na 4 lata zostawał jeden wynik, bo demo miało tylko 2027–2028."""
    from .test_import import _commit, _demo_preview
    setup_company(client)
    login(client, "kris@firma.pl")
    _commit(client, _demo_preview(client))
    with SessionLocal() as db:
        def ile(months):
            n = 0
            for t in db.query(PriceTemplate):
                pl_ = cn.current_list(db, t.supplier_id)
                if not pl_:
                    continue
                b = cn.base_for(t, pl_, product="fix", group="C11" if t.split == "grupy" else "", volume=D(100),
                                start=date(2027, 1, 1), months=months)
                n += 0 if b.error else 1
            return n
        z = {m: ile(m * 12) for m in (2, 3, 4, 5, 6)}
        # 11 z 12 spółek ma cennik na dziś (jeden wygasł); wymagamy rozsądnego rozkładu zasięgu
        assert z[2] >= 10 and z[3] >= 8 and z[4] >= 5 and z[5] >= 2 and z[6] == 0, z
        assert z[2] >= z[3] >= z[4] >= z[5]
        assert all("założenie demonstracyjne" in (p.note or "") for p in db.query(PriceList))


def test_podmiana_cennikow_demo_zmienia_stare_na_nowy_wzor(client):
    from .test_import import _commit, _demo_preview
    from app.models import Contract
    setup_company(client)
    login(client, "kris@firma.pl")
    bid = _demo_preview(client)
    _commit(client, bid)
    with SessionLocal() as db:  # stary wzór: tylko 2027–2028
        for t in db.query(PriceTemplate):
            t.periods = "2027, 2028, 2027-2028"
        for it in db.query(PriceItem).filter(PriceItem.period.in_(["2029", "2030", "2031"])): db.delete(it)
        db.commit()
        umowy = db.query(Contract).count()
    assert "Podmień cenniki demo" in client.get("/konto/import").text
    r = post(client, "/konto/import", "/konto/import/demo-cenniki", {"zastap": "1"})
    assert r.status_code == 303
    with SessionLocal() as db:
        assert db.query(PriceTemplate).count() == 12 and db.query(PriceList).count() == 13
        assert db.query(PriceItem).filter(PriceItem.period == "2030").count() > 0
        assert db.query(Contract).count() == umowy


def test_zostaja_dwa_cenniki_obowiazujacy_i_poprzedni_reszta_usuwana(client):
    """Zasada właścicielki 13.11.2026: tylko obowiązujący i poprzedni; umowy i oferty mają własne ceny."""
    from app.models import Contract, Supplier
    from .test_import import _commit, _demo_preview
    setup_company(client)
    login(client, "kris@firma.pl")
    _commit(client, _demo_preview(client))
    today = date.today()
    with SessionLocal() as db:
        sid = db.query(PriceTemplate).filter(PriceTemplate.split == "grupy").first().supplier_id
        db.query(PriceList).filter(PriceList.supplier_id == sid).delete()  # czysty start dla tej spółki
        for i, days in enumerate((40, 30, 20, 10)):  # cztery starsze zatwierdzone cenniki
            db.add(PriceList(supplier_id=sid, status="zatwierdzony", valid_from=today - timedelta(days=days),
                             valid_to=today - timedelta(days=days - 10), note=f"stary {i}",
                             items=[PriceItem(kind="cena", product="fix", period="2027", segment="C11", zone=1, value=D(500 + i))]))
        db.add(PriceList(supplier_id=sid, status="zatwierdzony", valid_from=today + timedelta(days=5), note="przyszły",
                         items=[PriceItem(kind="cena", product="fix", period="2027", segment="C11", zone=1, value=D(600))]))
        db.commit()
        umowy = [(c.id, c.base_price_pln_mwh, c.markup_pln_mwh) for c in db.query(Contract)]
    # nowy projekt, zatwierdzony przez stronę
    r = post(client, f"/cenniki/{sid}/nowy", f"/cenniki/{sid}/nowy", {
        "od": today.isoformat(), cn.price_key("fix", "2027", "C11", 1): "555"})
    assert r.status_code == 303, r.text
    pid = int(r.headers["location"].rsplit("/", 1)[1])
    r = post(client, f"/cenniki/projekt/{pid}", f"/cenniki/projekt/{pid}/zatwierdz", {})
    assert r.status_code == 303
    with SessionLocal() as db:
        notes = sorted((p.valid_from, p.note or "") for p in db.query(PriceList).filter(PriceList.supplier_id == sid, PriceList.status == "zatwierdzony"))
        # zostają: dwa najnowsze z już obowiązujących (nowy z dziś i „stary 3”), oraz przyszły
        assert len(notes) == 3 and notes[0][1] == "stary 3" and notes[-1][1] == "przyszły", notes
        assert db.query(PriceItem).join(PriceList).filter(PriceList.supplier_id == sid).count() == 3  # pozycje usuniętych znikają razem z nimi
        assert [(c.id, c.base_price_pln_mwh, c.markup_pln_mwh) for c in db.query(Contract)] == umowy
        assert cn.current_list(db, sid).note != "stary 3"
    # kolejne zatwierdzenie nie usuwa dalej niż zasada każe i nie tyka projektu w toku
    with SessionLocal() as db:
        assert cn.prune_old_lists(db, sid) == 0


def test_przycinanie_nie_rusza_projektu_ani_cennika_wygaslego_bez_nastepcy():
    from app.db import Base, engine
    Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine)
    from app.models import Supplier
    today = date.today()
    with SessionLocal() as db:
        s = Supplier(name="Spółka X"); db.add(s); db.flush()
        db.add(PriceList(supplier_id=s.id, status="zatwierdzony", valid_from=today - timedelta(days=12), valid_to=today - timedelta(days=5)))
        db.add(PriceList(supplier_id=s.id, status="projekt", valid_from=today))
        db.commit()
        assert cn.prune_old_lists(db, s.id) == 0  # wygasły cennik zostaje: alarm „cennik wygasł” go potrzebuje
        assert db.query(PriceList).filter(PriceList.supplier_id == s.id).count() == 2
