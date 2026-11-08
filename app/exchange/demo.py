"""Dane demonstracyjne w standardzie wymiany danych.

Spółki obrotu mają prawdziwe nazwy rynkowe, ale warunki umów agencyjnych są fikcyjne.
Osoby i klienci są zmyśleni. Klienci nie mają NIP-ów, żeby żadna prawdziwa firma nie
została powiązana z fikcyjną umową. Daty liczone od dnia wygenerowania pliku.
"""
from __future__ import annotations

import calendar
import random
from datetime import date, timedelta
from typing import Optional

from .standard import build_workbook

DOMAIN = "demo.invalid"

# nazwa, udział brokera, 1. transza, wyzwalacz, limit narzutu, mies. nowych przyłączy, korekta
SUPPLIERS = [
    ("e2V (Ekovoltis)", 75, 30, "weryfikacja", 200, 12, "proporcjonalna"),
    ("ENGIE", 70, 50, "start_dostaw", 180, 12, "proporcjonalna"),
    ("MET Polska", 65, 30, "weryfikacja", 150, 12, "proporcjonalna"),
    ("Enefit", 72, 40, "zmiana_sprzedawcy", 200, 12, "proporcjonalna"),
    ("Polenergia", 68, 30, "start_dostaw", 160, 12, "proporcjonalna"),
    ("Respect Energy", 80, 50, "weryfikacja", 200, 12, "proporcjonalna"),
    ("Enea", 60, 30, "start_dostaw", 120, 12, "proporcjonalna"),
    ("PGE", 62, 30, "start_dostaw", 120, 12, "proporcjonalna"),
    ("Orlen", 64, 30, "zmiana_sprzedawcy", 140, 12, "proporcjonalna"),
    ("Tauron", 61, 30, "start_dostaw", 130, 12, "proporcjonalna"),
    ("Audax", 78, 50, "weryfikacja", 200, 12, "brak"),
    ("Axpo", 74, 40, "weryfikacja", 180, 12, "proporcjonalna"),
]
RULES_FROM = date(2023, 1, 1)

MANAGER = ("Tomasz", "Zieliński", 45, 5)
TRADERS = [  # imię, nazwisko, udział, waga sprzedaży
    ("Anna", "Kowalczyk", 50, 14),
    ("Piotr", "Nowicki", 45, 11),
    ("Katarzyna", "Mazur", 40, 9),
    ("Michał", "Wójcik", 40, 8),
    ("Agnieszka", "Lewandowska", 35, 6),
    ("Paweł", "Kamiński", 35, 6),  # najgorszy portfel: najwięcej zerwań
]
BOK = ("Joanna", "Dąbrowska")

CLIENTS = [
    "Piekarnia Złoty Kłos sp. z o.o.", "Chłodnia Lubelska sp. z o.o.", "Hotel Pod Lipami", "Zakład Mechaniczny Kowalski",
    "Wspólnota Mieszkaniowa ul. Lipowa 12", "Wspólnota Mieszkaniowa ul. Długa 5", "Wspólnota Mieszkaniowa os. Słoneczne",
    "Drukarnia Akant sp. z o.o.", "Tartak Leśny Dwór", "Ogrodnictwo Zielone Pole", "Stolarnia Dąb s.c.",
    "Market Pod Zegarem", "Przetwórnia Owoców Sad", "Myjnia Błysk", "Centrum Logistyczne Wschód sp. z o.o.",
    "Hurtownia Budowlana Fundament", "Galwanizernia Metal-Pol", "Restauracja Stary Młyn", "Szkoła Językowa Lingua",
    "Klinika Weterynaryjna Azor", "Pensjonat Górski Potok", "Serwis Opon Kołowrót", "Zakład Mięsny Kłos",
    "Wytwórnia Lodów Bałtyk", "Pralnia Przemysłowa Biel", "Magazyny Chłodnicze Arktyka", "Przychodnia Zdrowie",
    "Fitness Klub Forma", "Kino Plaza", "Szklarnia Pomidor sp. z o.o.", "Odlewnia Żeliwa Sztaba",
    "Mleczarnia Łąka", "Browar Rzemieślniczy Chmiel", "Tłocznia Soków Jabłonka", "Wspólnota Mieszkaniowa ul. Ogrodowa 3",
    "Warsztat Samochodowy Tłok", "Hotel Nad Jeziorem", "Kamieniarstwo Granit", "Zakład Stolarki PCV Okno",
    "Centrum Handlowe Rynek", "Piekarnia Rumiana Skórka", "Spółdzielnia Ogrodnicza Plon", "Wylęgarnia Drobiu Kurnik",
    "Lakiernia Proszkowa Kolor", "Hala Sportowa Olimp", "Biurowiec Kwadrat", "Fabryka Mebli Komfort sp. z o.o.",
    "Cukiernia Słodki Kącik", "Gospodarstwo Rybne Karp", "Pracownia Ceramiki Glina", "Wspólnota Mieszkaniowa ul. Polna 8",
    "Hotel Biznes Centrum", "Zakład Tworzyw Polimer", "Agencja Reklamowa Baner", "Tłocznia Oleju Rzepak",
    "Przedszkole Niepubliczne Promyk", "Zakład Poligraficzny Druk-Art", "Serwerownia DataLas sp. z o.o.",
    "Sklep Ogrodniczy Konewka", "Producent Opakowań Karton",
]

BREAK_REASONS = [
    "Klient wypowiedział umowę i przeszedł do innego sprzedawcy.",
    "Upadłość klienta.",
    "Klient zamknął działalność w tym punkcie.",
    "Klient zrezygnował po podwyżce opłat dystrybucyjnych.",
]


def _email(first: str, last: str) -> str:
    tr = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")
    return f"{first}.{last}".translate(tr).lower() + "@" + DOMAIN


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _first_of_next_month(d: date) -> date:
    return _add_months(date(d.year, d.month, 1), 1)


def demo_rows(today: Optional[date] = None) -> dict[str, list[dict]]:
    today = today or date.today()
    rng = random.Random(2026)
    rows: dict[str, list[dict]] = {"zespol": [], "spolki": [], "umowy": [], "historia_statusow": []}

    mgr_email = _email(MANAGER[0], MANAGER[1])
    rows["zespol"].append({
        "id_zewn": "DEMO-M-1", "imie": MANAGER[0], "nazwisko": MANAGER[1], "email": mgr_email, "rola": "menedzer",
        "aktywny": "tak", "udzial_w_narzucie_proc": MANAGER[2], "override_proc": MANAGER[3], "baza_override": "narzut",
    })
    for i, (first, last, share, _) in enumerate(TRADERS, start=1):
        rows["zespol"].append({
            "id_zewn": f"DEMO-H-{i}", "imie": first, "nazwisko": last, "email": _email(first, last), "rola": "handlowiec",
            "menedzer_email": mgr_email, "aktywny": "tak", "udzial_w_narzucie_proc": share,
        })
    rows["zespol"].append({
        "id_zewn": "DEMO-B-1", "imie": BOK[0], "nazwisko": BOK[1], "email": _email(*BOK), "rola": "bok", "aktywny": "tak",
    })

    for i, (name, share, tranche, trigger, limit, months, clawback) in enumerate(SUPPLIERS, start=1):
        rows["spolki"].append({
            "id_zewn": f"DEMO-S-{i}", "nazwa": name, "aktywna": "tak", "obowiazuje_od": RULES_FROM.isoformat(),
            "udzial_brokera_proc": share, "pierwsza_transza_proc": tranche, "wyzwalacz_transzy": trigger,
            "limit_narzutu_zl_mwh": limit, "nowe_przylacza_miesiace": months, "tryb_korekty": clawback,
            "uwagi": "Warunki fikcyjne, dane demonstracyjne.",
        })
    # Jedna spółka zmienia warunki w trakcie: widać, że stare umowy zachowują stare reguły.
    rows["spolki"].append({
        "id_zewn": "DEMO-S-12b", "nazwa": "Axpo", "aktywna": "tak", "obowiazuje_od": date(today.year, 1, 1).isoformat(),
        "udzial_brokera_proc": 70, "pierwsza_transza_proc": 30, "wyzwalacz_transzy": "weryfikacja",
        "limit_narzutu_zl_mwh": 160, "nowe_przylacza_miesiace": 12, "tryb_korekty": "proporcjonalna",
        "uwagi": "Nowe, gorsze warunki od początku roku. Warunki fikcyjne.",
    })

    sellers = [(_email(f, l), w) for f, l, _, w in TRADERS] + [(mgr_email, 4)]
    bad = _email("Paweł", "Kamiński")

    # Scenariusze przypisane z góry, reszta to zwykły przebieg.
    scenarios = (["zerwana_zla"] * 4 + ["zerwana"] * 2 + ["utknieta"] * 4 + ["swieza"] * 5
                 + ["nowe_przylacze"] * 5 + ["zakonczona"] * 4)
    scenarios += ["zwykla"] * (len(CLIENTS) - len(scenarios))
    rng.shuffle(scenarios)

    for n, (client, scenario) in enumerate(zip(CLIENTS, scenarios), start=1):
        if scenario == "zerwana_zla":
            seller = bad
        elif scenario == "utknieta" and n % 2 == 0:
            seller = bad
        else:
            seller = rng.choices([e for e, _ in sellers], weights=[w for _, w in sellers])[0]
        sup = rng.choice(SUPPLIERS)
        name, limit = sup[0], sup[4]
        is_gas = rng.random() < 0.15 and "Wspólnota" not in client
        term = rng.choice([12, 24, 36, 36, 48, 60])
        volume = rng.choice([8, 15, 25] if "Wspólnota" in client else [25, 40, 60, 80, 120, 180, 250, 400, 600, 900, 1500])
        base = rng.randrange(220, 301, 5) if is_gas else rng.randrange(480, 621, 5)

        if scenario == "swieza":
            signed = today - timedelta(days=rng.randint(1, 6))
        elif scenario == "utknieta":
            signed = today - timedelta(days=rng.randint(42, 60))
        elif scenario == "zakonczona":
            signed = date(today.year - 2, rng.randint(1, 6), rng.randint(1, 28))
            term = 12
        else:
            signed = today - timedelta(days=rng.randint(60, 900))

        if name == "Axpo" and signed >= date(today.year, 1, 1):
            limit = 160  # nowe reguły Axpo od początku roku
        markup = rng.randrange(40, limit + 1, 5)

        steps = [("Umowa podpisana", signed, "")]
        start = None
        if scenario == "utknieta":
            steps.append(("Weryfikacja spółki", signed + timedelta(days=2), "Dokumenty wysłane do spółki."))
        elif scenario != "swieza":
            ver = signed + timedelta(days=rng.randint(2, 8))
            osd = ver + timedelta(days=rng.randint(7, 20))
            start = _first_of_next_month(osd + timedelta(days=14))
            tranche = start + timedelta(days=rng.randint(30, 45))
            plan = [
                ("Weryfikacja spółki", ver, ""), ("Zmiana sprzedawcy (OSD)", osd, ""), ("Start dostaw", start, ""),
                ("Transza 1 wypłacona", tranche, ""), ("Rozliczenia bieżące", tranche + timedelta(days=3), ""),
            ]
            end = _add_months(start, term)
            if scenario == "zakonczona":
                plan.append(("Zakończona", end, "Umowa wygasła."))
            if scenario in ("zerwana", "zerwana_zla"):
                broke = min(today, start + timedelta(days=rng.randint(70, 200)))
                plan = [p for p in plan if p[1] < broke] + [("Zerwana", broke, rng.choice(BREAK_REASONS))]
            steps += [p for p in plan if p[1] <= today]
        if scenario == "nowe_przylacze":
            steps = [s for s in steps if s[0] != "Transza 1 wypłacona"]

        ext = f"DEMO-U-{n:04d}"
        rows["umowy"].append({
            "id_zewn": ext, "klient_nazwa": client, "klient_nip": "", "medium": "gaz" if is_gas else "energia",
            "spolka": name, "handlowiec_email": seller, "data_podpisania": signed.isoformat(),
            "start_dostaw": start.isoformat() if start and start <= _add_months(today, 2) else "",
            "okres_miesiace": term, "wolumen_roczny_mwh": volume, "cena_bazowa_zl_mwh": base, "narzut_zl_mwh": markup,
            "nowe_przylacze": "tak" if scenario == "nowe_przylacze" else "nie", "status": steps[-1][0],
        })
        for status, when, note in steps:
            rows["historia_statusow"].append(
                {"umowa_id_zewn": ext, "status": status, "data_zdarzenia": when.isoformat(), "notatka": note}
            )
    return rows


def demo_workbook(today: Optional[date] = None) -> bytes:
    return build_workbook(demo_rows(today), demo=True)
