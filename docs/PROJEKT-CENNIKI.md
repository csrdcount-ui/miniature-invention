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

## Otwarte pytania (zadane 10.11.2026)
Patrz rozmowa: strefy (jedna marża na wszystkie strefy?), umowy wieloletnie (jedna cena
czy cena na każdy rok?), „w tym prowizja partnera”, OH i gwarancje pochodzenia
w kalkulatorze.
