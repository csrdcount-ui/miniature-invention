# Platforma brokerska — zasady pracy

Aplikacja dla polskich firm brokerskich na rynku energii elektrycznej i gazu:
prowizje, umowy, zespół, a docelowo lejek sprzedaży, rezerwacje NIP i BOK.

## O właścicielce projektu

- Ekspertka rynku energii w Polsce. Pracuje głównie na telefonie, z czytnikiem
  ekranu (jest osobą niewidomą).
- Odpowiedzi: po polsku, klarownie, precyzyjnie, szczerze, w oparciu o sprawdzone
  dane. Nagłówki i listy zamiast szerokich tabel. Bez zgadywania faktów branżowych:
  jeśli brakuje wiedzy, zapytaj.
- Wiadomości bywają dyktowane: nazwy własne mogą być przekręcone. Dopytaj zamiast
  powtarzać niepewną nazwę jako fakt.

## Zasady nadrzędne

1. **Render: żadnej akcji bez zgody.** Przed każdą akcją w Renderze (tworzenie,
   zmiana planu, zatwierdzanie planu Blueprintu, zmienne środowiskowe, usuwanie)
   napisz, co chcesz zrobić i dlaczego, i poczekaj na odpowiedź. Odczyty stanu są
   dozwolone.
2. **Testy przed każdym wypchnięciem.** `python -m pytest -q` musi przejść w całości.
   Push na `main` sam uruchamia wdrożenie (autoDeploy), więc main ma być zawsze zdrowy.
3. **Poufność warunków właściciela.** Udział brokera u spółki obrotu i marżę
   właściciela widzi wyłącznie właściciel. Nigdy menedżer, handlowiec ani BOK.
   Silnik prowizji liczy na serwerze.
4. **Dostępność.** Strony działają bez JavaScriptu, z czytnikiem ekranu i na telefonie:
   etykiety pól, komunikaty w `role="status"`/`role="alert"`, `aria-current` w nawigacji,
   cele dotyku min. 44 px, karty zamiast szerokich tabel na telefonie.
5. **Język:** interfejs, komunikaty błędów i commity po polsku.
6. **Migracje danych na produkcji.** `create_all` nie zmienia istniejących tabel.
   Nowe kolumny dodawaj w `app/migrate.py` (idempotentnie) i sprawdzaj na
   PostgreSQL 16 (lokalny klaster: `pg_ctlcluster 16 main start`) bazą utworzoną
   poprzednią wersją kodu, np. przez `git worktree` i `python -m app.demo`.

## Przypomnienie przed pilotażem

Darmowa baza Render wygasa po 30 dniach (utworzona ok. 5.11.2026). Przed pierwszym
pilotażem z brokerem: serwer na plan **Starter**, baza na **Basic-256mb**.
Przypomnij o tym, gdy aplikacja będzie gotowa do pokazania. Zmiana planu to akcja
w Renderze — tylko za zgodą.

## Wdrożenie

- GitHub `csrdcount-ui/miniature-invention`, gałąź `main` (domyślną w GitHubie
  ustawia właścicielka ręcznie).
- Render, region Frankfurt, Blueprint „Aplikacja” (`exs-dbmc5cgae00c738urihg`),
  serwis `platforma-brokerska` (`srv-dbmc7cetlv9c73duncgg`),
  baza `platforma-brokerska-db`. Adres: https://platforma-brokerska.onrender.com
- Narzędzia Render w sesji wymagają numeru przestrzeni roboczej (`tea-…`), którego
  dotąd nie udało się ustalić. Sieć sesji w chmurze blokuje domeny Rendera.
- W tej samej przestrzeni jest inny serwis, `energia-lublina-crm` — nie dotykać.

## Budowa kodu (modularny monolit, jedna baza)

- `app/main.py` — złożenie aplikacji, start, migracje, obsługa błędów.
- `app/web/` — `ui.py` (szablony, formatowanie, sesja, CSRF), `auth.py` (użytkownik,
  role, uprawnienia BOK, wymuszenie uzupełnienia danych), `forms.py` (walidacja),
  `navigation.py` (zakładki i podsekcje).
- `app/routes/` — strony według modułów: konto, portfel, spolki, zespol, raporty.
  Nowy moduł = nowy plik z `router` dodany w `main.py`.
- `app/services.py` — logika biznesowa i widoki przycięte do roli.
- `app/engine.py` — silnik prowizji (czyste funkcje, Decimal).
- `app/models.py`, `app/migrate.py`, `app/demo.py` (dane demo na pustej bazie).
- Test pilnuje, że `engine`, `services`, `models`, `migrate` nie importują FastAPI
  ani warstwy stron.

Uruchomienie lokalne: `pip install -r requirements-dev.txt`,
`python -m pytest -q`, `uvicorn app.main:app --reload`.
Kwoty formatowane z twardą spacją (U+00A0) — w testach używaj ` `.

## Stan prac

Zrobione: nawigacja z zakładkami pod kciukiem, imię i nazwisko osobno, nazwa firmy
w belce, historia statusów umów, podział kodu na moduły, rola BOK z przełącznikami.

Następne (w tej kolejności, po odpowiedziach na pytania niżej):
1. Moduł sprzedażowy: klient i punkt poboru, rezerwacje NIP (karta spółki z częścią
   BOK i szablonami e-maili), szansa i etapy lejka, „Mój dzień”, oferty z cennikiem
   i kalkulatorem prowizji, wycena indywidualna.
2. Analityka portfela, zespołu i raporty (propozycja w docs).
3. Import i migracja danych z innych CRM-ów (standard Excela + mapowanie kolumn).
4. Treści podpowiedzi sprzedażowych — osobna rozmowa; w systemie tylko miejsca na treści.
   Bez nazwy „Sandler” (zastrzeżona marka).

## Dokumentacja

- `docs/PROPOZYCJA-v1.0-v1.1.md` — plan wersji 1.0 i 1.1, moduł sprzedażowy.
- `docs/WIEDZA-BRANZOWA.md` — potwierdzona wiedza: rezerwacja NIP, oferty, cenniki,
  dokumenty, BOK, karta spółki. Szkic sekcji do skilla „rynek-brokerski-energii-pl”.
- `docs/RAPORT-etap-1.md` — raport z etapu 1.

## Otwarte pytania do właścicielki

Rezerwacja i dokumenty:
- Kto decyduje o przedłużeniu rezerwacji i na jak długo zwykle?
- Co dokładnie znaczy „regres” (odrzucenie/cofnięcie umowy przez spółkę z braków?).
- Jak klient akceptuje ofertę w systemie spółki (SMS, podpis elektroniczny, link)?
- Scoring: z jakich wywiadowni korzystają (KRD i inne)? Wpis ręczny z PDF czy integracja?

Uprawnienia BOK:
- Czy BOK może przepinać klientów i zmieniać statusy domyślnie? (Dziś: statusy tak,
  przepinanie nie; właściciel przełącza.)
- Czy w BOK bywa kilka osób z kierownikiem i podziałem pracy, np. według spółek?

Oferty i ceny:
- Forma cenników w spółkach bez własnego systemu (Excel, PDF)?
- Produkty w cennikach (stała, indeks, mix), zależność od okresu i taryfy.
- Ważność wyceny indywidualnej.

Klienci, migracja, pliki:
- Gospodarstwa domowe czy tylko firmy?
- Klient z wieloma punktami poboru: jedna umowa czy kilka?
- Z jakich CRM-ów migrujemy; zanonimizowany eksport do analizy.
- Czy przenosimy historię wypłaconych prowizji i korekt?
- Zgoda na płatny magazyn plików w UE (Frankfurt) i okres przechowywania dokumentów (RODO).
