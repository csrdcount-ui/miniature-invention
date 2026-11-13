"""Samouczek: kroki dla każdej roli, postęp, testowy NIP. Bez FastAPI (jak engine i pipeline).

Zasady (13.11.2026): zwykłe strony z nagłówkami, nie nakładki ani „wycieczki” (czytniki ekranu
sobie z nimi nie radzą); każdy krok to zadanie na prawdziwym ekranie z linkiem i opisem wyniku;
postęp zapisany osobno dla każdej osoby; każdemu testerowi platforma podaje inny, poprawny NIP
testowy (jeden NIP może mieć w biurze tylko jedną kartę). Kroki są sprawdzane automatycznym
przejściem w tests/test_samouczek.py: jeśli ekran się zmieni, test przestanie przechodzić.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    ROLE_BOK,
    ROLE_MANAGER,
    ROLE_OWNER,
    ROLE_TRADER,
    Client,
    TutorialProgress,
    User,
)

HIDDEN_KEY = "_ukryte"
NIP_WEIGHTS = [6, 5, 7, 2, 3, 4, 5, 6, 7]


def _nip_ok(nip: str) -> bool:
    check = sum(int(d) * w for d, w in zip(nip, NIP_WEIGHTS)) % 11
    return check != 10 and check == int(nip[9])


def test_nip(db: Session, user: User) -> str:
    """Poprawny NIP testowy dla osoby: stały dla niej, różny od NIP-ów innych osób i prawdziwych klientów."""
    n = 990_000_000 + (user.id % 1_000) * 1_000
    while True:
        base = f"{n:09d}"
        check = sum(int(d) * w for d, w in zip(base, NIP_WEIGHTS)) % 11
        if check != 10:
            nip = base + str(check)
            owner = db.scalar(select(Client.owner_id).where(Client.nip == nip))
            if owner is None or owner == user.id:
                return nip
        n += 1


def _s(key, title, do, expect, url="", label=""):
    return {"key": key, "title": title, "do": do, "expect": expect, "url": url, "label": label}


COMMON = {
    "id": "wspolne",
    "title": "Na początek (każdy)",
    "intro": "Kilka minut: hasło, poruszanie się po platformie i zgłaszanie uwag. Darmowy serwer usypia się po "
             "około 15 minutach bez ruchu, więc pierwsze otwarcie po przerwie może trwać około minuty. To nie awaria.",
    "steps": [
        _s("w-haslo", "Ustaw własne hasło",
           "Wejdź w zakładkę Konto, potem „Zmiana hasła”. Wpisz hasło startowe, nowe hasło (co najmniej 10 znaków) i powtórz je.",
           "Komunikat „Hasło zmienione.”", "/haslo", "Zmiana hasła"),
        _s("w-nawigacja", "Poznaj nawigację",
           "Na telefonie na dole ekranu jest belka z zakładkami (ikona i podpis), aktywna jest pogrubiona. Pod tytułem strony "
           "są podsekcje jako przyciski, np. „Lista klientów” i „Nowy klient”. Na komputerze te same zakładki są u góry. "
           "Czytnik ekranu: menu to nawigacja „Menu główne”, a bieżąca zakładka jest oznaczona jako bieżąca strona. "
           "Wylogowanie jest w zakładce Konto. Przejdź po wszystkich zakładkach, które widzisz.",
           "Wiesz, gdzie jest każda zakładka i jak wrócić do początku.", "/konto", "Zakładka Konto"),
        _s("w-male", "Gdy litery są bardzo małe",
           "Jeśli na telefonie platforma wygląda jak pomniejszona strona komputerowa, a menu jest u góry, w przeglądarce "
           "włączona jest „Wersja na komputer”. Wyłącz ją w menu przeglądarki (trzy kropki). Platforma sama pokaże wtedy ostrzeżenie.",
           "Duże litery i dolna belka."),
        _s("w-uwaga", "Zgłoś uwagę",
           "Na dole każdej strony jest link „Zgłoś uwagę do tej strony”. Napisz jedno zdanie: co było niejasne, czego "
           "brakowało albo co nie działało. Platforma sama dopisze stronę i Twoją rolę. Wyślij dowolną uwagę teraz, na próbę.",
           "Komunikat, że uwaga zapisana. Właściciel zobaczy ją na liście.", "/uwagi", "Zgłoś uwagę"),
    ],
}

TRADER = {
    "id": "handlowiec",
    "title": "Handlowiec: od telefonu do umowy",
    "intro": "Przejdź cały proces na kliencie testowym. NIP testowy w kroku 2 jest tylko dla Ciebie, nie wpisuj innego. "
             "Gdy wyślesz NIP albo faktury do BOK, odpowie osoba pełniąca rolę BOK (w tym teście właściciel).",
    "steps": [
        _s("h-dzien", "Zobacz swój dzień",
           "Otwórz „Mój dzień”. Na górze jest przycisk „Szybki lead: dodaj klienta”, wynik miesiąca wobec targetu, potem listy: "
           "Pilne, Dziś, Od BOK.", "Widzisz wynik miesiąca i listy. Na początku mogą być puste.", "/dzien", "Mój dzień"),
        _s("h-lead", "Dodaj klienta testowego",
           "Stuknij „Szybki lead: dodaj klienta”. Wpisz nazwę „TEST {imie} Sp. z o.o.”, telefon 600100200, NIP testowy {nip} "
           "i wybierz źródło. Zapisz.",
           "Karta klienta z czterema ekranami: Kontakt, Dane, Teren, Oferta i umowa.", "/klienci/nowy", "Nowy klient"),
        _s("h-ekrany", "Poruszaj się po ekranach klienta",
           "Na telefonie przesuwaj ekrany palcem w lewo i w prawo albo stukaj w pasek etapów na górze karty (1. Kontakt, "
           "2. Dane, 3. Teren, 4. Oferta i umowa). Na komputerze ekrany są jeden pod drugim, a pasek etapów przewija do wybranego. "
           "Każdy ekran to sekcja z nagłówkiem, a pasek etapów to zwykłe linki, więc czytnik ekranu też sobie poradzi.",
           "Pod nazwą klienta widać jego etap, następny krok i przycisk „Zadzwoń”.", "/klienci", "Lista klientów"),
        _s("h-rozmowa", "Zapisz rozmowę i następny krok",
           "Na ekranie Kontakt otwórz „Zapisz rozmowę i następny krok”. Wybierz „Telefon”, wpisz wynik rozmowy, następny krok "
           "„oddzwonić z ofertą” i datę na jutro. Zapisz.",
           "Na karcie następny krok z datą, a w „Historii działań” nowy wpis. Dzisiaj ustawiony krok pojawia się w „Mój dzień”.",
           "/klienci", "Lista klientów"),
        _s("h-punkt", "Dodaj punkt poboru i dane z faktur",
           "Ekran Dane, „Dodaj punkt poboru”: numer PPE „PL0001”, grupa C11, obecny sprzedawca „Obecna Energia”, koniec umowy "
           "za rok, wypowiedzenie 3 miesiące. Potem przy punkcie „Dodaj dane z faktury”, dwa razy: "
           "faktura 1: okres od 2025-01-01 do 2025-02-28, stan licznika na początek 10000, na koniec 12000; "
           "faktura 2: okres od 2025-11-01 do 2025-12-31, stan licznika na początek 28000, na koniec 30000.",
           "Przy punkcie: wolumen roczny około 20,055 MWh (z różnicy stanów licznika) i ostatni dzień na wypowiedzenie umowy.",
           "/klienci", "Lista klientów"),
        _s("h-nip", "Wyślij NIP do BOK",
           "Ekran Dane, „Wyślij NIP do BOK: wybierz spółki”. Zaznacz dwie spółki i wyślij.",
           "Przy spółkach „czeka na BOK”. Dopóki BOK nie odpowie, nie zapiszesz oferty w tych spółkach.", "/klienci", "Lista klientów"),
        _s("h-faktury", "Odeślij zdjęcia faktur do BOK",
           "Ekran Dane, „Odeślij zdjęcia faktur do BOK”. Zrób zdjęcie czegokolwiek albo wybierz zdjęcie z galerii (w prawdziwej pracy to "
           "zdjęcia faktur klienta) i wyślij.",
           "Status „Czeka na BOK”. Gdy BOK wprowadzi dane, w „Mój dzień” zobaczysz „dane z faktur gotowe”.", "/klienci", "Lista klientów"),
        _s("h-odp", "Odbierz odpowiedź BOK",
           "Gdy BOK odpowie, wejdź w „Mój dzień” i sekcję „Od BOK”.",
           "Wynik w każdej spółce: wolny i zarezerwowany do daty, zajęty albo negatywny scoring.", "/dzien", "Mój dzień"),
        _s("h-kalk", "Policz ofertę w kalkulatorze",
           "Ekran Teren, „Kalkulator: gdzie się bardziej opłaca”. Wolumen i grupa są już wpisane z karty. Wpisz cenę dla klienta "
           "w zł/MWh (np. 650), okres umowy w miesiącach (np. 36) i policz.",
           "Spółki z marżą, ceną dla klienta, Twoją prowizją i ostrzeżeniami (limit marży, wycena indywidualna).", "/klienci", "Lista klientów"),
        _s("h-oferta", "Zapisz ofertę",
           "W wyniku kalkulatora wybierz „Zapisz ofertę w tej spółce” (albo ekran Oferta i umowa, „Zapisz złożoną ofertę”). "
           "Sprawdź dane i zapisz. Oferta wymaga spółki, w której BOK potwierdził, że NIP jest wolny.",
           "Oferta na ekranie Oferta i umowa, ważna 7 dni. Po 3 dniach bez decyzji pojawi się zadanie „zadzwoń w sprawie oferty”.",
           "/klienci", "Lista klientów"),
        _s("h-umowa", "Klient podpisał: zapisz umowę (opcjonalnie)",
           "Przy ofercie stuknij „Klient podpisał: zapisz umowę”, sprawdź formularz i zapisz.",
           "Karta umowy z Twoją częścią prowizji. To umowa testowa, widoczna w portfelu.", "/umowy", "Umowy"),
    ],
}

MANAGER = {
    "id": "menedzer",
    "title": "Menedżer: zespół, lejek i wyniki",
    "intro": "Obejrzyj to, co widzisz Ty i czego nie widzą handlowcy. Najlepiej po tym, jak handlowcy dodadzą swoich klientów testowych.",
    "steps": [
        _s("m-dzien", "Zobacz dzień i lejek zespołu",
           "Otwórz „Mój dzień”. Oprócz własnych spraw widzisz lejek zespołu: kto ma mniej niż 3 klientów w toku (alarm małego lejka).",
           "Lejek każdego handlowca z etapami.", "/dzien", "Mój dzień"),
        _s("m-zespol", "Przeczytaj zespół",
           "Otwórz Zespół. Ranking miesiąca według targetu, rytm sprzedaży (w ilu z 6 ostatnich miesięcy była umowa) i sekcja "
           "„Udział w masie marży biura”. Przy osobie jest ocena: „w normie”, „słabszy bieżący miesiąc”, „trwała tendencja spadkowa”.",
           "Udział każdej osoby w masie marży biura. Tę sekcję widzisz tylko Ty i właściciel, handlowcy nie.", "/zespol", "Zespół"),
        _s("m-osoba", "Otwórz stronę osoby i ustaw target",
           "W Zespole stuknij nazwę handlowca. Zobaczysz statystyki po miesiącach z targetem. Swoim ludziom możesz ustawić target.",
           "Wykonanie targetu miesiąc po miesiącu.", "/zespol", "Zespół"),
        _s("m-pulpit", "Zobacz sprzedaż zespołu",
           "Otwórz „Portfel”, podsekcja Podsumowanie. Sprzedaż miesiąca wobec targetu, oferty złożone (te, które czekają 3 dni i dłużej "
           "są wyróżnione), statystyki po miesiącach w zwiniętej sekcji.", "Wynik zespołu i Twój override.", "/pulpit", "Pulpit"),
        _s("m-umowy", "Przefiltruj umowy",
           "Portfel, „Umowy”. Otwórz „Filtry”: produkt, spółka, handlowiec, status, daty. Zmień kilka i obserwuj licznik wyników.",
           "Lista umów zespołu. Adres strony z filtrami możesz zapisać i wrócić do tego widoku.", "/umowy", "Umowy"),
        _s("m-klienci", "Obejrzyj klientów handlowca",
           "Zakładka Klienci. Otwórz kartę klienta handlowca z zespołu: ekran Dane (NIP u BOK, punkty poboru), Oferta i umowa, Historia działań. "
           "Możesz pomóc: ustawić następny krok albo złożyć ofertę.",
           "Pełny obraz sprawy klienta: kto, co i kiedy zrobił, także BOK.", "/klienci", "Klienci"),
    ],
}

BOK = {
    "id": "bok",
    "title": "BOK: zlecenia, faktury i cenniki",
    "intro": "Tu pracuje biuro obsługi klienta. W tym teście tę rolę gra właściciel, bo handlowcy czekają na odpowiedzi.",
    "steps": [
        _s("b-zlecenia", "Zobacz zlecenia",
           "Otwórz zakładkę Zlecenia. Na górze są trzy kolejki: „Faktury do wprowadzenia”, „Faktury do zarchiwizowania” i „NIP-y do sprawdzenia”.",
           "Liczniki w nagłówkach pokazują, co czeka.", "/bok", "Zlecenia"),
        _s("b-nip", "Odpowiedz na NIP",
           "W „NIP-y do sprawdzenia” otwórz „[spółka]: wpisz wynik”. Wybierz: wolny i zarezerwowany, zajęty albo negatywny scoring. "
           "Dla wolnego ustaw datę ważności rezerwacji, dodaj uwagi i zapisz.",
           "Handlowiec widzi wynik na karcie klienta i w „Mój dzień”, w „Od BOK”.", "/bok", "Zlecenia"),
        _s("b-faktury", "Wprowadź dane z faktur",
           "W „Faktury do wprowadzenia” otwórz zadanie. Widzisz zdjęcia. Stuknij „Wpisz dane na karcie klienta”, dodaj punkt poboru i dane "
           "z faktur (ekran Dane), wróć i „Zamknij zadanie”.",
           "Handlowiec dostaje „dane z faktur gotowe”. Zdjęcia zostają do pobrania.", "/bok", "Zlecenia"),
        _s("b-archiwum", "Pobierz i zarchiwizuj faktury",
           "Zamknięte zadanie jest w „Faktury do zarchiwizowania”. Otwórz je, „Pobierz wszystkie faktury (ZIP)”, zapisz na dysku biura "
           "w dokumentacji klienta. Wróć, zaznacz potwierdzenie i „Usuń pliki z platformy”.",
           "Pliki znikają z platformy, dane na karcie klienta zostają, a na osi zdarzeń jest ślad archiwizacji.", "/bok", "Zlecenia"),
        _s("b-cenniki", "Zobacz cenniki spółek",
           "Podsekcja „Cenniki”. Lista spółek z ostrzeżeniem o wygasłych cennikach. Otwórz spółkę, „Nowy cennik”: formularz wypełniony "
           "poprzednimi cenami. Po zapisie projekt pokazuje zmiany wobec poprzedniego cennika, a zatwierdzenie jest osobnym krokiem. "
           "Zostają tylko obowiązujący i poprzedni. To dane demonstracyjne (ceny fikcyjne).",
           "Projekt cennika ze zmianami do zatwierdzenia.", "/cenniki", "Cenniki"),
    ],
}

OWNER = {
    "id": "wlasciciel",
    "title": "Właściciel: ustawienia i nadzór",
    "intro": "To, co ustawiasz tylko Ty i czego nie widzi nikt inny. Poniżej, w osobnej sekcji, kroki BOK, bo w tym teście grasz tę rolę.",
    "steps": [
        _s("o-pulpit", "Zobacz całe biuro",
           "Otwórz Portfel, Podsumowanie: sprzedaż miesiąca wobec targetu, przychód spółki, oferty złożone.",
           "Wyniki całego biura, także przychód spółki, którego nie widzi nikt poza Tobą.", "/pulpit", "Pulpit"),
        _s("o-spolki", "Reguły spółek",
           "Zakładka Spółki, otwórz spółkę. Udział brokera, pierwsza transza, limit marży z datą obowiązywania. Umowa zamraża reguły z dnia "
           "podpisania. Tych warunków nie widzi menedżer, handlowiec ani BOK.",
           "Reguły z historią zmian.", "/spolki", "Spółki"),
        _s("o-zespol", "Zespół i stawki",
           "Zespół, „Dodaj osobę”. Stawki prowizji (procent masy marży z własnych umów), przypisanie do menedżera, reset hasła "
           "(hasło losowe, pokazane raz). Sekcja „Udział w masie marży biura” pokazuje wszystkich.",
           "Lista osób ze stawkami.", "/zespol", "Zespół"),
        _s("o-konto", "Uprawnienia BOK i zasady biura",
           "Zakładka Konto. Uprawnienia BOK (co biuro może: zmiana statusów, wgląd w prowizje, import) i zasady biura (czy handlowcy "
           "widzą prognozę transzy B). Udziału brokera i Twojej marży BOK nie widzi nigdy.",
           "Przełączniki z historią zmian.", "/konto", "Konto"),
        _s("o-listy", "Listy wymagań",
           "Konto, „Listy wymagań”. Co jest potrzebne do oferty i do umowy. Handlowcy widzą te listy na kartach klientów.",
           "Dwie listy, które możesz edytować.", "/konto/listy", "Listy wymagań"),
        _s("o-uwagi", "Przeczytaj uwagi testerów",
           "Konto, „Uwagi testerów”. Wszystkie uwagi z każdej strony: kto, z jakiej strony, co. Oznaczaj jako załatwione.",
           "Lista uwag od najnowszych.", "/konto/uwagi", "Uwagi testerów"),
    ],
}

PLAN_TESTU = [
    "Handlowcy robią kroki od „Zobacz swój dzień” do „Wyślij NIP do BOK” i „Odeślij zdjęcia faktur”.",
    "Właściciel (w roli BOK) odpowiada na NIP-y i wprowadza dane z faktur w sekcji BOK.",
    "Handlowcy odbierają odpowiedź w „Mój dzień”, liczą ofertę w kalkulatorze i zapisują ją.",
    "Menedżer przegląda zespół, klientów i umowy handlowców.",
    "Wszyscy zgłaszają uwagi przez „Zgłoś uwagę do tej strony”: co było niejasne, czego brakowało, co nie działało.",
]


def sections_for(user: User) -> list[dict]:
    if user.role == ROLE_TRADER:
        return [COMMON, TRADER]
    if user.role == ROLE_MANAGER:
        return [COMMON, MANAGER]
    if user.role == ROLE_BOK:
        return [COMMON, BOK]
    if user.role == ROLE_OWNER:
        return [COMMON, OWNER, {**BOK, "id": "bok-wlasciciel", "title": "Zagraj BOK (w tym teście)"}]
    return [COMMON]


def all_keys(user: User) -> list[str]:
    return [s["key"] for sec in sections_for(user) for s in sec["steps"]]


def fill(text: str, user: User, nip: str) -> str:
    return text.replace("{nip}", nip).replace("{imie}", user.first_name or "Tester")


def done_keys(db: Session, user: User) -> set[str]:
    return set(db.scalars(select(TutorialProgress.step_key).where(TutorialProgress.user_id == user.id)))


def set_step(db: Session, user: User, key: str, done: bool) -> bool:
    """Zaznacza albo cofa krok. Zwraca False dla nieznanego klucza (np. kroku innej roli)."""
    if key not in all_keys(user):
        return False
    row = db.scalar(select(TutorialProgress).where(TutorialProgress.user_id == user.id, TutorialProgress.step_key == key))
    if done and not row:
        db.add(TutorialProgress(user_id=user.id, step_key=key, done_at=datetime.utcnow()))
    elif not done and row:
        db.delete(row)
    return True


def hide_invite(db: Session, user: User) -> None:
    if not db.scalar(select(TutorialProgress).where(TutorialProgress.user_id == user.id, TutorialProgress.step_key == HIDDEN_KEY)):
        db.add(TutorialProgress(user_id=user.id, step_key=HIDDEN_KEY))


def invite_visible(db: Session, user: User) -> bool:
    """Zaproszenie pokazujemy, dopóki osoba nie zrobiła żadnego kroku i go nie schowała."""
    return (db.scalar(select(func.count(TutorialProgress.id)).where(TutorialProgress.user_id == user.id)) or 0) == 0
