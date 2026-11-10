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

Zawsze kończ tę instrukcję i każde "sprawdź, czy wdrożenie się udało" DWOMA linkami,
każdy jako osobna linia na samym końcu wiadomości (prosiła o to 8.11.2026 i 10.11.2026:
ciągle gubi linki wklejone gdzie indziej, a czyta koniec wiadomości; link do Rendera
w środku listy kroków jej nie wystarcza):
Panel wdrożenia (Render): https://dashboard.render.com/web/srv-dbmc7cetlv9c73duncgg
Aplikacja: https://platforma-brokerska.onrender.com

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
(12 spółek, 9 osób, 100 umów) usuwane cofnięciem paczki, reset hasła przez
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
- `docs/PROJEKT-DZIEN-HANDLOWCA.md` — projekt ekranu „Mój dzień”, lejka, kalendarza i
  podpowiedzi (10.11.2026, do akceptacji). Następny temat: uporządkowanie BOK.
- `docs/CHECKLISTA-PO-ROLACH.md` — co wdrożone a co nie, po każdej roli (właściciel,
  menedżer, handlowiec, BOK), do aktualizacji po każdym większym kroku.

## Otwarte pytania do właścicielki

Odpowiedzi z 7.11.2026 są w `docs/WIEDZA-BRANZOWA.md`. Zostały:

- Punkt poboru w dwóch umowach: czy liczy się nakładanie okresów dostaw (odnowienie
  podpisane wcześniej, ze startem po końcu starej umowy, jest dozwolone)?
- Grupy taryfowe gazu, które mają być na liście (energia: B, C, G).
- „Ofertownik”: czy to narzędzie spółki, czy dokument biura brokerskiego dla klienta
  (wtedy aplikacja ma generować ofertę, np. PDF z logo)?
- Co znaczy „regres” (odrzucenie/cofnięcie umowy przez spółkę z braków?).
- Na jak długo opiekun brokera zwykle przedłuża rezerwację?
- ~~Produkty w cennikach~~ — odpowiedziane 9.11.2026: SPOT, FIX, TRANZA
  (`docs/WIEDZA-BRANZOWA.md`, sekcja „Produkty cenowe i ryzyko zerwania”).
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
  1. ODPOWIEDZIANE 9.11.2026: trzy produkty — SPOT, FIX, TRANZA, z kolorami
     (FIX zielony, SPOT niebieski, TRANZA żółty) i zasadą UC84 o karze umownej
     (patrz `docs/WIEDZA-BRANZOWA.md`). `Contract` wciąż nie ma pola typu
     cenowego — do dodania razem z filtrami, propozycja czeka na jej akceptację.
  2. „Czy opłaca się zerwać umowę, bo giełda spadła” wymaga danych o aktualnej
     cenie rynkowej (TGE: fixing, RDN) — to osobna integracja z zewnętrznym
     źródłem danych giełdowych, nie jest to sam filtr na istniejących polach.
  3. ZROBIONE 9.11.2026: `Contract.pricing_product` (spot/fix/tranza,
     `app/models.py`, domyślnie fix — silnik liczy stały narzut, strukturalnie
     odpowiada FIX), wybór przy zapisie umowy, plakietka z kolorem (WCAG AA
     sprawdzony, `.produkt-*` w `app/static/style.css`) wszędzie, gdzie widać
     umowę. Filtry na `/umowy` (GET, w adresie, więc link do widoku można
     zapisać): produkt (kilka naraz), spółka, medium, handlowiec (ukryty dla
     handlowca — zawsze tylko on), status, zakres dat podpisania, zakres
     wolumenu i narzutu, nowe przyłącze, sortowanie — `ContractFilters` i
     `apply_contract_filters` w `app/services.py`, parsowanie bez wyjątków
     (literówka w adresie = pusty filtr, nie błąd) w `app/routes/portfel.py`.
     Punkty 1–2 (prawdziwa ocena opłacalności zerwania wobec giełdy) wciąż
     NIE zrobione — osobna integracja z danymi rynkowymi.

## Czysty start 10.11.2026 (wykonany, kod usunięty)

Jednorazowe czyszczenie bazy po zablokowaniu konta Boss01 zadziałało (właścicielka
założyła konto od nowa i wczytała demo). Kod `_one_time_clean_start` usunięty z
`app/migrate.py`; tabela `system_flags` zostaje (pusta lub ze starym znacznikiem). Uwaga na przyszłość: właściciel nie ma dziś
odzyskiwania dostępu, gdy zapomni hasło (BOK nie resetuje właściciela, e-maila brak) —
propozycja: jednorazowy kod odzyskiwania pokazywany przy tworzeniu konta; nie zrobione.

Dane demo przebudowane 10.11.2026 (`app/exchange/demo.py`): 100 umów, marże i
proporcje wg `docs/WIEDZA-BRANZOWA.md`, menedżer Michał Lex, BOK: Jessica Kowal (szefowa,
nazwisko zgadnięte, właścicielka może je zmienić w Zespół) i Joanna Dąbrowska. Platforma
nie rozróżnia szefa BOK od zwykłej osoby BOK.

## Zgłoszenia właścicielki z 9.11.2026 (po teście demo)

ZROBIONE 9.11.2026 (commit po 979292b): nazewnictwo („marża”, „całkowita masa marży”,
„Przychód spółki” zamiast „Marża właściciela”; techniczne nazwy pól i kolumn importu
bez zmian), sprzedaż bieżącego miesiąca vs target na pulpicie (`SalesTarget`,
`month_sales` w `app/services.py`; liczą się umowy podpisane w miesiącu, bez
zerwanych i bez Lead/Kontakt/Oferta), target ustawia właściciel albo menedżer
swoim ludziom, zakładka Zespół dla menedżera (tylko jego ludzie, bez edycji stawek
i bez resetu haseł, `team_viewer` w `app/web/auth.py`), polityka biura
„Handlowcy widzą prognozę transzy B” (`Company.traders_see_tranche_b`, domyślnie
tak; prognoza B zawsze z zastrzeżeniem, schowana w `<details>`).

NIE zrobione — następne wdrożenie: poziomy handlowców (junior/senior/pro,
definiuje właściciel, przypisuje menedżer) oraz harmonogram rozliczeń w karcie
spółki (warianty transzy B 1–3, terminy rozliczenia i wypłaty) z podsumowaniem
portfela wg okresów i potwierdzaniem wpływu od spółki. Wiedza w
`docs/WIEDZA-BRANZOWA.md` („Wypłata prowizji w czasie”).

Pierwotne zgłoszenia:

1. **Terminologia:** w branży brokerskiej mówi się „marża”, nie „narzut”. Zamienić
   wszędzie („masa narzutu” → „całkowita masa marży”, „narzut zł/MWh” → „marża
   zł/MWh”, także w imporcie). Konflikt nazw: dzisiejsza „Marża właściciela” —
   nowa nazwa do ustalenia z właścicielką.
2. **Menedżer nie ma zakładki Zespół** — potwierdzone, nie ma też przełącznika
   (zakładka jest tylko dla właściciela i BOK z uprawnieniem). Menedżer ma zarządzać
   zespołem: zaprojektować widok zespołu menedżera (tylko jego ludzie).
3. **Harmonogram rozliczeń prowizji** w karcie spółki (nie tylko wysokość i transza,
   ale terminy: np. umowy z miesiąca M rozliczane przez spółkę do 25. dnia M+1,
   wypłata 10. dnia M+2; różnie w spółkach) i podsumowanie w portfelu według
   okresów rozliczeniowych: „Transza I z okresu [miesiąc]: N umów, kwota” oraz
   „Transza B z wcześniejszych umów: N umów, kwota”. Zrozumienie i pytania
   przedstawione właścicielce, kod NIE zaczęty.

## Pulpit sprzedażowy i widoki na telefon (9.11.2026, wieczór)

ZROBIONE: lista umów z paskiem jak w aplikacjach rezerwacyjnych (Filtry (N) i Sortowanie w
`<details>`, jeden „Wyczyść filtry”), licznik wyników na żywo (`/umowy/liczba`, JSON,
`app/static/filtry.js` — postępowe ulepszenie, bez JS działa zwykły GET). Pulpit: najpierw
bieżący miesiąc vs target (pasek postępu, „brakuje do targetu”), potem „Oferty złożone”
(`offers_overview`: umowy w statusie „Oferta”, pogrupowane po handlowcach, prognoza masy
marży; właściciel widzi przychód spółki, menedżer swój override, handlowiec swoją prowizję),
potem zwijane „Statystyki sprzedaży” z zakresem miesięcy (`od_mies`, `do_mies`,
`monthly_stats`, maks. 36 mies.) i portfelem. Właściciel ma portfel zawsze rozwinięty.
Lead/Kontakt/Oferta NIE wchodzą już do sum portfela (`summary_for`, pole `offers`).
Zwinięte sekcje drugorzędne: zmiana statusu, historia, tabela transz (umowa), stawki,
target, ustawienia (osoba), reguły i historia (spółka), polityka i uprawnienia BOK (konto).
Demo: 100 umów + 14 ofert (w tym „Wózki Widłowe Michalski”).
Oferta to dziś umowa w statusie „Oferta” — rozwiązanie przejściowe do modułu sprzedażowego.

## Demo z rytmem sprzedaży i targetami (10.11.2026)

- Standard Excela 1.1: opcjonalny arkusz `targety` (email, miesiac RRRR-MM, kwota_zl).
- Demo: daty umów wg `RHYTHM` w `app/exchange/demo.py` (12 miesięcy): Anna, Katarzyna
  regularne; Piotr Nowicki zrywami (2 miesiące sprzedaje, 2 nie); Michał Wójcik zrywami,
  od 2 miesięcy przestój; Agnieszka od 9 miesięcy; Paweł słabnący. Bieżący miesiąc ma
  tylko świeże (małe/średnie) umowy, żeby % targetu był realny w trakcie miesiąca.
- Targety demo wg udziału: 35% junior 150 000 zł, 40% senior 200 000 zł, 45%+ pro
  250 000 zł (menedżer 45% też 250 000 — założenie, do potwierdzenia), na 12 miesięcy.
  „Ci, którzy mają juniora: 200 000” z dyktowanej wiadomości zinterpretowane jako senior.
- Zespół: ranking miesiąca (wykonanie targetu), „Rytm: umowy w N z ostatnich 6 miesięcy”
  (≤3 = „nieregularnie”). Strona osoby: zwijane statystyki po miesiącach z targetem
  i % w każdym miesiącu, „brak umów” wyróżnione. Pulpit: oferty czekające 3 dni i dłużej
  wyróżnione („Czeka N dni”).

## Dzień handlowca, wdrożenie 1 (10.11.2026)

Decyzje właścicielki: alarm to lejek, nie norma tygodniowa (mniej niż 3 klientów w pracy:
kontakt, dane, oferta = pilny sygnał „dodaj nowych”); menedżer pilnuje wypełnienia lejka
na każdym etapie; handlowiec sam wskazuje spółki do sprawdzenia NIP, BOK sprawdza tylko je;
duplikat NIP: tylko „NIP obsługuje już Twój kolega z biura. Zapytaj BOK o szczegóły.”;
oferta ważna do 7 dni, telefon po 3 dniach bez odpowiedzi.

Kod: `app/pipeline.py` (logika, bez FastAPI), `app/routes/klienci.py` (/dzien, /klienci,
/klienci/{id}, /klienci/{id}/kalkulator, /bok, /konto/listy), modele Client, NipCheck,
ClientOffer, ClientEvent, Checklist (nowe tabele, bez nowych kolumn w starych). Etapy:
lead, kontakt, dane, oferta, wygrana, przegrana (z powodem). Zakładki: handlowiec i menedżer
zaczynają od „Mój dzień”, BOK od „Zlecenia” (/bok), właściciel od pulpitu; Raporty są
podsekcją Portfela. Umowa z oferty: /umowy/nowa?klient=&oferta= wypełnia formularz, po
zapisie klient przechodzi na „Umowa podpisana”. Pulpit „Oferty złożone” czyta oferty
z kart klientów (i dawne umowy w statusie Oferta). Standard Excela 1.2: arkusze klienci,
sprawdzenia_nip, oferty. Demo: 100 umów, 41 klientów (14 z ofertą), 26 sprawdzeń
(10 czeka na BOK); Michał Wójcik i Paweł Kamiński mają alarm małego lejka.
Sprawdzone na PostgreSQL 16: baza z poprzedniej wersji, cofnięcie starego demo, nowe demo.

Nie zrobione (następne): przedłużanie rezerwacji z dowodami, karta spółki dla BOK
(szablony e-maili), wersje cenników, punkty poboru, kalendarz w telefonie (ICS),
podpowiedzi rozmów, nazwa firmy z wykazu VAT po NIP, uporządkowanie reszty BOK.

## Redakcja językowa interfejsu (10.11.2026)

Przegląd wszystkich tekstów, zatwierdzony przez właścicielkę. Zasady na przyszłość: „klienci
w toku” (nie „w pracy”), „spółka, w której NIP jest wolny” (nie „z wolnym NIP-em”), „zasady
biura” (nie „polityka”), „zabezpieczona” (nie „zahedowana”), „platforma” tylko w nazwie,
bez „system”/„aplikacja” w zdaniach, imiona w komunikatach po dwukropku (nie da się ich
odmieniać). Jej słownictwo zostaje: lead, override, target, scoring, wolumen, ofertować,
masa marży, przychód spółki. Test `test_teksty_interfejsu_bez_kalek_i_starych_sformulowan`
pilnuje, żeby stare zwroty nie wróciły. W Excelu i adresach filtrów zostaje „narzut”
(zgodność wsteczna).
