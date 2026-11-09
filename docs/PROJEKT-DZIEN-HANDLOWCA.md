# Projekt: dzień handlowca (propozycja z 10.11.2026, do akceptacji)

Rozwija sekcję „Moduł sprzedażowy handlowca” z `docs/PROPOZYCJA-v1.0-v1.1.md`
o ekran dnia, kalendarz, następny krok i podpowiedzi na etapach. Fakty branżowe
pochodzą z `docs/WIEDZA-BRANZOWA.md`. Treści podpowiedzi (pytania, obiekcje) pisze
właścicielka; aplikacja daje na nie miejsca i sama dokłada tylko kontrole wynikające z danych.

## Zasada przewodnia

Każda otwarta szansa ma zawsze **następny krok z datą**. Szansa bez następnego kroku
trafia do „Pilne”. Na tym opiera się cały ekran dnia i wszystkie dane dla menedżera.

## Ekran „Mój dzień” (pierwszy ekran handlowca, zamiast dzisiejszego pulpitu)

Kolejność od góry, na telefonie tylko listy, reszta zwinięta:

1. Jedna linia celu: „Listopad: 62% targetu, brakuje 57 000 zł”.
2. **Pilne**:
   - zaległe kroki i zadania;
   - rezerwacje NIP wygasające w ciągu 7 dni (przedłużenie wymaga dowodów rozmów);
   - nowy cennik spółki: oferta z poprzedniego ważna tylko do końca doby;
   - oferty bez decyzji klienta dłużej niż 14 dni;
   - szanse bez następnego kroku.
3. **Dziś**: spotkania i telefony z godziną, potem zadania bez godziny.
   Przy każdej pozycji: „Zrobione, zapisz wynik”, „Przełóż”.
4. **Okazje**: klienci, u których zbliża się ostatni dzień na wypowiedzenie umowy
   u obecnego sprzedawcy (data końca minus okres wypowiedzenia), oraz odnowienia
   własnych umów biura.
5. **Od BOK**: rezerwacja potwierdzona albo odmowa, scoring (zielone światło albo
   nie ofertować), braki w dokumentach.
6. Zwinięte: „Mój lejek” (liczba szans i wartość na każdym etapie), „Tydzień”
   (plan na 7 dni), „Statystyki sprzedaży” (jak dziś).

Na górze stały przycisk „Szybki lead”: nazwa firmy, telefon, opcjonalnie NIP,
notatka. Pole notatki działa z dyktowaniem w telefonie.

## Lejek dla brokera energii (propozycja etapów)

1. Lead: pozyskany kontakt.
2. Rozmowa: pierwsza rozmowa odbyta, jest osoba decyzyjna.
3. Dokumenty: faktury dystrybucyjne, zużycie roczne, punkty poboru, data końca
   umowy i okres wypowiedzenia u obecnego sprzedawcy.
4. Rezerwacja i scoring: BOK rezerwuje NIP w wybranych spółkach, sprawdza scoring.
   Wynik: mapa dostępności klienta (gdzie można ofertować).
5. Oferta: z cennika albo, powyżej progu spółki (1, 2 lub 4 GWh), wniosek o wycenę
   indywidualną z profilem zużycia.
6. Decyzja klienta: negocjacje, przypomnienia.
7. Podpisanie: Autenti, SMS albo papier.
8. Wygrana: powstaje umowa (dzisiejszy obiekt), przekazanie do BOK
   (kompletność dokumentów, wysyłka do spółki).

Przegrana zawsze z powodem: cena, zostaje u obecnego sprzedawcy, inny broker,
rezerwacja zajęta we wszystkich spółkach, scoring negatywny, brak decyzji, inny.

## Podpowiedzi na każdym etapie

Trzy warstwy na karcie szansy, pod przyciskiem „Podpowiedź do etapu”:

1. **Czego brakuje, żeby przejść dalej**: liczone z danych, np. „brak faktury
   dystrybucyjnej”, „nie znamy okresu wypowiedzenia”, „wolumen 2,4 GWh, w Enea
   potrzebna wycena indywidualna”, „rezerwacja w Tauron wygasa za 5 dni”.
2. **Co zrobić teraz**: krótka lista kroków etapu, edytowana przez właściciela.
3. **Pytania i obiekcje**: treści właściciela dla etapu (bez nazwy „Sandler”).

Kalkulator przy ofercie: handlowiec wpisuje marżę i od razu widzi swoją prowizję
i ostrzeżenie o limicie marży spółki. Udział brokera u spółki pozostaje ukryty.

## Kalendarz

- W aplikacji: lista dzień po dniu (agenda), nie siatka miesiąca. Siatka jest
  nieczytelna z czytnikiem ekranu i na telefonie.
- Synchronizacja z kalendarzem w telefonie: prywatny adres subskrypcji (format ICS).
  Spotkania i zadania pojawiają się w kalendarzu Google albo Apple, z ich
  powiadomieniami. Działa w jedną stronę: z aplikacji do telefonu.
- Dwustronna synchronizacja z Google Calendar wymaga osobnej integracji
  z logowaniem Google: później, jeśli będzie potrzebna.

## Co zyskuje menedżer i właściciel

- Szanse bez następnego kroku, utknięte na etapie (czas na etapie).
- Aktywność: rozmowy i spotkania w tygodniu na handlowca.
- Skuteczność: oferta do umowy, liczona z obiektu oferty.
- Powody przegranych według handlowca i spółki.
- Wartość lejka ważona etapem i portfel do odnowienia w 12 miesiącach.

## Nowe obiekty w bazie

Klient, punkt poboru (z datą końca obecnej umowy i okresem wypowiedzenia),
szansa (etap, następny krok z datą), rezerwacja NIP (klient i spółka, obsługuje BOK),
oferta (szansa i spółka, z cennika albo wycena), zdarzenie (spotkanie, telefon,
zadanie, notatka; z datą, godziną i wynikiem). Wygrana szansa tworzy umowę.
Dzisiejsze umowy w statusie Lead, Kontakt i Oferta przechodzą do szans przy migracji.

## Etapy wdrożenia (każdy do osobnego wdrożenia i testu)

1. Klient, punkt poboru, szansa z etapami, następny krok, zadania, ekran „Mój dzień”,
   szybki lead, migracja dzisiejszych ofert.
2. Rezerwacje NIP i scoring: wspólnie z uporządkowaniem BOK.
3. Oferty z kalkulatorem prowizji, wersje cennika, wygrana zamienia się w umowę.
4. Kalendarz w telefonie (ICS), podpowiedzi na etapach, raporty lejka dla menedżera.

## Pytania do właścicielki

1. Czy etapy lejka i ich nazwy są dobre?
2. Podpowiedzi: piszesz treści sama, czy przygotować wersję startową do poprawienia?
3. Kalendarz: wystarczy subskrypcja w telefonie, czy biuro pracuje na Google Calendar
   i potrzebna jest synchronizacja w obie strony?
4. Źródło leada (polecenie, zimny telefon, kampania, strona): zbierać do statystyk?
5. Czy próg „oferta bez decyzji” 14 dni i „rezerwacja wygasa” 7 dni są właściwe?
