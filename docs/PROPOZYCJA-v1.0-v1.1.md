# Propozycja przebudowy widoku właściciela: wersje 1.0 i 1.1

Stan: propozycja zatwierdzona do realizacji etapami, listopad 2026.
Zrealizowane: nawigacja (punkt 1), imię i nazwisko osobno (punkt 3), nazwa firmy przy pierwszym uruchomieniu i w górnej belce (część punktu 2).

## Co jest dziś i dlaczego jest nieczytelne

- Menu ma 6 linków w jednym rzędzie. Na telefonie zawija się w kilka wierszy i zajmuje większość ekranu.
- Nad menu jest wiersz „Zalogowano: …”, a pod nim przycisk „Wyloguj”. To kolejne miejsce zajęte, zanim pokaże się treść.
- Na stronach „Spółki” i „Zespół” formularz dodawania jest pod listą. Przy kilku pozycjach trzeba długo przewijać.
- Imię i nazwisko to jedno pole. System przyjmie samo „Anna”.
- Nie ma historii statusów umowy. Gdy umowa przejdzie z „Oferta” do „Umowa podpisana”, ślad po ofercie znika. Bez tego nie da się uczciwie policzyć złożonych ofert ani skuteczności handlowca.
- Nie ma daty rozpoczęcia współpracy, danych abonamentu ani zapisu korekt i zwrotów.

## Wersja 1.0

### 1. Nawigacja

Pięć zakładek:

1. Portfel: podsumowanie, lista umów, nowa umowa. Ekran startowy.
2. Spółki: umowy agencyjne ze spółkami obrotu i ich reguły.
3. Zespół: menedżerowie i handlowcy.
4. Raporty.
5. Konto: abonament, dane właściciela, dane firmy, hasło, wylogowanie.

Telefon:

- Pasek zakładek na dole ekranu, pod kciukiem. Każda zakładka ma ikonę i podpis tekstowy.
- Górna belka ma jedną linię.
- Wiersz „Zalogowano” i przycisk „Wyloguj” trafiają do zakładki Konto.

Komputer: te same zakładki w górnej belce, w jednym rzędzie.

Podsekcje: każda zakładka ma u góry krótkie przełączniki, na przykład w Zespole: lista i dodawanie osoby.

Formularze „Dodaj spółkę”, „Dodaj osobę” i „Nowa umowa” mają osobne strony. Po zapisie wracasz do listy z komunikatem.

Dostępność:

- Nawigacja oznaczona jako „Menu główne”, bieżąca zakładka ogłaszana jako bieżąca strona.
- Przyciski i linki mają co najmniej 44 piksele wysokości.
- Zostaje link „Przejdź do treści”.
- Na telefonie listy osób i umów jako karty, bez szerokich tabel.

### 2. Konto

Abonament, na górze:

- plan: miesięczny albo roczny;
- opłacony do: data;
- pozostało: liczba dni;
- status: aktywny, kończy się (mniej niż 14 dni, z ostrzeżeniem), wygasł.

W wersji 1.0 dane abonamentu wpisuje operator platformy. Potrzebna jest nowa rola „administrator platformy”, wyższa niż właściciel biura.

Dalej: moje dane (imię, nazwisko, e-mail, telefon), dane firmy (nazwa, NIP, adres), bezpieczeństwo (hasło, wylogowanie).

### 3. Imię i nazwisko w dwóch polach

- Dwa osobne pola, oba wymagane, każde co najmniej 2 znaki.
- Sortowanie po nazwisku, wyświetlanie „Imię Nazwisko”.
- Migracja istniejących kont: ostatnie słowo do nazwiska, reszta do imienia. Konto z jednym słowem dostaje oznaczenie „Uzupełnij nazwisko”.

### 4. Spółki

- Lista: nazwa, status, obecne reguły w skrócie, liczba umów, wolumen MWh na rok, prowizja należna, wypłacona i narażona na zwrot.
- Filtry: status, medium. Sortowanie: nazwa, liczba umów, wartość portfela, ryzyko.
- Strona spółki: obecne reguły, historia zmian reguł, lista umów.
- Reguły spółek widzi tylko właściciel.

### 5. Zespół

Podsekcje: Handlowcy i Menedżerowie.

Karta osoby: imię i nazwisko, rola, menedżer, status, data rozpoczęcia współpracy i staż, ostatnia podpisana umowa (data i dni od niej), liczba ofert i umów w okresie, skuteczność oferta do umowy, wolumen, prowizja, jakość portfela (odsetek zerwań i kwota korekt). U menedżera także wyniki zespołu.

Filtry: rola, status, menedżer, okres, „bez umowy od ponad X dni”.

Sortowanie: najwięcej umów, najwięcej ofert, najwyższa skuteczność, najdłuższy i najkrótszy staż, najdłużej bez umowy, najgorszy portfel.

Duże zespoły: 25, 50 albo 100 osób na stronę, wyszukiwanie po nazwisku, ogłoszenie wyniku dla czytnika ekranu.

### 6. Portfel

Na górze: portfel aktywny, portfel zagrożony, zerwane umowy i korekty w okresie, prognoza prowizji na kolejne lata (osobno 2026, 2027, 2028).

Filtry wspólne: okres podpisania, spółka, medium, handlowiec, menedżer, status, ryzyko. Filtry zapisują się w adresie strony.

Portfel zagrożony to umowa spełniająca co najmniej jeden warunek:

1. Utknęła przed startem dostaw: weryfikacja dłużej niż 30 dni albo zmiana sprzedawcy dłużej niż 60 dni. Progi ustawia właściciel.
2. Pierwsza transza wypłacona, a umowa jest w okresie, w którym zerwanie oznacza zwrot (kwota narażona na zwrot).
3. Oznaczona ręcznie jako ryzykowna.

Zerwanie: zapis daty i korekty policzonej silnikiem prowizji, osobno dla brokera, handlowca i menedżera.

Prognoza: prowizja rozłożona w czasie (pierwsza transza na datę wypłaty, reszta na miesiące dostaw). W 1.0 nominalna, oznaczona jako szacunek.

Najgorszy portfel: (kwota korekt + kwota narażona na zwrot) / wygenerowana prowizja, obok odsetek zerwań. Sortowanie od najgorszego, z rozwinięciem do umów.

Historia statusów: każda zmiana statusu zapisywana (data, osoba, status przed i po). Umowy sprzed wdrożenia nie mają historii.

### 7. Raporty

- Rodzaje: portfel; zespół i skuteczność; prowizje do wypłaty; zerwania i korekty; prognoza.
- Zakres: data od i data do, skróty (bieżący miesiąc, poprzedni, kwartał, rok).
- Filtry: spółka, menedżer, handlowiec.
- Wynik na ekranie i w pliku CSV.

### 8. Menedżer i handlowiec

W 1.0 ta sama nawigacja z mniejszą liczbą zakładek. Poufność reguł spółek bez zmian.

## Wersja 1.1

1. Abonament online (np. Przelewy24), automatyczne przedłużenie, faktura.
2. Przypomnienia e-mail 14 i 3 dni przed końcem abonamentu.
3. Prognoza z korektą o historyczny odsetek zerwań, obok wariantu nominalnego.
4. Ręczne flagi ryzyka z notatką i historią.
5. Wykresy z tabelą tekstową dla czytnika ekranu.
6. Raporty PDF i XLSX, raport miesięczny wysyłany e-mailem.
7. Zapisane widoki filtrów.
8. Pełne widoki menedżera i handlowca.
9. Import umów z pliku CSV.

## Otwarte decyzje

1. Oferta jako etap umowy czy osobny obiekt (kilka ofert dla jednego klienta).
2. Progi ryzyka: 30 dni weryfikacji, 60 dni zmiany sprzedawcy.
3. Abonament w 1.0 wpisywany ręcznie przez operatora.
4. Kolejność: nawigacja, imię i nazwisko, historia statusów.
