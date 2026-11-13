"""Punkty poboru, wolumen z faktur, profil, „odeślij do BOK” ze zdjęciami, marszruta klienta."""
import re
from datetime import date, timedelta
from decimal import Decimal as D
from io import BytesIO

from app import faktury as fk
from app.db import SessionLocal
from app.models import InvoicePhoto, InvoiceReading, InvoiceTask, MeteringPoint

from .conftest import csrf_of, login, post
from .test_app import setup_company
from .test_klienci import _bok, _klient


def _r(od, do, zuzycie=None, l_od=None, l_do=None):
    return InvoiceReading(period_from=od, period_to=do, consumption_kwh=None if zuzycie is None else D(zuzycie),
                          meter_start=None if l_od is None else D(l_od), meter_end=None if l_do is None else D(l_do))


def _co_dwa_miesiace(start, zuzycia):
    out, d = [], start
    for z in zuzycia:
        nxt = d + timedelta(days=60)
        out.append(_r(d, nxt - timedelta(days=1), z))
        d = nxt
    return out


# --------------------------------------------------------------------------
# Wolumen roczny i profil (metoda właścicielki 13.11.2026)
# --------------------------------------------------------------------------

def test_wolumen_z_szesciu_faktur_i_profil_plaski():
    rs = _co_dwa_miesiace(date(2025, 1, 1), [10000] * 6)  # 360 dni po 10 000 kWh
    v = fk.annual_volume(rs)
    assert v.mwh == D("60.833") and "6 faktur" in v.method and not v.warning
    assert fk.usage_profile(rs).kind == "płaski"


def test_profil_sezonowy():
    rs = _co_dwa_miesiace(date(2025, 1, 1), [16000, 12000, 6000, 5000, 9000, 15000])
    p = fk.usage_profile(rs)
    assert p.kind == "sezonowy" and "najwięcej" in p.text


def test_wolumen_z_dwoch_faktur_oddalonych_o_10_miesiecy_ze_stanow_licznika():
    rs = [_r(date(2025, 1, 1), date(2025, 2, 28), l_od="10000", l_do="12000"),
          _r(date(2025, 11, 1), date(2025, 12, 31), l_od="28000", l_do="30000")]
    v = fk.annual_volume(rs)
    # 20 000 kWh w 364 dni (1.01–31.12) -> rocznie ok. 20,055 MWh
    assert v.mwh == D("20.055") and "stanów licznika" in v.method


def test_za_malo_danych_i_bledy():
    krotko = [_r(date(2025, 1, 1), date(2025, 2, 28), "5000", "1000", "6000")]
    assert fk.annual_volume(krotko).mwh is None and "10 miesięcy" in fk.annual_volume(krotko).error
    malejacy = [_r(date(2025, 1, 1), date(2025, 2, 28), l_od="9000", l_do="9500"),
                _r(date(2025, 11, 1), date(2025, 12, 31), l_od="100", l_do="400")]
    assert "wymiana licznika" in fk.annual_volume(malejacy).error
    assert "za mało" in fk.usage_profile(krotko).text.lower() or "od 4 faktur" in fk.usage_profile(krotko).text


def test_rozne_wyniki_metod_daja_ostrzezenie():
    rs = _co_dwa_miesiace(date(2025, 1, 1), [10000] * 6)
    rs[0].meter_start, rs[-1].meter_end = D("0"), D("90000")  # licznik pokazuje dużo więcej niż suma faktur
    assert "sprawdź wpisane liczby" in fk.annual_volume(rs).warning


def test_termin_wypowiedzenia():
    p = MeteringPoint(contract_end=date(2027, 3, 31), notice_months=3)
    assert fk.notice_deadline(p) == date(2026, 12, 31)
    assert fk.notice_deadline(MeteringPoint(contract_end=date(2027, 3, 31))) is None


# --------------------------------------------------------------------------
# Karta klienta: marszruta, punkty poboru, faktury
# --------------------------------------------------------------------------

def _png() -> bytes:
    from PIL import Image
    out = BytesIO()
    Image.new("RGB", (3000, 2000), "white").save(out, "PNG")
    return out.getvalue()


def test_marszruta_ma_cztery_ekrany_i_pasek_etapow(client):
    setup_company(client)
    login(client, "hania@firma.pl")
    cid = _klient(client)
    page = client.get(f"/klienci/{cid}").text
    for sid in ("kontakt", "dane", "teren", "oferta-umowa"):
        assert f'href="#{sid}"' in page and f'id="{sid}"' in page
    assert 'aria-label="Marszruta klienta: ekrany"' in page and 'aria-current="step"' in page
    assert page.count("<h1") == 1 and "1. Kontakt" in page and "4. Oferta i umowa" in page
    ids = re.findall(r' id="([^"]+)"', page)
    assert len(ids) == len(set(ids)), "powtórzone identyfikatory pól"


def test_handlowiec_wpisuje_punkt_i_faktury_wolumen_trafia_do_kalkulatora(client):
    setup_company(client)
    login(client, "hania@firma.pl")
    cid = _klient(client)
    r = post(client, f"/klienci/{cid}", f"/klienci/{cid}/punkty", {
        "ppe": "PL0012345678", "adres": "Lublin, ul. Fabryczna 1", "grupa": "C12a", "sprzedawca": "Obecna Spółka",
        "koniec": "2027-03-31", "wypowiedzenie": "3"})
    assert r.status_code == 303 and r.headers["location"].endswith("#dane")
    with SessionLocal() as db:
        pid = db.query(MeteringPoint).one().id
    start = date(2025, 1, 1)
    for i in range(6):
        od = start + timedelta(days=60 * i)
        r = post(client, f"/klienci/{cid}", f"/klienci/{cid}/punkty/{pid}/faktura", {
            "punkt": str(pid), "od": od.isoformat(), "do": (od + timedelta(days=59)).isoformat(), "zuzycie": "10 000"})
        assert r.status_code == 303, r.text
    page = client.get(f"/klienci/{cid}").text
    assert "Wolumen roczny: <strong>60,833\u00a0MWh</strong>" in page and "Profil płaski" in page
    assert "wypowiedzenie najpóźniej 31.12.2026" in page
    assert f"/klienci/{cid}/kalkulator?wolumen=60.833&amp;grupa=C12a" in page
    # błędny okres: komunikat, nie błąd serwera
    r = post(client, f"/klienci/{cid}", f"/klienci/{cid}/punkty/{pid}/faktura", {"punkt": str(pid), "od": "2025-05-01", "do": "2025-04-01", "zuzycie": "5"})
    assert r.status_code == 400 and "Koniec okresu" in r.text
    # obcy handlowiec nie widzi karty ani nie dopisze danych
    login(client, "olek@firma.pl")
    r = post(client, "/klienci/nowy", f"/klienci/{cid}/punkty", {"ppe": "X"})
    assert r.status_code == 404


def test_zdjecia_faktur_do_bok_bok_wpisuje_dane_i_zamyka_zdjecia_znikaja(client):
    setup_company(client)
    _bok(client)
    login(client, "hania@firma.pl")
    cid = _klient(client)
    token = csrf_of(client.get(f"/klienci/{cid}").text)
    r = client.post(f"/klienci/{cid}/faktury-bok", data={"csrf": token, "uwagi": "punkt w hali"},
                    files=[("zdjecia", ("f1.png", _png(), "image/png")), ("zdjecia", ("f2.pdf", b"%PDF-1.4 test", "application/pdf"))],
                    follow_redirects=False)
    assert r.status_code == 303, r.text
    with SessionLocal() as db:
        t = db.query(InvoiceTask).one()
        tid, photos = t.id, [(p.id, p.content_type, len(p.data)) for p in t.photos]
    assert [c for _, c, _ in photos] == ["image/jpeg", "application/pdf"]
    assert photos[0][2] < 1_000_000  # pomniejszone
    # plik, który nie jest zdjęciem ani PDF-em: komunikat
    token = csrf_of(client.get(f"/klienci/{cid}").text)
    r = client.post(f"/klienci/{cid}/faktury-bok", data={"csrf": token},
                    files=[("zdjecia", ("x.txt", b"nie faktura", "text/plain"))], follow_redirects=False)
    assert r.status_code == 400 and "To nie jest zdjęcie" in r.text
    # obcy handlowiec nie zobaczy zdjęcia
    login(client, "olek@firma.pl")
    assert client.get(f"/bok/faktury/{tid}/zdjecie/{photos[0][0]}").status_code == 404
    assert client.get(f"/bok/faktury/{tid}").status_code == 403
    # BOK: kolejka, zadanie, zdjęcie, wpisanie danych na karcie, zamknięcie
    login(client, "basia@firma.pl")
    assert "Faktury do wprowadzenia: 1" in client.get("/bok").text
    page = client.get(f"/bok/faktury/{tid}").text
    assert 'alt="Faktura, zdjęcie 1 z 2"' in page and "Faktura 2 z 2 (PDF)" in page
    ph = client.get(f"/bok/faktury/{tid}/zdjecie/{photos[0][0]}")
    assert ph.status_code == 200 and ph.headers["content-type"] == "image/jpeg" and "no-store" in ph.headers["cache-control"]
    r = post(client, f"/klienci/{cid}", f"/klienci/{cid}/punkty", {"ppe": "PL001", "grupa": "C11"})
    assert r.status_code == 303
    with SessionLocal() as db:
        pid = db.query(MeteringPoint).one().id
    r = post(client, f"/klienci/{cid}", f"/klienci/{cid}/punkty/{pid}/faktura",
             {"punkt": str(pid), "od": "2025-01-01", "do": "2025-02-28", "licznik_od": "1000", "licznik_do": "3000"})
    assert r.status_code == 303
    r = post(client, f"/bok/faktury/{tid}", f"/bok/faktury/{tid}/zamknij", {"wynik": "zrobione", "uwagi": "wpisane"})
    assert r.status_code == 303
    with SessionLocal() as db:
        t = db.get(InvoiceTask, tid)
        assert t.status == "zrobione" and db.query(InvoicePhoto).count() == 0
        assert db.query(InvoiceReading).one().source == "bok"
    # handlowiec widzi odpowiedź BOK na ekranie dnia
    login(client, "hania@firma.pl")
    assert "dane z faktur gotowe" in client.get("/dzien").text
    page = client.get(f"/klienci/{cid}").text
    assert "BOK wprowadził dane" in page


def test_bok_nie_odsyla_faktur_ale_moze_wpisac_dane(client):
    setup_company(client)
    _bok(client)
    login(client, "hania@firma.pl")
    cid = _klient(client)
    login(client, "basia@firma.pl")
    page = client.get(f"/klienci/{cid}").text
    assert "Dodaj punkt poboru" in page and "Odeślij zdjęcia faktur do BOK" not in page


def test_ai_wylaczone():
    assert fk.extractor() is None
