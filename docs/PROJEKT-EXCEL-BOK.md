# Projekt: Excele dla BOK, cenniki spółek (11.11.2026, do akceptacji)

Założenie do potwierdzenia: „docelowe excele dla BOK” to pliki, w których BOK
przygotowuje i aktualizuje cenniki spółek, bo to najczęstsza i najbardziej
pracochłonna czynność BOK (cennik zmienia się zwykle raz w tygodniu, w 12 i więcej
spółkach). Jeśli chodzi też o inne pliki BOK (rejestr rezerwacji NIP, listy klientów
do sprawdzenia), plan rozszerzamy w etapie D.

Zasady z `docs/STANDARD-WYMIANY-DANYCH.md` obowiązują bez zmian: jeden plik .xlsx,
arkusz README, polskie nazwy, przecinek i kropka, sprawdzenie bez zapisu, raport
błędów wiersz po wierszu, wszystko albo nic.

## Cel

Aktualizacja cenników spółek zajmuje BOK minuty, nie godziny. BOK nie przepisuje
ręcznie dziesiątek liczb (lata × grupy taryfowe × strefy × produkty), tylko pobiera
plik, wkleja nowe ceny i wgrywa go z powrotem.

## Jak to działa (propozycja)

1. **Pobranie arkusza spółki.** Na stronie cennika spółki: „Pobierz arkusz do
   uzupełnienia (Excel)”. Plik jest zbudowany ze struktury cennika tej spółki
   (produkty, okresy, grupy taryfowe albo przedziały wolumenu, strefy, opłata
   handlowa) i wypełniony ostatnimi cenami. Zmienia się tylko to, co BOK nadpisze.
2. **Wypełnienie.** BOK nadpisuje ceny w arkuszu (albo wkleja z pliku spółki) i
   ustawia „obowiązuje od”.
3. **Wgranie.** „Wgraj arkusz”. Platforma sprawdza plik i pokazuje raport, nic nie
   zapisując.
4. **Projekt cennika.** Po akceptacji raportu powstaje projekt cennika, czyli to samo,
   co dziś daje formularz. Dalej bez zmian: ekran „Zmiany wobec poprzedniego cennika”,
   zatwierdzenie, nowy cennik kończy poprzedni z końcem dnia.
5. **Zatwierdzenie** jak dziś, osobnym krokiem. Wgranie pliku nigdy samo nie zmienia
   cen, z których liczy kalkulator.

Wniosek techniczny: wczytanie przepisuje komórki na te same klucze, które ma formularz
(`price_key`, `oh_key` w `app/cenniki.py`) i woła istniejące `save_draft`. Dzięki temu
walidacja, projekt i zatwierdzanie są jednym kodem, a nie dwoma.

## Układ arkusza spółki

- `README`: wersja standardu (1.3), nazwa spółki, jak wypełniać, co jest zablokowane.
- `ceny`: wiersze to segment i strefa (np. „C12a, strefa I”), kolumny to produkt i
  okres (np. „FIX 2027”, „FIX 2027–2028”). Wiersz nagłówków i kolumna segmentów
  opisane w pełni, żeby czytnik ekranu czytał sensowne komórki.
- `oplata_handlowa`: opłata handlowa zł/miesiąc/punkt poboru według segmentu.
- `dane`: obowiązuje od, obowiązuje do (opcjonalnie), uwagi.
- Struktura (kolumny, wiersze) jest tylko do odczytu. Jeśli spółka zmieni strukturę
  (nowy rok, nowa grupa), robi to BOK w „Budowa cennika”, a potem pobiera nowy arkusz.
  Plik ze starą strukturą jest odrzucany z jasnym komunikatem.

## Sprawdzenia przy wgraniu

- Plik z arkusza innej spółki albo starej struktury: odrzucony.
- Cena pusta, tekst, ujemna lub równa zero: błąd z adresem komórki
  („arkusz ceny, wiersz 9, kolumna FIX 2028: podaj cenę w zł/MWh”).
- Zmiana większa niż próg względem poprzedniego cennika (propozycja: 15 procent):
  ostrzeżenie, nie błąd. Wyłapuje literówki typu 5 zamiast 500.
- Brak ceny na rok, który spółka wcześniej miała: ostrzeżenie.
- Data „obowiązuje od” w przeszłości o więcej niż dobę: ostrzeżenie.
- Liczby z przecinkiem, kropką i spacją w tysiącach przyjmujemy.
- Ceny, których BOK nie ruszył, zostają jak w poprzednim cenniku.

## Uprawnienia i poufność

- Wgrywa BOK i właściciel, czyli ci sami, którzy dziś wpisują cenniki. Osobny
  przełącznik nie jest potrzebny.
- Plik zawiera wyłącznie ceny. Nigdy udziału brokera, warunków umowy agencyjnej ani
  prowizji. Tych kolumn w arkuszu nie ma.
- Cenniki spółek są poufne. Propozycja: po przetworzeniu nie przechowujemy wgranego
  pliku, tylko zapisane ceny, autora i datę (do decyzji, patrz pytania).

## Etapy

- **A. Arkusz jednej spółki** (pobranie, wgranie, raport, projekt). Najmniejszy
  kawałek, który daje korzyść od pierwszego tygodnia.
- **B. Plik zbiorczy.** Jeden plik dla wielu spółek (arkusz długi: spółka, produkt,
  okres, segment, strefa, cena), do pierwszego wczytania cenników wszystkich spółek
  albo do tygodniowej aktualizacji hurtem.
- **C. Wersja cennika w ofercie** i alarm wygasłych cenników w „Zleceniach” BOK
  (częściowo jest).
- **D. Inne pliki BOK**, jeśli są potrzebne (rejestr rezerwacji NIP, lista klientów do
  sprawdzenia). Osobny projekt po odpowiedzi na pytanie 1.
- Poza planem, ale na tym samym formacie: czytanie PDF przez AI wypełni ten sam
  projekt cennika do zatwierdzenia (etap 2 z `docs/PROJEKT-CENNIKI.md`).

## Wdrożenie u BOK (jak wprowadzamy to w praktyce)

1. **Struktury prawdziwych spółek.** Dla każdej z Twoich spółek ustalamy strukturę:
   medium, produkty, lata, grupy albo przedziały wolumenu, strefy, opłata handlowa.
   Same struktury, bez cen. Potrzebuję ich od Ciebie lub BOK (patrz pytanie 2).
2. **Budowa cenników** w „Budowa cennika” dla każdej spółki (BOK, jednorazowo).
3. **Etap A** w kodzie i testach, potem wdrożenie Twoim ręcznym wdrożeniem.
4. **Pilot na dwóch spółkach** przez tydzień: jednej z podziałem na grupy taryfowe i
   jednej z podziałem na wolumen. BOK robi aktualizację tygodniową obiema drogami
   (formularz i Excel) i porównuje wyniki. Zmierzymy czas.
5. **Wszystkie spółki.** Dopiero po pilocie.
6. **Etap B** po tygodniu pracy na etapie A, jeśli BOK nadal traci czas na wiele plików.

## Testy

- Jednostkowe: przepisanie komórek na klucze formularza, rozpoznanie struktury, adresy
  błędów, progi zmian, liczby z przecinkiem i spacją.
- Cykl pełny: pobranie arkusza, zmiana cen, wgranie, projekt, zatwierdzenie, a
  kalkulator liczy po nowych cenach; ceny, których nie ruszono, zgadzają się z poprzednimi.
- Zachowanie: niezmienione ceny zostają, plik innej spółki odrzucony, plik uszkodzony
  lub zbyt duży odrzucony bez błędu serwera, stary projekt zastąpiony nowym.
- Poufność: w pliku nie ma żadnych danych właściciela; handlowiec i menedżer nie mają
  dostępu do pobierania ani wgrywania.
- Dostępność: strona pobrania i wgrania bez JavaScriptu, raport w `role="alert"`,
  sprawdzony na drzewie dostępności. Wgrywanie pliku z telefonu przez standardowy
  wybór pliku.
- Test „złośliwych danych” z `CLAUDE.md` na nowych adresach, na PostgreSQL 16.

## Pytania do właścicielki

1. Czy „docelowe excele” to wyłącznie cenniki spółek, czy BOK ma też inne pliki, które
   mamy zastąpić (rejestr rezerwacji NIP, listy do sprawdzenia)? Które?
2. Ile spółek ma być w pierwszym wdrożeniu i kto poda ich struktury (Ty czy BOK)?
3. Jak BOK dostaje dziś ceny: z PDF, z e-maila, z Excela spółki? Od tego zależy, czy
   wystarczy arkusz platformy, czy potrzebny jest też konwerter pliku spółki.
4. Co z plikiem po wgraniu: przechowywać go w platformie jako dowód, czy usuwać i
   zostawić tylko zapisane ceny (ostrożniej wobec poufności cenników)?
5. Ostrzeżenie o dużej zmianie ceny: od jakiego progu? Propozycja 15 procent względem
   poprzedniego cennika.
6. Kto zatwierdza po wgraniu: ten sam BOK, który wgrał, czy dopiero druga osoba lub
   Ty? Dziś zatwierdza ten, kto wpisał.
