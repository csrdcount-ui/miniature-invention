# Projekt: cenniki i kalkulator (10.11.2026, do akceptacji)

Decyzja właścicielki: ceny wpisuje BOK w formularzu dla każdej spółki, zatwierdza
i dopiero wtedy trafiają do kalkulatora. Handlowiec nie wpisuje cen z cenników.
Czytanie PDF przez AI to etap 2: wypełnia ten sam formularz jako projekt do zatwierdzenia.

## Model danych
- Struktura cennika spółki (ustawiana raz, zmieniana rzadko): medium, produkty (FIX,
  RDN), lata dostaw, wymiar podziału (grupy taryfowe ze strefami albo przedziały
  wolumenu), opłata handlowa (od grupy albo stała), zakres „dla klientów do X MWh”,
  próg wyceny indywidualnej.
- Cennik: spółka, ważny od (data i godzina), ważny do (opcjonalnie), kto wpisał, kto
  zatwierdził, status (projekt, zatwierdzony). Nowy cennik kończy poprzedni z końcem dnia.
- Pozycja: produkt, rok, grupa taryfowa albo przedział wolumenu, strefa, cena zł/MWh;
  osobno OH zł/miesiąc/punkt poboru.

## BOK
- Zakładka „Cenniki”: spółki z datą ostatniego cennika i ostrzeżeniem, gdy cennik
  wygasł.
- „Nowy cennik” otwiera formularz wypełniony poprzednimi cenami, podzielony na lata
  (zwijane sekcje), pola opisane w pełni („2026, C12a, strefa I, zł/MWh”).
- Zatwierdzenie pokazuje zmiany wobec poprzedniego cennika.

## Kalkulator (handlowiec)
- Dane z karty klienta: grupa taryfowa albo wolumen, start i okres umowy.
- Ceny bazowe z zatwierdzonych cenników spółek, w których NIP klienta jest wolny.
- Wynik dla każdej spółki: marża, cena dla klienta w każdej strefie i w każdym roku,
  OH, prowizja handlowca, pierwsza transza; ostrzeżenia: brak ceny na któryś rok,
  wolumen ponad zakres cennika (wycena indywidualna), marża ponad limit, cennik z dziś.
- Oferta zapamiętuje wersję cennika.

## Stan (10.11.2026)

ZROBIONE etap 1: `app/cenniki.py`, `app/routes/cenniki.py`, modele PriceTemplate, PriceList,
PriceItem (nowe tabele). Zakładka BOK „Zlecenia” → podsekcja „Cenniki”; właściciel: Spółki →
Cenniki. Kalkulator na karcie klienta czyta tylko zatwierdzone cenniki. Bloki lat wygrywają,
gdy pokrywają dokładnie lata umowy; inaczej średnia ważona miesiącami. Marża osobno na
każdą strefę, udział stref do masy marży. OH stała albo z dopłatą (dopłata pokazana jako
przychód biura, poza prowizją handlowca — podział do ustalenia). „Zapisz ofertę w tej
spółce” przepisuje średnią ważoną cenę bazową i marżę do formularza oferty. Demo: 13
cenników 12 spółek (fikcyjne ceny), w tym zmiana cennika dziś i wygasły cennik.

Otwarte: „w tym prowizja partnera” (PST), udział handlowca w dopłacie do OH, import
cennika z Excela, czytanie PDF przez AI (etap 2), oferty specjalne, gwarancje pochodzenia,
wycena indywidualna, zapamiętanie wersji cennika w ofercie.
