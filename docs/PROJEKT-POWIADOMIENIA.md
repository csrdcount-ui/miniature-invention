# Projekt: komunikacja i powiadomienia w trójkącie handlowiec, BOK, menedżer (13.11.2026, do akceptacji)

Cel: każda informacja potrzebna do sprzedaży i rozliczeń trafia do właściwej osoby, nikt nie musi
jej szukać, a po fakcie da się sprawdzić, kto co dostał i kiedy. Właściciel widzi całość.

Stan dziś (13.11.2026): odpowiedzi BOK są w „Mój dzień” handlowca (sekcja „Od BOK”), BOK ma
kolejki (NIP-y do sprawdzenia, faktury do wprowadzenia i do zarchiwizowania), karta klienta ma oś
zdarzeń. Brakuje: znacznika z liczbą nowych spraw, rozmowy między osobami w sprawie klienta,
terminów reakcji i eskalacji do menedżera, dziennika powiadomień dla właściciela.

Wersja do testów: platforma bez powiadomień, wdrożona 13.11.2026 (commit ab45772). Ten dokument
uzupełniamy po uwagach testerów (sekcja na końcu).

## Stan wdrożenia (14.11.2026)

**N1 jest w kodzie na main** (powiadomienia i dziennik firmy). Właścicielka zgodziła się 14.11.2026 ruszyć
z budową; N1 nie wymagał odpowiedzi na pytania, przyjęte założenia są niżej i łatwo je zmienić.

Co działa:
- tabela `notifications` (nowa, bez zmian w starych), logika `app/powiadomienia.py`, strony
  `app/routes/powiadomienia.py`: `/powiadomienia`, `/powiadomienia/{id}` (otwiera sprawę i zapisuje odczyt),
  „Oznacz wszystkie jako przeczytane”, `/konto/dziennik` (tylko właściciel, filtry w adresie);
- znacznik w belce jako tekst: „Powiadomienia, 3 nowe”; jedno zapytanie po indeksie przy każdej stronie;
- zdarzenia: NIP do BOK (wszyscy z BOK), wynik NIP (opiekun klienta i zlecający), faktury do BOK (wszyscy z BOK),
  faktury gotowe albo odrzucone (opiekun i zlecający), zapisana umowa (menedżer handlowca, handlowiec gdy zapisał
  ktoś inny, wszyscy z BOK: „umowa do przygotowania”), zmiana statusu umowy (handlowiec i menedżer z umowy),
  zerwanie: pilne, także właściciel;
- autor zdarzenia nie dostaje powiadomienia o własnym ruchu; treść bez kwot, udziałów i prowizji (test);
- dziennik nieusuwalny: brak tras do edycji i usuwania; numery osób, klientów i umów bez kluczy obcych, imiona
  zapisane w chwili powstania; cofnięcie demo odpina wpisy od usuwanych osób, ale ich nie kasuje;
- import z Excela i dane demo NIE tworzą powiadomień (tylko działania ludzi w platformie);
- czasy pokazywane w czasie polskim, zapisywane w UTC.

Przyjęte założenia (do zmiany po odpowiedziach na pytania):
- pytanie 3: szefa BOK nie ma, więc powiadomienia dla BOK dostaje każda osoba z BOK;
- pytanie 5: okres przechowywania nieustalony, na razie nic nie jest usuwane;
- pytanie 6: w N1 wszystko przychodzi od razu; zbiorcze podsumowania menedżera dopiero w N3.

Nie zrobione z N1: „Faktury do zarchiwizowania” jako powiadomienie (BOK ma tę kolejkę na ekranie Zlecenia),
przypomnienia zależne od czasu (oferta: telefon po 3 dniach, wygasa jutro; rezerwacja wygasa) — te wymagają
zegara i przechodzą do N3 razem z eskalacjami. Kroku samouczka o powiadomieniach jeszcze nie ma.

## Zasady

1. **Trzy kanały, każdy do czegoś innego:**
   - **powiadomienie**: platforma sama mówi „coś się wydarzyło” (np. BOK potwierdził rezerwację);
   - **wiadomość w sprawie**: człowiek pisze do człowieka przy konkretnym kliencie lub umowie
     (np. BOK: „brakuje drugiej strony faktury”), zawsze w kontekście, nigdy „luzem”;
   - **prośba z terminem**: ktoś czegoś potrzebuje do daty; platforma pilnuje terminu
     i eskaluje (np. BOK prosi handlowca o pełnomocnictwo do piątku).
2. **Dziennik nieusuwalny.** Wpisów nikt nie edytuje ani nie usuwa, także właściciel. Każdy ma
   trzy czasy: powstał, adresat zobaczył (otworzył listę), adresat przeczytał (otworzył sprawę).
3. **Każdy widzi swoje; menedżer swój zespół; właściciel wszystko.** Sprawdzane na serwerze.
4. **Bez danych poufnych w treści** (udział brokera, przychód spółki): krótki tekst i link;
   szczegóły po wejściu, według uprawnień.
5. **Wewnątrz platformy** (baza we Frankfurcie). E-mail i powiadomienie w telefonie: osobny etap.
6. **Dostępność:** znacznik w belce jako tekst dla czytnika („Powiadomienia, 3 nowe”), nie sam
   czerwony kolor; lista z nagłówkami; każde powiadomienie jednym zdaniem.

## Mapa procesu: kto działa, kto musi wiedzieć

Dla każdego kroku: kto wykonuje, kto dostaje powiadomienie, termin i eskalacja.
Terminy w nawiasach to propozycje do potwierdzenia.

### 1. Nowy lead i pierwszy kontakt
- Działa: handlowiec (szybki lead, rozmowa, następny krok).
- Powiadomienia: brak (praca własna handlowca).
- Menedżer: zbiorczo raz dziennie „alarm małego lejka” u osoby z mniej niż 3 klientami w toku
  (zasada z 10.11.2026), zamiast powiadomień o każdym leadzie.
- Eskalacja: klient bez następnego kroku dłużej niż (2 dni robocze) → menedżer.

### 2. Dane klienta i faktury
- Działa: handlowiec (zdjęcia, „Odeślij do BOK”) albo sam wpisuje dane.
- Powiadomienia:
  - BOK: „Nowe faktury do wprowadzenia: [klient]”;
  - handlowiec: „Dane z faktur gotowe: [klient]” albo „BOK nie odczytał faktur, wyślij nowe”;
  - BOK, gdy zadanie zamknięte, a pliki niepobrane: „Faktury do zarchiwizowania: [klient]”.
- Termin BOK: (tego samego dnia roboczego; w godzinach spotkań — do 1 godziny).
- Eskalacja: zadanie czeka dłużej niż termin → menedżer handlowca i szef BOK.

### 3. NIP do BOK: rezerwacja i scoring
- Działa: handlowiec wysyła NIP i spółki; BOK sprawdza.
- Powiadomienia:
  - BOK: „Nowe NIP-y do sprawdzenia: [klient], [n] spółek”;
  - handlowiec: „[spółka]: zarezerwowany do [data]” / „zajęty” / „negatywny scoring”.
- Termin BOK: (do końca następnego dnia roboczego) — pytanie otwarte z 13.11.2026.
- Eskalacja: brak odpowiedzi po terminie → menedżer i szef BOK.
- Rezerwacja wygasa: za 7 dni → handlowiec; za 3 dni bez przedłużenia → menedżer.

### 4. Oferta
- Działa: handlowiec (kalkulator, zapis oferty).
- Powiadomienia:
  - handlowiec: „Zadzwoń w sprawie oferty: [klient]” po 3 dniach bez decyzji;
  - handlowiec: „Oferta wygasa jutro: [klient]”;
  - handlowiec: „Nowy cennik [spółka]: oferta z poprzedniego ważna do końca dnia”;
  - menedżer: zbiorczo „Oferty zespołu bez odpowiedzi od 5 dni: [n]”.
- Wycena indywidualna (powyżej progu spółki): prośba handlowca do BOK z terminem.

### 5. Decyzja klienta i umowa do podpisu
- Działa: handlowiec (klient przyjął albo odrzucił, sposób podpisu).
- Powiadomienia:
  - BOK: „Umowa do przygotowania: [klient], [spółka], podpis: Autenti/SMS/papier”;
  - menedżer: „Podpisana umowa: [handlowiec], [klient]” (dobra wiadomość też jest informacją);
  - przegrana z powodem → menedżer zbiorczo raz w tygodniu.
- BOK ↔ handlowiec: wiadomości i prośby o braki (dokumenty, pełnomocnictwo, numery PPE).

### 6. Po podpisaniu: spółka, OSD, start dostaw
- Działa: BOK (wysyłka do spółki, statusy: weryfikacja, zmiana sprzedawcy, start dostaw).
- Powiadomienia:
  - handlowiec i menedżer: każda zmiana statusu jego umowy;
  - handlowiec i menedżer: „Spółka odrzuciła umowę / braki: [powód]” (pilne);
  - właściciel: zbiorczo umowy z problemem.

### 7. Rozliczenia i prowizje
- Działa: właściciel albo BOK z uprawnieniem (wpływ od spółki, wypłata transzy).
- Powiadomienia:
  - handlowiec i menedżer: „Transza A wypłacona: [klient], [kwota]” — tylko ich część;
  - handlowiec i menedżer: „Korekta (zerwanie): [klient], [kwota do zwrotu]”.
- Uwaga: harmonogram rozliczeń i rejestr wpływów jeszcze nie istnieją (osobny moduł); do tego czasu
  ten krok nie ma powiadomień.

### 8. Zespół (menedżer)
- Menedżer dostaje zbiorczo, nie pojedynczo:
  - raz dziennie rano: alarm małego lejka, oferty bez odpowiedzi, eskalacje z kroków 1–6;
  - raz w tygodniu: udział w masie marży biura (słabiej drugi miesiąc z rzędu, trwała tendencja),
    powody przegranych.
- Menedżer może napisać wiadomość do swojego handlowca w sprawie klienta i dać prośbę z terminem.

### 9. Właściciel
- Panel „Dziennik firmy”: wszystkie powiadomienia, wiadomości i prośby, z filtrami (osoba, rodzaj,
  klient, data), z czasami powstania, zobaczenia i przeczytania.
- Czasy reakcji: średni czas odpowiedzi BOK na NIP i faktury, czas reakcji handlowców na prośby
  BOK; prośby po terminie.
- Pojedyncze powiadomienia właściciela: tylko eskalacje i sprawy pilne (np. odrzucona umowa),
  reszta w dzienniku, żeby nie zalewać.

## Model danych (propozycja)

- `Notification`: adresat, rodzaj, treść (jedno zdanie), link, klient/umowa/zadanie, utworzone,
  zobaczone, przeczytane. Tworzone wyłącznie przez platformę.
- `CaseMessage`: autor, sprawa (klient albo umowa), adresaci, treść, utworzone; odczyt każdego
  adresata zapisany osobno. Pojawia się na osi zdarzeń karty i jako powiadomienie.
- `Request`: autor, odpowiedzialny, sprawa, treść, termin, status (otwarta, zrobiona, odrzucona
  z powodem), zamknięta przez i kiedy. Po terminie: eskalacja do przełożonego.
- Wszystkie tabele nowe (bez zmian w starych), tylko dopisywanie; brak przycisku „usuń”.
- Okres przechowywania: do decyzji (propozycja: 2 lata), usuwanie starszych automatycznie.

## Etapy wdrożenia

- **N1. Powiadomienia i dziennik** (ok. 1 dzień): znacznik z liczbą w belce, strona powiadomień,
  powiadomienia z kroków 2, 3, 4, 5 i 6, dziennik firmy dla właściciela. Bez e-maili.
- **N2. Wiadomości w sprawie i prośby z terminem** (ok. 1–2 dni): BOK ↔ handlowiec ↔ menedżer
  przy kliencie i umowie, potwierdzenia przeczytania.
- **N3. Terminy, eskalacje, zbiorcze podsumowania menedżera, czasy reakcji** (ok. 1 dzień).
  Wymaga ustalenia terminów (pytania niżej).
- **N4. Poza platformą**: e-mail z podsumowaniem i powiadomienia w telefonie (aplikacja na
  ekranie głównym). Wymaga skrzynki nadawczej albo konfiguracji powiadomień; osobna decyzja.

## Testy

- Każde zdarzenie z mapy tworzy powiadomienie dla właściwych osób i tylko dla nich.
- Poufność: treść powiadomień bez udziału brokera i przychodu spółki; handlowiec nie widzi
  powiadomień innego zespołu; menedżer tylko swojego.
- Dziennik: brak możliwości edycji i usunięcia; czasy zobaczenia i przeczytania zapisane.
- Eskalacje: zegar testowy, termin przekroczony → powiadomienie przełożonego.
- Dostępność: znacznik czytany jako tekst, lista z nagłówkami, bez JavaScriptu.
- Obciążenie: liczenie znacznika przy każdej stronie nie może spowolnić serwera (jedno szybkie
  zapytanie; test jak 13.11.2026 dla 20 osób).

## Pytania do właścicielki

1. Terminy reakcji BOK: NIP-y (do końca następnego dnia roboczego?), faktury w trakcie spotkań
   (1 godzina?), umowa do przygotowania (ile?).
2. Eskalacje: do menedżera handlowca, do szefa BOK, czy do obu? Kiedy także do właściciela?
3. Szef BOK: dziś platforma nie odróżnia szefa BOK od pracownika BOK. Czy dodać tę rolę?
4. Czy menedżer czyta wiadomości między swoim handlowcem a BOK, czy tylko widzi, że były?
5. Okres przechowywania dziennika (RODO): 2 lata?
6. Które powiadomienia zbiorczo (raz dziennie), a które od razu?

## Uwagi po testach z 13.11.2026

(Do uzupełnienia po rozmowie z właścicielem, menedżerem i dwoma handlowcami.)
