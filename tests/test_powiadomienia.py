"""Powiadomienia i dziennik firmy, etap N1 (docs/PROJEKT-POWIADOMIENIA.md)."""
import re
from datetime import date, timedelta

from app.db import SessionLocal
from app.models import NipCheck, Notification

from .conftest import csrf_of, login, post
from .test_app import CONTRACT, PW, setup_company
from .test_faktury import _png
from .test_klienci import _bok, _klient


def _mine(email):
    with SessionLocal() as db:
        from app.models import User
        uid = db.query(User).filter_by(email=email).one().id
        return [(n.kind, n.text) for n in db.query(Notification).filter_by(recipient_id=uid).order_by(Notification.id)]


def _nip_flow(client):
    """Hania wysyła NIP do BOK, Basia (BOK) rezerwuje. Zwraca numer klienta."""
    setup_company(client)
    _bok(client)
    login(client, "hania@firma.pl")
    cid = _klient(client)
    r = post(client, f"/klienci/{cid}", f"/klienci/{cid}/bok", {"spolka": "2"})
    assert r.status_code == 303
    return cid


def test_nip_do_bok_i_wynik_trafiaja_do_wlasciwych_osob(client):
    cid = _nip_flow(client)
    assert _mine("basia@firma.pl") == [("nip_nowe", "Nowe NIP-y do sprawdzenia: Wózki Widłowe Michalski, 1 spółka.")]
    assert _mine("hania@firma.pl") == []  # bez powiadomień o własnym ruchu
    assert _mine("marek@firma.pl") == [] and _mine("olek@firma.pl") == [] and _mine("kris@firma.pl") == []
    # znacznik w belce u BOK: tekst czytany przez czytnik, nie sam kolor
    login(client, "basia@firma.pl")
    page = client.get("/bok").text
    assert re.search(r'href="/powiadomienia"[^>]*>Powiadomienia<span class="licznik">, 1 nowe</span>', page)
    with SessionLocal() as db:
        kid = db.query(NipCheck).one().id
    until = (date.today() + timedelta(days=10)).isoformat()
    r = post(client, "/bok", f"/bok/{kid}", {"wynik": "zarezerwowany", "do": until, "uwagi": ""})
    assert r.status_code == 303
    got = _mine("hania@firma.pl")
    assert len(got) == 1 and got[0][0] == "nip_wynik"
    assert got[0][1].startswith("Spółka B, klient Wózki Widłowe Michalski: wolny, zarezerwowany dla nas do ")
    # lista: oznaczone jako nowe, po wejściu znacznik znika, link prowadzi do karty klienta
    login(client, "hania@firma.pl")
    assert ", 1 nowe" in client.get("/dzien").text
    page = client.get("/powiadomienia").text
    assert "Nowe: Spółka B" in page and "Nowych od ostatniej wizyty: 1" in page and "od: Basia Bok" in page
    assert 'class="licznik"' not in client.get("/dzien").text
    nid = int(re.search(r'href="/powiadomienia/(\d+)"', page).group(1))
    r = client.get(f"/powiadomienia/{nid}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/klienci/{cid}"
    with SessionLocal() as db:
        n = db.get(Notification, nid)
        assert n.seen_at and n.read_at and n.created_at <= n.seen_at <= n.read_at
    # cudze powiadomienie: 404, bez zapisu odczytu
    login(client, "olek@firma.pl")
    assert client.get(f"/powiadomienia/{nid}").status_code == 404


def test_faktury_do_bok_i_z_powrotem(client):
    setup_company(client)
    _bok(client)
    login(client, "hania@firma.pl")
    cid = _klient(client)
    token = csrf_of(client.get(f"/klienci/{cid}").text)
    r = client.post(f"/klienci/{cid}/faktury-bok", data={"csrf": token},
                    files=[("zdjecia", ("f1.png", _png(), "image/png"))], follow_redirects=False)
    assert r.status_code == 303
    assert _mine("basia@firma.pl") == [("faktury_nowe", "Nowe faktury do wprowadzenia: Wózki Widłowe Michalski.")]
    with SessionLocal() as db:
        from app.models import InvoiceTask
        tid = db.query(InvoiceTask).one().id
    login(client, "basia@firma.pl")
    r = post(client, f"/bok/faktury/{tid}", f"/bok/faktury/{tid}/zamknij", {"wynik": "anuluj", "uwagi": "Zdjęcie nieostre, prześlij jeszcze raz."})
    assert r.status_code == 303
    assert _mine("hania@firma.pl") == [("faktury_gotowe", "BOK nie odczytał faktur klienta Wózki Widłowe Michalski: Zdjęcie nieostre, prześlij jeszcze raz.")]


def test_umowa_menedzer_bok_status_i_zerwanie_do_wlasciciela(client):
    setup_company(client)
    _bok(client)
    login(client, "hania@firma.pl")
    r = post(client, "/umowy/nowa", "/umowy/nowa", CONTRACT)
    assert r.status_code == 303
    uid = r.headers["location"].rsplit("/", 1)[1]
    assert _mine("marek@firma.pl") == [("umowa_podpisana", "Podpisana umowa: Hania Handlowiec, klient Piekarnia Kowalski, Spółka A.")]
    assert _mine("basia@firma.pl") == [("umowa_do_przygotowania", "Umowa do przygotowania: klient Piekarnia Kowalski, Spółka A, handlowiec: Hania Handlowiec.")]
    assert _mine("hania@firma.pl") == [] and _mine("olek@firma.pl") == [] and _mine("kris@firma.pl") == []
    # BOK zmienia status: handlowiec i menedżer
    login(client, "basia@firma.pl")
    r = post(client, f"/umowy/{uid}", f"/umowy/{uid}/status", {"status": "Weryfikacja spółki", "data": date.today().isoformat()})
    assert r.status_code == 303, r.text
    assert _mine("hania@firma.pl")[-1] == ("umowa_status", "Umowa z klientem Piekarnia Kowalski: status „Weryfikacja spółki” (wcześniej „Umowa podpisana”).")
    assert _mine("marek@firma.pl")[-1][0] == "umowa_status"
    assert _mine("kris@firma.pl") == []
    # zerwanie: pilne, także właściciel
    r = post(client, f"/umowy/{uid}", f"/umowy/{uid}/status", {"status": "Zerwana", "data": date.today().isoformat(), "notatka": "Klient wycofał pełnomocnictwo"})
    assert r.status_code == 303, r.text
    for who in ("hania@firma.pl", "marek@firma.pl", "kris@firma.pl"):
        kind, text = _mine(who)[-1]
        assert kind == "umowa_problem" and "Powód: Klient wycofał pełnomocnictwo" in text
    login(client, "kris@firma.pl")
    assert "Nowe, pilne: Umowa z klientem Piekarnia Kowalski" in client.get("/powiadomienia").text


def test_tresc_powiadomien_bez_danych_poufnych(client):
    setup_company(client)
    _bok(client)
    login(client, "hania@firma.pl")
    post(client, "/umowy/nowa", "/umowy/nowa", CONTRACT)
    with SessionLocal() as db:
        texts = " ".join(n.text for n in db.query(Notification))
    assert texts
    for secret in ("zł", "%", "38 500", "77", "prowizj", "marż", "udział"):
        assert secret not in texts, secret


def test_dziennik_firmy_tylko_wlasciciel_z_filtrami_i_bez_usuwania(client):
    _nip_flow(client)
    login(client, "basia@firma.pl")
    assert client.get("/konto/dziennik").status_code == 403
    login(client, "hania@firma.pl")
    assert client.get("/konto/dziennik").status_code == 403
    assert "Dziennik firmy" not in client.get("/konto").text
    login(client, "kris@firma.pl")
    page = client.get("/konto/dziennik").text
    assert "Dziennik firmy: 1 wpis" in page and "Do:</strong> Basia Bok. <strong>Rola:</strong> Biuro obsługi (BOK)" in page and "Od:</strong> Hania Handlowiec" in page
    assert "Zobaczone:</strong> jeszcze nie" in page
    # filtry w adresie; literówki nie wywracają strony
    assert "Dziennik firmy: 0 wpisów" in client.get("/konto/dziennik?rodzaj=umowa_status").text
    assert "Dziennik firmy: 1 wpis" in client.get("/konto/dziennik?rodzaj=nip_nowe&od=2020-01-01").text
    assert client.get("/konto/dziennik?osoba=²&od=2026-13-45&rodzaj=xyz").status_code == 200
    # nie ma żadnej trasy do edycji ani usuwania wpisów
    from app.main import app
    paths = [getattr(r, "path", "") for r in app.routes]
    assert not [p for p in paths if "powiadomienia" in p and any(w in p for w in ("usun", "edytuj", "zmien"))]


def test_cofniecie_demo_zostawia_wpisy_w_dzienniku(client):
    """Dziennik nieusuwalny: po cofnięciu demo wpisy zostają z imieniem z chwili zapisu."""
    from app.exchange.importer import revert
    from app.models import ImportBatch, User
    from app import powiadomienia as pw
    setup_company(client)
    with SessionLocal() as db:
        batch = ImportBatch(status="zatwierdzony", filename="demo.xlsx")
        db.add(batch)
        db.flush()
        u = User(email="demo@firma.pl", name="Demo Osoba", password_hash="x", role="handlowiec", import_batch_id=batch.id)
        db.add(u)
        db.flush()
        pw.notify(db, [u], "umowa_status", "Umowa z klientem Test: status „Start dostaw”.")
        db.commit()
        revert(db, batch)
        n = db.query(Notification).one()
        assert n.recipient_id is None and n.recipient_name == "Demo Osoba"


def test_nowe_brzmienie_kroku_po_ofercie_i_podmiana_starego_tekstu(client):
    """14.11.2026: „Zadzwoń i sprawdź, co ze złożoną ofertą”; stary tekst w bazie podmieniany przy starcie."""
    from app import migrate
    from app.db import engine
    from app.models import Client
    cid = _nip_flow(client)
    with SessionLocal() as db:
        db.get(Client, cid).next_step = migrate.OLD_FOLLOWUP
        db.commit()
    migrate.run(engine)
    with SessionLocal() as db:
        assert db.get(Client, cid).next_step == "Zadzwoń i sprawdź, co ze złożoną ofertą"


def test_karta_handlowca_mowi_kto_jest_menedzerem(client):
    """14.11.2026: zamiast samego „Zespół: Marek Menedżer” — „w zespole menedżera: …”."""
    setup_company(client)
    login(client, "kris@firma.pl")
    page = client.get("/zespol").text
    assert "Handlowiec w zespole menedżera: Marek Menedżer" in page and "zespół: Marek" not in page
    with SessionLocal() as db:
        from app.models import User
        hid = db.query(User).filter_by(email="hania@firma.pl").one().id
    page = client.get(f"/zespol/{hid}").text
    assert "<dt>W zespole menedżera</dt><dd>Marek Menedżer</dd>" in page
