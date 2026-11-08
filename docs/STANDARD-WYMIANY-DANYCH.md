# Standard wymiany danych (import i eksport Excela), wersja robocza 0.1

Stan: PROJEKT do akceptacji. Nic z tego nie jest jeszcze w kodzie.
Decyzje właścicielki z 8.11.2026 (sekcja na końcu) mają pierwszeństwo przed resztą pliku.
Cel: jeden plik .xlsx, który (1) służy do wczytania portfela z innego CRM-u,
(2) jest wynikiem eksportu z platformy, (3) zawiera dane przykładowe na pokaz.

## Zasady ogólne

- Jeden plik .xlsx, osobny arkusz na każdy rodzaj danych, pierwszy wiersz to nazwy kolumn.
- Arkusz `README` na początku: wersja standardu (`standard: 1.0`), opis arkuszy, opis
  kolumn (nazwa, typ, wymagana, dozwolone wartości, przykład). Plik sam się tłumaczy.
- Nazwy kolumn po polsku, bez spacji i polskich znaków w nazwach technicznych
  (np. `data_podpisania`), żeby konwertery z innych CRM-ów łatwo je mapowały.
- Liczby: przyjmujemy przecinek i kropkę, spacje w tysiącach. Daty: RRRR-MM-DD albo
  DD.MM.RRRR. Wartości tak/nie: `tak`, `nie`, `1`, `0`.
- Każdy rekord ma `id_zewn`: identyfikator ze starego systemu. Dzięki niemu ponowny
  import tego samego pliku nie tworzy duplikatów, tylko aktualizuje rekordy.
- Wersjonowanie: kolumny można dodawać, nie zmieniać znaczenia istniejących.
  Stary plik z wcześniejszej wersji standardu nadal się wczyta.

## Arkusze

### 1. `zespol` (osoby)
`id_zewn`, `imie`, `nazwisko`, `email`, `rola` (wlasciciel / menedzer / handlowiec / bok),
`menedzer_email`, `aktywny`, `data_rozpoczecia_wspolpracy`,
`udzial_w_narzucie_proc`, `override_proc`, `baza_override` (narzut / udzial_handlowca).
Hasła nie są w pliku. Importowane osoby dostają hasło jednorazowe do zmiany.

### 2. `spolki` (spółki obrotu i ich reguły, tylko właściciel)
`id_zewn`, `nazwa`, `aktywna`, `obowiazuje_od`, `udzial_brokera_proc`,
`pierwsza_transza_proc`, `wyzwalacz_transzy`, `limit_narzutu_zl_mwh`,
`nowe_przylacza_miesiace`, `tryb_korekty`, `uwagi`.

### 3. `klienci` (po wprowadzeniu modułu klientów)
`id_zewn`, `nip`, `nazwa`, `adres`, `osoba_kontaktowa`, `telefon`, `email`,
`handlowiec_email` (właściciel klienta w biurze).

### 4. `punkty_poboru` (po wprowadzeniu modułu klientów)
`id_zewn`, `klient_nip`, `numer_punktu`, `medium` (energia / gaz), `grupa_taryfowa`,
`osd`, `roczne_zuzycie_mwh`, `obecny_sprzedawca`, `koniec_obecnej_umowy`,
`okres_wypowiedzenia_miesiace`.

### 5. `umowy`
`id_zewn`, `klient_nazwa`, `klient_nip`, `medium`, `spolka`, `handlowiec_email`,
`data_podpisania`, `start_dostaw`, `okres_miesiace`, `wolumen_roczny_mwh`,
`cena_bazowa_zl_mwh`, `narzut_zl_mwh`, `nowe_przylacze`, `status`,
`punkty_poboru` (numery oddzielone średnikiem, gdy moduł punktów jest wdrożony).

Warunki zamrożone w dniu podpisania (tylko właściciel, opcjonalne):
`udzial_brokera_proc`, `pierwsza_transza_proc`, `udzial_handlowca_proc`,
`override_menedzera_proc`, `baza_override`, `tryb_korekty`.
Jeśli puste, platforma użyje reguł spółki obowiązujących w dniu podpisania. Jeśli
wypełnione, umowa historyczna zachowa swoje prawdziwe warunki i nie zostanie przeliczona
według obecnych reguł.

### 6. `historia_statusow`
`umowa_id_zewn`, `status`, `data_zdarzenia`, `notatka`, `kto_email`.
Pozwala przenieść prawdziwą historię lejka. Bez tego arkusza umowa dostaje jeden wpis
„stan w chwili importu”.

### 7. `wyplaty_i_korekty` (opcjonalny)
`umowa_id_zewn`, `typ` (transza / faktura / korekta), `strona` (broker / handlowiec /
menedzer), `kwota_zl`, `data`, `opis`. Chroni przed ponowną wypłatą tego, co już wypłacono.

## Przebieg importu

1. Wgranie pliku (strona w zakładce Konto, tylko właściciel; uprawnienie dla BOK
   do ustalenia).
2. Sprawdzenie bez zapisywania. Raport błędów wiersz po wierszu, czytelny dla czytnika
   ekranu: „arkusz umowy, wiersz 14, kolumna nip: niepoprawna suma kontrolna”.
3. Podsumowanie: ile rekordów nowych, ile do aktualizacji, ile błędnych, ostrzeżenia
   (np. umowa z limitem narzutu przekroczonym).
4. Zatwierdzenie. Zapis w jednej transakcji: albo wszystko, albo nic.
5. Możliwość cofnięcia całej paczki importu (każdy rekord pamięta, z której paczki pochodzi).

## Eksport i poufność

- Właściciel: pełny plik, wszystkie arkusze, także warunki ze spółkami i marża.
- Menedżer: umowy i zespół swojego zespołu, bez warunków właściciela.
- Handlowiec: własne umowy i klienci, bez warunków właściciela.
- BOK: według przełączników uprawnień (domyślnie bez prowizji).
- Plik eksportu można wczytać z powrotem (ten sam standard).

## Konwertery z innych CRM-ów

Zamiast osobnego programu dla każdego systemu: ekran mapowania kolumn („ta kolumna z ich
pliku to nasze pole X”) z zapisywanymi profilami, np. „Pipedrive”, „Excel biura Y”.
Gotowe profile dla najpopularniejszych systemów po analizie prawdziwych eksportów.

## Dane przykładowe

- Ten sam plik w standardzie, wczytywany przyciskiem „Wczytaj dane przykładowe”.
- Wszystkie rekordy przykładowe są oznaczone jako demo i usuwane jednym przyciskiem,
  bez dotykania danych prawdziwych.
- Zestaw ma pokazywać funkcje: portfel zagrożony, zerwane umowy z korektami, różne
  spółki z różnymi regułami, handlowcy o różnej skuteczności, odnowienia w najbliższych
  miesiącach, nowe przyłącza, prognozę na 2028.

## Decyzje właścicielki z 8.11.2026

- **Eksport danych klientów jest odłożony** do czasu, aż system będzie dopracowany.
  Pierwszy etap to import i dane przykładowe. Poufność eksportu opisana wyżej zostaje
  jako założenie na później.
- **Każdy broker ma inny zestaw danych.** Dlatego import przechodzi przez konwerter na
  nasz standard (mapowanie kolumn z zapisywanymi profilami), a nie wymaga, żeby broker
  przygotował plik w naszym układzie.
- **Brakujące dane:** system nie zgaduje. Tworzy listę braków („do uzupełnienia”), a
  każdy brak ma przypisaną rolę odpowiedzialną: właściciel (np. warunki ze spółkami,
  zamrożone udziały) albo BOK (dane operacyjne).
- **Kto importuje:** domyślnie wyłącznie właściciel. Właściciel może przekazać BOK
  część zadań. BOK może importować i aktualizować: zespół, handlowców i menedżerów,
  umowy oraz statusy obecnie obowiązujących umów. BOK nigdy nie importuje spółek
  obrotu i ich reguł (umowy agencyjne): to zawsze tylko właściciel. Przełącznik
  w ustawieniach konta, jak pozostałe uprawnienia BOK, z historią zmian.
- **Dane przykładowe (demo)** służą do pokazów dla brokerów: spółki obrotu z prawdziwymi
  nazwami rynkowymi, ale warunki umów agencyjnych są fikcyjne i tak oznaczone na ekranie.
  Dane właściciela i nazwę firmy wpisuje właścicielka, demo ich nie dotyka.
