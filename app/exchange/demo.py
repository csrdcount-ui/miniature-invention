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

# nazwa, udział brokera, 1. transza, wyzwalacz, limit marży, mies. nowych przyłączy, korekta
# Limity marży co najmniej 150 zł/MWh, żeby mieściły najwyższe marże małych umów.
SUPPLIERS = [
    ("e2V (Ekovoltis)", 75, 30, "weryfikacja", 200, 12, "proporcjonalna"),
    ("ENGIE", 70, 50, "start_dostaw", 180, 12, "proporcjonalna"),
    ("MET Polska", 65, 30, "weryfikacja", 150, 12, "proporcjonalna"),
    ("Enefit", 72, 40, "zmiana_sprzedawcy", 200, 12, "proporcjonalna"),
    ("Polenergia", 68, 30, "start_dostaw", 160, 12, "proporcjonalna"),
    ("Respect Energy", 80, 50, "weryfikacja", 200, 12, "proporcjonalna"),
    ("Enea", 60, 30, "start_dostaw", 150, 12, "proporcjonalna"),
    ("PGE", 62, 30, "start_dostaw", 150, 12, "proporcjonalna"),
    ("Orlen", 64, 30, "zmiana_sprzedawcy", 150, 12, "proporcjonalna"),
    ("Tauron", 61, 30, "start_dostaw", 150, 12, "proporcjonalna"),
    ("Audax", 78, 50, "weryfikacja", 200, 12, "brak"),
    ("Axpo", 74, 40, "weryfikacja", 180, 12, "proporcjonalna"),
]
RULES_FROM = date(2023, 1, 1)

MANAGER = ("Michał", "Lex", 45, 5)
TRADERS = [  # imię, nazwisko, udział, waga sprzedaży
    ("Anna", "Kowalczyk", 50, 14),
    ("Piotr", "Nowicki", 45, 11),
    ("Katarzyna", "Mazur", 40, 9),
    ("Michał", "Wójcik", 40, 8),
    ("Agnieszka", "Lewandowska", 35, 6),
    ("Paweł", "Kamiński", 35, 3),  # najgorszy portfel: najwięcej zerwań
]
# Rytm sprzedaży w ostatnich 12 miesiącach (0 = bieżący miesiąc, 11 = rok temu). Menedżer ma na
# filtrach i statystykach zobaczyć różnicę między kimś, kto podpisuje co miesiąc, a kimś, kto
# „dwa miesiące przyciśnie, dwa nic nie robi”.
WINDOW_MONTHS = 12
RHYTHM = {
    "Kowalczyk": ("regularna", range(0, 12)),
    "Nowicki": ("zrywami: dwa miesiące sprzedaje, dwa nie", [0, 1, 4, 5, 8, 9]),
    "Mazur": ("regularna", range(0, 12)),
    "Wójcik": ("zrywami, od dwóch miesięcy przestój", [2, 3, 6, 7, 10, 11]),
    "Lewandowska": ("regularna, pracuje od 9 miesięcy", range(0, 9)),
    "Kamiński": ("słabnąca: nic w ostatnich dwóch miesiącach", range(2, 12)),
    "Lex": ("regularna, co drugi miesiąc", range(0, 12, 2)),
}
# Target masy marży wg poziomu (wytyczne właścicielki 10.11.2026): udział 35% = junior,
# 40% = senior, 45% i więcej = pro.
TARGET_BY_SHARE = [(35, 150_000), (40, 200_000), (100, 250_000)]


def target_for_share(share) -> int:
    return next(t for limit, t in TARGET_BY_SHARE if share <= limit)


# Biuro obsługi: pierwsza osoba to szefowa. Platforma nie rozróżnia dziś szefa BOK od zwykłej
# osoby BOK (obie mają te same uprawnienia).
BOK = [("Jessica", "Kowal"), ("Joanna", "Dąbrowska")]

# Struktura portfela wg rocznego wolumenu (razem 100 umów, procenty = liczby):
# nazwa, liczba umów, możliwe wolumeny roczne w MWh, możliwe marże w zł/MWh
TIERS = [
    ("do 50 MWh", 17, [5, 8, 10, 12, 15, 18, 20, 25, 30, 35, 40, 45, 50], list(range(110, 151, 5))),
    ("50–300 MWh", 49, [60, 70, 80, 90, 100, 120, 140, 150, 160, 180, 200, 220, 250, 280, 300], list(range(90, 121, 5))),
    ("300–500 MWh", 4, [320, 350, 400, 450, 500], list(range(90, 121, 5))),
    ("500–1000 MWh", 7, [550, 600, 650, 700, 800, 900, 1000], [60, 65, 70]),
    ("1–3 GWh", 17, [1100, 1200, 1400, 1500, 1800, 2000, 2500], list(range(30, 51, 5))),
    ("3–10 GWh", 4, [3200, 3500, 4000, 5000], [30, 35, 40]),
    ("powyżej 10 GWh", 2, [10500, 12000], list(range(8, 16))),
]

CLIENTS_SMALL = [
    "Wspólnota Mieszkaniowa ul. Lipowa 12", "Wspólnota Mieszkaniowa ul. Długa 5", "Wspólnota Mieszkaniowa os. Słoneczne",
    "Wspólnota Mieszkaniowa ul. Ogrodowa 3", "Wspólnota Mieszkaniowa ul. Polna 8", "Wspólnota Mieszkaniowa ul. Krótka 2",
    "Pracownia Ceramiki Glina", "Sklep Ogrodniczy Konewka", "Myjnia Błysk", "Kancelaria Podatkowa Bilans",
    "Studio Fryzjerskie Nożyczki", "Gabinet Stomatologiczny Uśmiech", "Księgarnia Kartka", "Apteka Pod Różą",
    "Warsztat Rowerowy Szprycha", "Kwiaciarnia Pod Magnolią", "Biuro Rachunkowe Księga",
]
CLIENTS_MEDIUM = [
    "Piekarnia Złoty Kłos sp. z o.o.", "Hotel Pod Lipami", "Zakład Mechaniczny Kowalski", "Drukarnia Akant sp. z o.o.",
    "Tartak Leśny Dwór", "Ogrodnictwo Zielone Pole", "Stolarnia Dąb s.c.", "Market Pod Zegarem", "Restauracja Stary Młyn",
    "Szkoła Językowa Lingua", "Klinika Weterynaryjna Azor", "Pensjonat Górski Potok", "Serwis Opon Kołowrót",
    "Pralnia Przemysłowa Biel", "Przychodnia Zdrowie", "Fitness Klub Forma", "Kino Plaza", "Browar Rzemieślniczy Chmiel",
    "Warsztat Samochodowy Tłok", "Hotel Nad Jeziorem", "Kamieniarstwo Granit", "Zakład Stolarki PCV Okno",
    "Piekarnia Rumiana Skórka", "Cukiernia Słodki Kącik", "Gospodarstwo Rybne Karp", "Lakiernia Proszkowa Kolor",
    "Hala Sportowa Olimp", "Biurowiec Kwadrat", "Hotel Biznes Centrum", "Agencja Reklamowa Baner",
    "Przedszkole Niepubliczne Promyk", "Zakład Poligraficzny Druk-Art", "Producent Opakowań Karton",
    "Salon Meblowy Komfort", "Szwalnia Igła i Nić", "Zakład Betoniarski Beton-Mix", "Wytwórnia Makaronu Kluska",
    "Centrum Rehabilitacji Ruch", "Cukiernia Marcepan", "Szkoła Jazdy Kierownica", "Pływalnia Miejska Fala",
    "Zajazd Pod Dębem", "Dom Kultury Akord", "Laboratorium Analiz Probówka", "Sklep Spożywczy Smak",
    "Hurtownia Kwiatów Tulipan", "Zakład Pogrzebowy Pokój", "Drukarnia Cyfrowa Piksel", "Pensjonat Leśna Cisza",
]
CLIENTS_LARGE = [  # 300–1000 MWh
    "Chłodnia Lubelska sp. z o.o.", "Hurtownia Budowlana Fundament", "Galwanizernia Metal-Pol", "Zakład Mięsny Kłos",
    "Wytwórnia Lodów Bałtyk", "Magazyny Chłodnicze Arktyka", "Szklarnia Pomidor sp. z o.o.", "Mleczarnia Łąka",
    "Tłocznia Soków Jabłonka", "Przetwórnia Owoców Sad", "Odlewnia Żeliwa Sztaba",
]
CLIENTS_XL = [  # powyżej 1 GWh; dwa pierwsze to największe (powyżej 10 GWh)
    "Walcownia Stali Hutnik S.A.", "Cementownia Wapienna S.A.",
    "Zakłady Chemiczne Reagent S.A.", "Papiernia Biała sp. z o.o.", "Cukrownia Buraczana S.A.", "Zakład Produkcji Szkła Kryształ",
    "Centrum Logistyczne Wschód sp. z o.o.", "Fabryka Mebli Komfort sp. z o.o.", "Serwerownia DataLas sp. z o.o.",
    "Centrum Handlowe Rynek", "Tłocznia Oleju Rzepak", "Zakład Tworzyw Polimer", "Spółdzielnia Ogrodnicza Plon",
    "Wylęgarnia Drobiu Kurnik", "Fabryka Opakowań Tektura sp. z o.o.", "Zakład Przetwórstwa Mięsnego Wędlina S.A.",
    "Hurtownia Spożywcza Centrum sp. z o.o.", "Fabryka Okien Panorama S.A.", "Szpital Powiatowy Zielona Dolina",
    "Uczelnia Techniczna Politech", "Centrum Dystrybucji Paczek Ekspres", "Kopalnia Kruszyw Żwir", "Zakłady Mleczarskie Nabiał S.A.",
]


def _client_slots() -> list[dict]:
    """Jedno miejsce na umowę: klient, wolumen i marża z właściwego przedziału. Razem 100."""
    pools = [CLIENTS_SMALL, CLIENTS_MEDIUM, CLIENTS_LARGE[:4], CLIENTS_LARGE[4:], CLIENTS_XL[6:], CLIENTS_XL[2:6], CLIENTS_XL[:2]]
    slots = []
    for (tier, count, _, _), names in zip(TIERS, pools):
        assert len(names) == count, (tier, len(names), count)
        slots += [{"tier": tier, "client": n} for n in names]
    return slots


# Oferty złożone, jeszcze niepodpisane (status „Oferta”): klient, wolumen roczny MWh, marża zł/MWh.
# Do rozmów na odprawie: „co z ofertą dla Wózki Widłowe Michalski?”.
OFFERS = [
    ("Wózki Widłowe Michalski", 180, 105),
    ("Piekarnia Złoty Kłos", 95, 130),
    ("Zajazd Pod Wiatrakiem", 260, 110),
    ("Chłodnia Mrozik", 1400, 45),
    ("Stolarnia Dębowy Dwór", 70, 140),
    ("Warsztat Auto-Serwis Nowak", 40, 145),
    ("Drukarnia Offsetowa Kolor", 320, 100),
    ("Wspólnota Mieszkaniowa Słoneczna 12", 120, 115),
    ("Odlewnia Żeliwa Kuźnia", 2200, 40),
    ("Szkoła Językowa Lingwa", 30, 150),
    ("Wytwórnia Lodów Sopel", 850, 65),
    ("Kwiaciarnia Storczyk", 60, 135),
    ("Myjnia Bezdotykowa Bąbel", 110, 120),
    ("Centrum Logistyczne Węzeł", 3100, 35),
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
    rows: dict[str, list[dict]] = {"zespol": [], "spolki": [], "umowy": [], "historia_statusow": [], "targety": []}

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
    for i, (first, last) in enumerate(BOK, start=1):
        rows["zespol"].append({
            "id_zewn": f"DEMO-B-{i}", "imie": first, "nazwisko": last, "email": _email(first, last), "rola": "bok",
            "aktywny": "tak",
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

    slots = _client_slots()
    rng.shuffle(slots)  # kolejność umów nie grupuje się według wielkości
    tiers = {t[0]: t for t in TIERS}
    # Scenariusze przypisane z góry, reszta to zwykły przebieg.
    scenarios = (["zerwana_zla"] * 6 + ["zerwana"] * 3 + ["utknieta"] * 6 + ["swieza"] * 8
                 + ["nowe_przylacze"] * 8 + ["zakonczona"] * 5)
    scenarios += ["zwykla"] * (len(slots) - len(scenarios))
    rng.shuffle(scenarios)

    month0 = date(today.year, today.month, 1)
    surname = {e: l for f, l, _, _ in TRADERS for e in [_email(f, l)]} | {mgr_email: MANAGER[1]}

    def offset_of(d: date) -> int:
        return (month0.year - d.year) * 12 + month0.month - d.month

    def active(seller: str, d: date) -> bool:
        return offset_of(d) in RHYTHM[surname[seller]][1]

    def weighted(pool):
        pool = pool or sellers
        return rng.choices([e for e, _ in pool], weights=[w for _, w in pool])[0]

    # Świeże umowy (ostatnie dni) to małe i średnie firmy: jedna umowa na kilka GWh w pierwszych
    # dniach miesiąca dałaby nierealne 300% targetu. Duże sloty zamieniamy z małymi „zwykłymi”.
    big = {"1–3 GWh", "3–10 GWh", "powyżej 10 GWh"}
    small = [i for i, sc in enumerate(scenarios) if sc == "zwykla" and slots[i]["tier"] not in big]
    for i, sc in enumerate(scenarios):
        if sc == "swieza" and slots[i]["tier"] in big and small:
            j = small.pop()
            slots[i], slots[j] = slots[j], slots[i]

    # Przebieg 1: sprzedawca i (dla scenariuszy z ustaloną datą) data podpisania.
    plan_rows = []
    for n, (slot, scenario) in enumerate(zip(slots, scenarios), start=1):
        signed = None
        if scenario == "swieza":
            signed = today - timedelta(days=rng.randint(1, 6))
        elif scenario == "utknieta":
            signed = today - timedelta(days=rng.randint(42, 60))
        elif scenario == "zakonczona":
            signed = date(today.year - 2, rng.randint(1, 6), rng.randint(1, 28))
        if scenario == "zerwana_zla" or (scenario == "utknieta" and n % 4 == 0):
            seller = bad
        elif signed and scenario != "zakonczona":
            seller = weighted([sw for sw in sellers if active(sw[0], signed)])  # nikt nie sprzedaje „w przestoju”
        else:
            seller = weighted(sellers)
        plan_rows.append({"n": n, "slot": slot, "scenario": scenario, "seller": seller, "signed": signed})

    # Przebieg 2: pozostałe daty rozłożone po miesiącach rytmu danej osoby, po kolei, żeby
    # regularni mieli umowę w (prawie) każdym miesiącu. Zerwane trafiają w miesiące sprzed 3+ mies.
    def day_in(offset: int) -> date:
        y, m = divmod(month0.month - 1 - offset, 12)
        first = date(month0.year + y, m + 1, 1)
        last = today.day if offset == 0 else calendar.monthrange(first.year, first.month)[1]
        return first.replace(day=rng.randint(1, last))

    for seller in {r["seller"] for r in plan_rows}:
        months = sorted(RHYTHM[surname[seller]][1])  # od bieżącego w tył
        old = [o for o in months if o >= 3] or [max(months)]
        todo = [r for r in plan_rows if r["seller"] == seller and r["signed"] is None]
        broken = [r for r in todo if r["scenario"] in ("zerwana", "zerwana_zla")]
        rest = [r for r in todo if r not in broken]
        for i, r in enumerate(broken):
            r["signed"] = day_in(old[-1 - i % len(old)])
        # Od najstarszego miesiąca. Bieżący (niepełny) miesiąc dostaje tylko świeże umowy, więc
        # wykonanie targetu w trakcie miesiąca wygląda realnie.
        past = [o for o in months[::-1] if o > 0] or months  # bieżący miesiąc: tylko świeże umowy
        for i, r in enumerate(rest):
            r["signed"] = day_in(past[i % len(past)])

    # Przebieg 3: warunki i historia statusów.
    for r in plan_rows:
        n, slot, scenario, seller, signed = r["n"], r["slot"], r["scenario"], r["seller"], r["signed"]
        client = slot["client"]
        _, _, volumes, margins = tiers[slot["tier"]]
        sup = rng.choice(SUPPLIERS)
        name, limit = sup[0], sup[4]
        is_gas = rng.random() < 0.15 and "Wspólnota" not in client
        term = rng.choice([12, 24, 36, 36, 48, 60])
        volume = rng.choice(volumes)
        base = rng.randrange(220, 301, 5) if is_gas else rng.randrange(480, 621, 5)

        if scenario == "zakonczona":
            term = 12

        if name == "Axpo" and signed >= date(today.year, 1, 1):
            limit = 160  # nowe reguły Axpo od początku roku
        markup = min(rng.choice(margins), limit)

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

    for k, (client, volume, markup) in enumerate(OFFERS, start=1):
        seller = sellers[(k - 1) % len(sellers)][0]
        sup = rng.choice(SUPPLIERS)
        sent = today - timedelta(days=rng.randint(1, 25))
        ext = f"DEMO-O-{k:04d}"
        rows["umowy"].append({
            "id_zewn": ext, "klient_nazwa": client, "klient_nip": "", "medium": "energia",
            "spolka": sup[0], "handlowiec_email": seller, "data_podpisania": sent.isoformat(), "start_dostaw": "",
            "okres_miesiace": rng.choice([12, 24, 36]), "wolumen_roczny_mwh": volume,
            "cena_bazowa_zl_mwh": rng.randrange(480, 621, 5), "narzut_zl_mwh": min(markup, sup[4]),
            "nowe_przylacze": "nie", "status": "Oferta",
        })
        rows["historia_statusow"].append(
            {"umowa_id_zewn": ext, "status": "Oferta", "data_zdarzenia": sent.isoformat(), "notatka": "Oferta wysłana klientowi."}
        )

    # Targety: każdy sprzedający na każdy miesiąc okna, wg poziomu (udziału w masie marży).
    rows["targety"] = []
    for first, last, share in [(f, l, sh) for f, l, sh, _ in TRADERS] + [MANAGER[:3]]:
        for off in range(WINDOW_MONTHS):
            y, m = divmod(month0.month - 1 - off, 12)
            rows["targety"].append({
                "email": _email(first, last), "miesiac": f"{month0.year + y}-{m + 1:02d}",
                "kwota_zl": target_for_share(share),
            })
    return rows


def demo_workbook(today: Optional[date] = None) -> bytes:
    return build_workbook(demo_rows(today), demo=True)
