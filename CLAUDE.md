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
   Push na `main` NIE uruchamia wdrożenia (patrz „Procedura wdrożenia”), ale main ma
   być zawsze zdrowy, bo właścicielka wdraża z niego ręcznie.
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

7. **Koszt klikania w panelach.** Panele GitHuba i Rendera słabo współpracują z
   czytnikiem ekranu, a właścicielka traci na nich pół dnia (zrzuty ekranu,
   przeklikiwanie menu). Zanim zaproponujesz cokolwiek, co wymaga jej ręcznych zmian
   w GitHubie lub Renderze, ostrzeż o tym wprost, na początku odpowiedzi: co to
   jest, ile kroków, czy jest konieczne. Domyślnie wybieraj rozwiązania w kodzie i w
   repozytorium. Nie dawaj takich kroków jako „zadań do zrobienia”, jeśli aplikacja
   działa bez nich. Zrób sam wszystko, co da się przez dostępne narzędzia.

8. **Kod w repozytorium to nie wdrożenie.** Po wypchnięciu pisz „zmiana jest w
   kodzie na main”, nigdy „wdrożone” ani „działa na serwerze”, dopóki nie ma
   potwierdzenia. Potwierdzeniem jest strona https://platforma-brokerska.onrender.com/wersja
   z numerem ostatniego commitu (Render podaje go w RENDER_GIT_COMMIT). Sesja w chmurze
   nie ma dostępu do domen Rendera, więc numer z /wersja podaje właścicielka.
   8.11.2026 na serwerze działała jeszcze wersja sprzed commitu 51e0182, mimo
   późniejszych wypchnięć — podejrzenie: autoDeploy wyłączony w serwisie.

## Procedura wdrożenia (ustalona 8.11.2026)

Auto-Deploy nie działa, a właścicielce nie przeszkadza ręczne wdrażanie (kilka
stuknięć, max minuta). Przy każdej większej porcji zmian daj jej na początku
odpowiedzi tę instrukcję, z linkiem i wskazaniem sekcji:

1. Otwórz stronę serwisu: https://dashboard.render.com/web/srv-dbmc7cetlv9c73duncgg
   (adresu nie sprawdzono, jeśli nie działa: Render, lista serwisów, platforma-brokerska).
2. Na górze strony, pod nazwą serwisu, są dwa przyciski: „Connect” i „Manual Deploy”.
3. Stuknij „Manual Deploy”, potem „Deploy latest commit”.
4. Napisz „zrobione”. Resztę sprawdza asystent przez `list_events` (deploy_ended
   ze statusem succeeded, ok. 1–2 min po starcie).
5. Potwierdzenie: https://platforma-brokerska.onrender.com/wersja pokazuje numer
   ostatniego commitu.

Zawsze kończ tę instrukcję i każde "sprawdź, czy wdrożenie się udało" linkiem
do aplikacji, jako osobna linia na końcu wiadomości (prosiła o to 8.11.2026,
bo ciągle gubi link wklejony gdzie indziej):
https://platforma-brokerska.onrender.com

Nie proś o nic więcej w panelu. Sekcji „Auto-Deploy” właścicielka nie znalazła; nie
wracaj do tego.

## Przypomnienie przed pilotażem

Darmowa baza Render wygasa po 30 dniach (utworzona ok. 5.11.2026). Przed pierwszym
pilotażem z brokerem: serwer na plan **Starter**, baza na **Basic-256mb**.
Przypomnij o tym, gdy aplikacja będzie gotowa do pokazania. Zmiana planu to akcja
w Renderze — tylko za zgodą.

## Wdrożenie

- GitHub `csrdcount-ui/miniature-invention`, gałąź `main`. Domyślna gałąź w GitHubie
  to nadal stara `ccr-fcf28ba4-j6eqkl`; zmiana wymaga klikania w ustawieniach i jest
  opcjonalna, aplikacja działa bez niej. Nie ponaglaj.
- Render, region Frankfurt, Blueprint „Aplikacja” (`exs-dbmc5cgae00c738urihg`),
  serwis `platforma-brokerska` (`srv-dbmc7cetlv9c73duncgg`),
  baza `platforma-brokerska-db`. Adres: https://platforma-brokerska.onrender.com
- Narzędzie `list_events` z serwisem `srv-dbmc7cetlv9c73duncgg` działa bez numeru
  przestrzeni roboczej: tak sprawdzaj wdrożenia (deploy_started/ended, build_ended,
  server_failed) zamiast prosić o zrzuty. Pozostałe narzędzia Render wymagają numeru
  przestrzeni (`tea-…`), którego nie znamy. Sieć sesji blokuje domeny Rendera.
- Stan 8.11.2026: wdrożenia były tylko przy utworzeniu (5.11) i po zmianie gałęzi
  w Blueprincie (6.11, commit 1711fb8). Żaden push nie uruchomił wdrożenia.
  Ręczne wdrożenie 8.11 o 13:37 UTC (commit ff2d070) zakończyło się sukcesem.
- W tej samej przestrzeni jest inny serwis, `energia-lublina-crm` — nie dotykać.

## Budowa kodu (modularny monolit, jedna baza)

- `app/main.py` — złożenie aplikacji, start, migracje, obsługa błędów.
- `app/web/` — `ui.py` (szablony, formatowanie, sesja, CSRF), `auth.py` (użytkownik,
  role, uprawnienia BOK, wymuszenie uzupełnienia danych), `forms.py` (walidacja),
  `navigation.py` (zakładki i podsekcje).
- `app/routes/` — strony według modułów: konto, portfel, spolki, zespol, raporty,
  system (publiczna strona `/wersja`).
  Nowy moduł = nowy plik z `router` dodany w `main.py`.
- `app/services.py` — logika biznesowa i widoki przycięte do roli.
- `app/engine.py` — silnik prowizji (czyste funkcje, Decimal).
- `app/models.py`, `app/migrate.py`, `app/demo.py` (stare dane demo z wiersza poleceń).
- `app/exchange/` — wymiana danych bez FastAPI: `standard.py` (arkusze, kolumny, README),
  `importer.py` (odczyt, walidacja, zapis, cofnięcie; podgląd = ten sam zapis w
  wycofanej transakcji), `demo.py` (dane demonstracyjne w standardzie).
  Strony: `app/routes/wymiana.py` (/konto/import, tylko właściciel).
- `migrate.run`: najpierw wszystkie kolumny (`_schema`), potem kroki danych. Odwrotnie
  start wywraca się na bazie sprzed wdrożenia (wykryte na PostgreSQL 8.11.2026).
- Test pilnuje, że `engine`, `services`, `models`, `migrate` nie importują FastAPI
  ani warstwy stron.

Uruchomienie lokalne: `pip install -r requirements-dev.txt`,
`python -m pytest -q`, `uvicorn app.main:app --reload`.
Kwoty formatowane z twardą spacją (U+00A0) — w testach używaj ` `.

## Stan prac

Zrobione: nawigacja z zakładkami pod kciukiem, imię i nazwisko osobno, nazwa firmy
w belce, historia statusów umów, podział kodu na moduły, rola BOK z przełącznikami,
strona /wersja, import z Excela (standard 1.0: zespol, spolki, umowy,
historia_statusow) z podglądem, zatwierdzeniem i cofnięciem paczki, dane demo
(12 spółek, 8 osób, 60 umów) usuwane cofnięciem paczki, reset hasła przez
właściciela (hasło losowe, czytelne, pokazane raz) i wskazówka odzyskiwania
na stronie logowania (`new_password()` w `app/security.py`, wspólna z importem).
Samoobsługowe odzyskiwanie przez e-mail NIE jest zrobione — właścicielka wycofała
tę prośbę 9.11.2026, reset ma zostać ręczny (BOK/właściciel). Zrobione za to:
dostęp BOK do zakładki Zespół (podgląd + reset hasła menedżerów/handlowców,
nigdy właściciela ani innego BOK) włączony tylko gdy `bok_sees_commissions` jest
`True` (`owner_or_bok_commissions` w `app/web/auth.py`); ostatnie logowanie
widoczne na /konto i na stronie osoby; „Wyloguj wszystkie inne urządzenia”
(`User.session_version` + klucz "sv" w sesji, sprawdzane w `current_user`).

Następne (w tej kolejności, po odpowiedziach na pytania niżej):
1. Moduł sprzedażowy: klient i punkt poboru, rezerwacje NIP (karta spółki z częścią
   BOK i szablonami e-maili), szansa i etapy lejka, „Mój dzień”, oferty z cennikiem
   i kalkulatorem prowizji, wycena indywidualna.
2. Analityka portfela, zespołu i raporty (propozycja w docs).
3. Import danych z innych CRM-ów (standard Excela + mapowanie kolumn + lista braków
   z rolą odpowiedzialną) oraz dane demo na pokazy. Eksport klientów odłożony
   (decyzja 8.11.2026). Szczegóły: docs/STANDARD-WYMIANY-DANYCH.md.
4. Treści podpowiedzi sprzedażowych — osobna rozmowa; w systemie tylko miejsca na treści.
   Bez nazwy „Sandler” (zastrzeżona marka).

## Dokumentacja

- `docs/PROPOZYCJA-v1.0-v1.1.md` — plan wersji 1.0 i 1.1, moduł sprzedażowy.
- `docs/WIEDZA-BRANZOWA.md` — potwierdzona wiedza: rezerwacja NIP, oferty, cenniki,
  dokumenty, BOK, karta spółki. Szkic sekcji do skilla „rynek-brokerski-energii-pl”.
- `docs/RAPORT-etap-1.md` — raport z etapu 1.
- `docs/STANDARD-WYMIANY-DANYCH.md` — projekt standardu Excela do importu i eksportu,
  dane przykładowe (wersja robocza 0.1, do akceptacji).

## Otwarte pytania do właścicielki

Odpowiedzi z 7.11.2026 są w `docs/WIEDZA-BRANZOWA.md`. Zostały:

- Punkt poboru w dwóch umowach: czy liczy się nakładanie okresów dostaw (odnowienie
  podpisane wcześniej, ze startem po końcu starej umowy, jest dozwolone)?
- Grupy taryfowe gazu, które mają być na liście (energia: B, C, G).
- „Ofertownik”: czy to narzędzie spółki, czy dokument biura brokerskiego dla klienta
  (wtedy aplikacja ma generować ofertę, np. PDF z logo)?
- Co znaczy „regres” (odrzucenie/cofnięcie umowy przez spółkę z braków?).
- Na jak długo opiekun brokera zwykle przedłuża rezerwację?
- Produkty w cennikach (stała, indeks, mix), zależność od okresu i taryfy.
- Ważność wyceny indywidualnej.
- BOK: domyślne uprawnienia do przepinania klientów; kilka osób z podziałem pracy?
- Migracja: z jakich CRM-ów, zanonimizowany eksport, historia wypłat i korekt.
- Zgoda na płatny magazyn plików w UE (Frankfurt) i okres przechowywania (RODO).

## Stan po rozmowie z 9.11.2026

- **Ceny przy umowie:** potwierdzone, że strona szczegółów umowy wystarcza, nic
  do zmiany. Temat zamknięty.
- **Odzyskiwanie hasła e-mailem:** wycofane, zastąpione resetem ręcznym (wyżej).
- **Filtry menedżera** (dowolny parametr umowy, w tym ryzyko zerwania przy spadku
  cen na giełdzie — „fixing”/RDN) — zgłoszone, NIE zrobione. Blokery do
  rozstrzygnięcia z właścicielką, zanim da się to zaprojektować:
  1. Dziś `Contract` nie ma pola typu cenowego (stała/indeks/mix) — to wciąż
     otwarte pytanie z `docs/WIEDZA-BRANZOWA.md` („Produkty w cennikach”), bez
     niego nie da się filtrować po „umowach na fixing/RDN”.
  2. „Czy opłaca się zerwać umowę, bo giełda spadła” wymaga danych o aktualnej
     cenie rynkowej (TGE: fixing, RDN) — to osobna integracja z zewnętrznym
     źródłem danych giełdowych, nie jest to sam filtr na istniejących polach.
  3. Zwykłe filtry (spółka, handlowiec, status, zakres dat, wolumenu, narzutu,
     medium, nowe przyłącze) da się zrobić od razu na `/umowy`, niezależnie od
     punktów 1–2 — do zaprojektowania i potwierdzenia z właścicielką jako osobny,
     mniejszy krok.
