"""Standard pliku Excela, wersja 1.0: arkusze, kolumny, typy i opis do arkusza README."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Font

from .. import engine as eng
from ..models import CONTRACT_STATUSES, LEAD_SOURCES, LOST_REASONS, MEDIA, NIP_CHECK_RESULTS, OFFER_STATUSES, PRICING_PRODUCTS, STAGES, TRIGGERS

STANDARD_VERSION = "1.2"  # 1.1: targety; 1.2: klienci, sprawdzenia_nip, oferty


@dataclass(frozen=True)
class Col:
    name: str
    desc: str
    kind: str = "text"  # text, email, int, dec, date, bool, choice
    required: bool = False
    choices: tuple = ()
    example: str = ""


ROLE_CHOICES = ("menedzer", "handlowiec", "bok")

SHEETS: dict[str, list[Col]] = {
    "zespol": [
        Col("id_zewn", "Identyfikator osoby w poprzednim systemie.", example="H-001"),
        Col("imie", "Imię.", required=True, example="Anna"),
        Col("nazwisko", "Nazwisko.", required=True, example="Kowalczyk"),
        Col("email", "E-mail do logowania, unikalny.", "email", True, example="anna.kowalczyk@firma.pl"),
        Col("rola", "Rola w platformie. Właściciela się nie importuje.", "choice", True, ROLE_CHOICES, "handlowiec"),
        Col("menedzer_email", "E-mail menedżera, do którego zespołu należy osoba (z pliku albo z platformy).", "email", example="tomasz.zielinski@firma.pl"),
        Col("aktywny", "Czy konto jest aktywne. Domyślnie tak.", "bool", example="tak"),
        Col("udzial_w_narzucie_proc", "Udział w całej masie marży z własnej sprzedaży, w procentach. Wymagany dla menedżera i handlowca.", "dec", example="40"),
        Col("override_proc", "Tylko menedżer: override od umów zespołu, w procentach.", "dec", example="5"),
        Col("baza_override", "Tylko menedżer: od czego liczony override.", "choice", False, eng.OVERRIDE_BASES, eng.OVERRIDE_OD_NARZUTU),
    ],
    "spolki": [
        Col("id_zewn", "Identyfikator spółki w poprzednim systemie.", example="S-01"),
        Col("nazwa", "Nazwa spółki obrotu. Kilka wierszy z tą samą nazwą = historia reguł.", required=True, example="Axpo"),
        Col("aktywna", "Czy spółka jest aktywna. Domyślnie tak.", "bool", example="tak"),
        Col("obowiazuje_od", "Od kiedy obowiązują reguły w tym wierszu.", "date", True, example="2024-01-01"),
        Col("udzial_brokera_proc", "Udział brokera w całej masie marży, w procentach.", "dec", True, example="75"),
        Col("pierwsza_transza_proc", "Pierwsza transza, w procentach kwoty każdej strony.", "dec", True, example="30"),
        Col("wyzwalacz_transzy", "Kiedy spółka wypłaca pierwszą transzę.", "choice", False, tuple(TRIGGERS), "weryfikacja"),
        Col("limit_narzutu_zl_mwh", "Maksymalna marża w zł/MWh. Puste = bez limitu.", "dec", example="200"),
        Col("nowe_przylacza_miesiace", "Ile miesięcy prowizji z faktur dla nowych przyłączy. Domyślnie 12.", "int", example="12"),
        Col("tryb_korekty", "Jak spółka koryguje prowizję przy zerwaniu.", "choice", False, eng.CLAWBACK_MODES, eng.KOREKTA_PROPORCJONALNA),
        Col("uwagi", "Dowolne uwagi do umowy agencyjnej.", example=""),
    ],
    "umowy": [
        Col("id_zewn", "Identyfikator umowy w poprzednim systemie. Wymagany, łączy umowę z historią statusów.", required=True, example="U-0001"),
        Col("klient_nazwa", "Nazwa klienta.", required=True, example="Piekarnia Złoty Kłos sp. z o.o."),
        Col("klient_nip", "NIP klienta, 10 cyfr, z poprawną sumą kontrolną.", example=""),
        Col("medium", "Energia elektryczna albo paliwo gazowe.", "choice", True, tuple(MEDIA), "energia"),
        Col("spolka", "Nazwa spółki obrotu (z arkusza spolki albo z platformy).", required=True, example="Axpo"),
        Col("handlowiec_email", "E-mail osoby, która sprzedała umowę.", "email", True, example="anna.kowalczyk@firma.pl"),
        Col("data_podpisania", "Data podpisania umowy.", "date", True, example="2025-03-14"),
        Col("start_dostaw", "Data startu dostaw.", "date", example="2025-05-01"),
        Col("okres_miesiace", "Okres umowy w miesiącach.", "int", True, example="36"),
        Col("wolumen_roczny_mwh", "Roczny wolumen w MWh.", "dec", True, example="250"),
        Col("cena_bazowa_zl_mwh", "Cena bazowa spółki w zł/MWh.", "dec", example="520"),
        Col("narzut_zl_mwh", "Marża w zł/MWh (narzut na cenę bazową).", "dec", True, example="90"),
        Col("nowe_przylacze", "Czy to nowe przyłącze bez historii zużycia.", "bool", example="nie"),
        Col("status", "Obecny status umowy.", "choice", True, tuple(CONTRACT_STATUSES), "Rozliczenia bieżące"),
        Col("udzial_brokera_proc", "Opcjonalnie: udział brokera zamrożony w dniu podpisania.", "dec"),
        Col("pierwsza_transza_proc", "Opcjonalnie: pierwsza transza zamrożona w dniu podpisania.", "dec"),
        Col("udzial_handlowca_proc", "Opcjonalnie: udział handlowca zamrożony w dniu podpisania.", "dec"),
        Col("override_menedzera_proc", "Opcjonalnie: override menedżera zamrożony w dniu podpisania.", "dec"),
    ],
    "historia_statusow": [
        Col("umowa_id_zewn", "id_zewn umowy z arkusza umowy.", required=True, example="U-0001"),
        Col("status", "Status, w który umowa weszła.", "choice", True, tuple(CONTRACT_STATUSES), "Weryfikacja spółki"),
        Col("data_zdarzenia", "Kiedy umowa weszła w ten status.", "date", True, example="2025-03-20"),
        Col("notatka", "Notatka. Przy statusie Zerwana wymagany powód.", example=""),
    ],
    "targety": [
        Col("email", "E-mail menedżera albo handlowca (z arkusza zespol albo z platformy).", "email", True, example="anna.kowalczyk@firma.pl"),
        Col("miesiac", "Miesiąc targetu w formacie RRRR-MM.", required=True, example="2026-11"),
        Col("kwota_zl", "Target masy marży w zł na ten miesiąc.", "dec", True, example="150000"),
    ],
    "klienci": [
        Col("id_zewn", "Identyfikator klienta w poprzednim systemie. Łączy kartę ze sprawdzeniami i ofertami.", required=True, example="K-001"),
        Col("nazwa", "Nazwa firmy.", required=True, example="Wózki Widłowe Michalski"),
        Col("nip", "NIP, 10 cyfr. Jeden NIP = jeden klient w biurze.", example=""),
        Col("handlowiec_email", "E-mail opiekuna klienta.", "email", True, example="anna.kowalczyk@firma.pl"),
        Col("etap", "Etap w lejku.", "choice", False, tuple(STAGES), "lead"),
        Col("zrodlo", "Skąd pochodzi lead.", "choice", False, tuple(LEAD_SOURCES), "Polecenie"),
        Col("osoba_kontaktowa", "Osoba kontaktowa.", example="Jan Michalski"),
        Col("telefon", "Telefon.", example="600 100 200"),
        Col("email", "E-mail klienta.", example=""),
        Col("nastepny_krok", "Następny krok.", example="Telefon: decyzja po ofercie"),
        Col("nastepny_krok_data", "Data następnego kroku.", "date", example="2026-11-20"),
        Col("powod_przegranej", "Przy etapie przegrana: powód z listy.", "choice", False, tuple(LOST_REASONS), ""),
        Col("notatka", "Notatka do historii działań.", example=""),
    ],
    "sprawdzenia_nip": [
        Col("klient_id_zewn", "id_zewn klienta z arkusza klienci.", required=True, example="K-001"),
        Col("spolka", "Nazwa spółki obrotu.", required=True, example="Axpo"),
        Col("wynik", "Wynik sprawdzenia przez BOK.", "choice", True, tuple(NIP_CHECK_RESULTS), "zarezerwowany"),
        Col("zarezerwowany_do", "Do kiedy rezerwacja (przy wyniku zarezerwowany).", "date", example="2026-12-31"),
        Col("uwagi", "Uwagi BOK.", example=""),
    ],
    "oferty": [
        Col("klient_id_zewn", "id_zewn klienta z arkusza klienci.", required=True, example="K-001"),
        Col("spolka", "Nazwa spółki obrotu.", required=True, example="Axpo"),
        Col("produkt", "Produkt cenowy.", "choice", False, tuple(PRICING_PRODUCTS), "fix"),
        Col("medium", "Energia albo gaz.", "choice", False, tuple(MEDIA), "energia"),
        Col("cena_bazowa_zl_mwh", "Cena bazowa z cennika.", "dec", example="520"),
        Col("marza_zl_mwh", "Marża w zł/MWh.", "dec", True, example="100"),
        Col("wolumen_roczny_mwh", "Wolumen roczny w MWh.", "dec", True, example="180"),
        Col("okres_miesiace", "Okres umowy w miesiącach.", "int", True, example="24"),
        Col("data_wyslania", "Kiedy oferta trafiła do klienta.", "date", True, example="2026-11-05"),
        Col("wazna_do", "Ważna do. Puste = 7 dni od wysłania.", "date", example="2026-11-12"),
        Col("status", "Status oferty.", "choice", False, tuple(OFFER_STATUSES), "otwarta"),
    ],
}

SHEET_TITLES = {
    "zespol": "Zespół: menedżerowie, handlowcy, biuro obsługi",
    "spolki": "Spółki obrotu i reguły prowizji (umowy agencyjne)",
    "umowy": "Umowy z klientami",
    "historia_statusow": "Historia statusów umów",
    "targety": "Miesięczne targety masy marży (arkusz opcjonalny)",
    "klienci": "Karty klientów w lejku (arkusz opcjonalny)",
    "sprawdzenia_nip": "Sprawdzenia NIP przez BOK w spółkach (arkusz opcjonalny)",
    "oferty": "Oferty złożone klientom (arkusz opcjonalny)",
}


def build_workbook(rows: Optional[dict[str, list[dict]]] = None, *, demo: bool = False) -> bytes:
    """Plik w standardzie: README + arkusze. rows=None daje pusty szablon."""
    wb = Workbook()
    readme = wb.active
    readme.title = "README"
    bold = Font(bold=True)
    readme.append(["standard", STANDARD_VERSION])
    readme.append(["demo", "tak" if demo else "nie"])
    readme.append([])
    readme.append(["Plik w standardzie wymiany danych Platformy brokerskiej."])
    readme.append(["Liczby z przecinkiem albo kropką. Daty RRRR-MM-DD albo DD.MM.RRRR. Tak/nie: tak, nie, 1, 0."])
    if demo:
        readme.append(["DANE DEMONSTRACYJNE. Warunki umów agencyjnych ze spółkami są fikcyjne."])
    for sheet, cols in SHEETS.items():
        readme.append([])
        readme.append([f"Arkusz: {sheet}", SHEET_TITLES[sheet]])
        readme.cell(readme.max_row, 1).font = bold
        readme.append(["kolumna", "opis", "wymagana", "dozwolone wartości", "przykład"])
        for c in cols:
            readme.append([c.name, c.desc, "tak" if c.required else "nie", ", ".join(c.choices), c.example])
    for sheet, cols in SHEETS.items():
        ws = wb.create_sheet(sheet)
        ws.append([c.name for c in cols])
        for cell in ws[1]:
            cell.font = bold
        for r in (rows or {}).get(sheet, []):
            ws.append([r.get(c.name, "") if r.get(c.name) is not None else "" for c in cols])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
