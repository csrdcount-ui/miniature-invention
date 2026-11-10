# Checklista po rolach: co jest wdrożone a co czeka

Stan na 9.11.2026 (wieczór). Nowości po `979292b`: marża zamiast narzutu, „Przychód spółki”, sprzedaż miesiąca vs target, zakładka Zespół menedżera, polityka transzy B. Pierwsza kolumna zasad: wszystko tu opisane
jest w kodzie na `main`. „Wdrożone” znaczy: na serwerze po ostatnim ręcznym
„Manual Deploy” — sprawdź numer commitu na https://platforma-brokerska.onrender.com/wersja.

Role w aplikacji dziś: **Właściciel**, **Menedżer**, **Handlowiec**, **BOK**.
Zaloguj się do każdej przez dane demonstracyjne (zakładka Konto → Import danych →
„Sprawdź dane demonstracyjne” → zatwierdź → hasła pokażą się raz na ekranie wyniku).

## Nowość 9.11.2026 (wieczór) — dla wszystkich ról

- Lista umów: przyciski „Filtry” i „Sortowanie” zwinięte, licznik „Pasuje: N umów” zmienia
  się przy zaznaczaniu, przycisk „Pokaż N umów” zwija panel i zostawia same wyniki.
- Pulpit: bieżący miesiąc i target na górze, „Oferty złożone” z podziałem na handlowców,
  „Statystyki sprzedaży” zwinięte, z wyborem zakresu miesięcy.
- Dane demonstracyjne: 100 umów + 14 ofert (np. „Wózki Widłowe Michalski”). Uwaga: demo
  nie ustawia targetów — ustaw je w Zespół → osoba → „Target masy marży”.

## Nowość: cenniki i kalkulator (do sprawdzenia po wdrożeniu)

Najpierw: Konto → Import danych → cofnij starą paczkę demo → wczytaj nową (dochodzą cenniki).
- BOK (Jessica Kowal): Zlecenia → Cenniki. ENGIE nie ma obowiązującego cennika (alarm),
  Axpo zmieniło cennik dziś. „Nowy cennik” otwiera formularz z poprzednimi cenami,
  po zapisaniu widać zmiany, potem „Zatwierdź”.
- Handlowiec (Anna Kowalczyk): karta klienta → Kalkulator. Wybierz grupę C12a, wpisz ceny
  dla klienta w obu strefach i udział stref; zaznacz „Pokaż też spółki…”, żeby zobaczyć
  wszystkie. „Zapisz ofertę w tej spółce” przepisuje dane do oferty.
- Właściciel: Spółki → Cenniki (to samo, co BOK).

## Nowość: dzień handlowca (do sprawdzenia po wdrożeniu)

Najpierw: Konto → Import danych → cofnij starą paczkę demo → wczytaj nową.
- Handlowiec (Paweł Kamiński): po zalogowaniu „Mój dzień”, alarm „Za mało klientów
  w pracy”, oferty do telefonu i wygasłe.
- Handlowiec (Anna Kowalczyk): zakładka Klienci, karta klienta z ofertą, „Wyślij NIP
  do BOK” z wyborem spółek, kalkulator, „Klient podpisał: zapisz umowę”.
- Nowy klient z NIP-em, który ma już kolega: komunikat bez szczegółów.
- BOK (Jessica Kowal): zakładka „Zlecenia”, 10 sprawdzeń, wpisanie wyniku.
- Menedżer (Michał Lex): „Mój dzień” i „Lejek zespołu” z alarmami.
- Właściciel: Konto → Listy wymagań (do oferty, do umowy).

## Nowość 10.11.2026 — do sprawdzenia po wdrożeniu

- Dane demo mają targety (junior 150 000, senior 200 000, pro 250 000 zł) — paski na
  pulpicie od razu. Trzeba cofnąć starą paczkę demo i wczytać nową.
- Zespół: ranking miesiąca i „Rytm: umowy w N z ostatnich 6 miesięcy”.
- Strona osoby: „Statystyki sprzedaży” po miesiącach. Porównaj Annę Kowalczyk
  (regularna), Piotra Nowickiego (zrywami) i Michała Wójcika (przestój od 2 miesięcy).
- Pulpit: oferty czekające ponad 14 dni są wyróżnione.

## Właściciel

### Gotowe do testowania
- Pierwsze uruchomienie: nazwa firmy, imię, nazwisko (`/start`).
- Nawigacja: zakładki Portfel, Spółki, Zespół, Raporty, Konto (na telefonie na dole
  ekranu pod kciukiem).
- Spółki obrotu: dodawanie, reguły prowizji z datą obowiązywania, historia reguł,
  włączanie/wyłączanie spółki (`/spolki`).
- Zespół: dodawanie menedżerów/handlowców/BOK, stawki (udział w narzucie, override
  menedżera), historia stawek, zmiana przełożonego, aktywacja/dezaktywacja,
  **reset hasła** (losowe, czytelne, pokazane raz), **ostatnie logowanie** każdej
  osoby (`/zespol`).
- Umowy: zapis nowej umowy z wyborem **produktu cenowego** (SPOT/FIX/Transza),
  zmiana statusu z datą zdarzenia i notatką, pełna **historia statusów**, pełny
  podgląd prowizji (udział brokera, marża własna — nigdy nie widzi tego nikt inny)
  (`/umowy`).
- **Filtry na liście umów**: produkt, spółka, medium, handlowiec, status, zakres
  dat podpisania, zakres wolumenu i narzutu, nowe przyłącze, sortowanie — w adresie
  strony, więc widok da się zapisać jako link.
- Konto: dane firmy i własne, zmiana hasła, **uprawnienia BOK** (cztery
  przełączniki, z historią zmian), **„Wyloguj wszystkie inne urządzenia”**.
- **Import danych z Excela**: szablon do pobrania, podgląd z raportem błędów
  wiersz po wierszu, zatwierdzenie, **cofnięcie całej paczki**.
- **Dane demonstracyjne**: 12 spółek z prawdziwymi nazwami rynkowymi i fikcyjnymi
  warunkami, 6 handlowców, 1 menedżer (Michał Lex), 2 osoby BOK (Jessica Kowal, Joanna Dąbrowska), 100 umów ze scenariuszami (zerwania
  z powodem, umowy utknięte w weryfikacji, nowe przyłącza, świeże i zakończone).
  Jeden przycisk usuwa je wszystkie naraz, bez ruszania prawdziwych danych.
- Strona `/wersja`: numer wdrożonego commitu, bez logowania.

### Czego brakuje — do Twojej uwagi, zanim zaplanujemy dalej
- **Domyślna gałąź w GitHubie** nadal stara (opcjonalne, aplikacja działa bez tego
  — zasada 7, nie ponaglam).
- **Raporty**: sama zakładka istnieje, ale pokazuje tylko zapowiedź — żadnego
  prawdziwego raportu jeszcze nie ma.
- **Abonament** na stronie Konto: zapowiedź, bez treści.
- **Odzyskiwanie hasła e-mailem**: wycofane na Twoją prośbę, zostaje reset ręczny.

## Menedżer

### Gotowe do testowania
- Pulpit i lista umów: widzi umowy własne i całego zespołu, z plakietką produktu,
  filtrami i sortowaniem jak właściciel — bez warunków właściciela u spółek.
- Własna sprzedaż: zapisuje umowy, zmienia ich status, widzi swoją prowizję.
- Override od umów zespołu, widoczny na umowach podwładnych.
- Konto: swoje dane, zmiana hasła, ostatnie logowanie, wylogowanie innych urządzeń.

### Jeszcze nie przetestowane przez Ciebie / otwarte
- To jest **pierwsze realne wejście menedżera, o które prosiłaś** — potwierdź, czy
  filtry i widoczność zespołu działają tak, jak oczekujesz.
- Nie ma jeszcze rankingu/analityki zespołu (kto ma najgorszy portfel, kto najwięcej
  sprzedał) — to pozycja 2 z planu („Analityka portfela, zespołu i raporty”).
- Nie ma jeszcze oceny opłacalności zerwania umowy SPOT względem bieżącej ceny na
  giełdzie (wymaga osobnej integracji z danymi rynkowymi, patrz niżej).

## Handlowiec

### Gotowe do testowania
- Widzi i zapisuje tylko własne umowy, z własną prowizją i produktem cenowym.
- Nie widzi: warunków właściciela u spółek, cudzych umów, stawek innych osób.
- Konto: swoje dane, zmiana hasła, ostatnie logowanie, wylogowanie innych urządzeń.

### Jeszcze nie zrobione
- **Cały moduł sprzedażowy** (pozycja 1 z planu): klient i punkt poboru, rezerwacja
  NIP-u, lejek sprzedaży, ekran „Mój dzień”, oferty z kalkulatorem. Dziś handlowiec
  ma tylko rejestr umów, nie narzędzie do prowadzenia sprzedaży — to świadomie
  odłożone do czasu ustalenia szczegółów (karta spółki, szablony e-maili BOK).
- Podpowiedzi sprzedażowe (etapy rozmowy, obiekcje) — pozycja 4, osobna rozmowa.

## BOK (biuro obsługi)

### Gotowe do testowania
- **Dostęp uzależniony od Twojego przełącznika** „Widzi prowizje handlowców i
  override menedżerów” w Koncie:
  - wyłączony (domyślnie): BOK w ogóle nie widzi zakładki Zespół, nie resetuje
    żadnych haseł — sprawdź to jako pierwszy test;
  - włączony: BOK widzi tylko menedżerów i handlowców (nigdy Ciebie ani innego
    BOK), może zresetować im hasło, ale nie edytuje stawek ani ustawień konta.
- Wpisuje umowy w imieniu dowolnego handlowca, zmienia status umowy (przełącznik
  „Zmienia statusy umów”, domyślnie włączony).
- Widzi wszystkie umowy; prowizje na nich — tylko gdy ma permisję jak wyżej.
- Nie widzi nigdy: udziału brokera u spółki, Twojej marży.

### Jeszcze nie zrobione
- Rezerwacja NIP-u i przepinanie klientów między handlowcami — przełączniki już
  istnieją w Koncie, ale nic za nimi nie stoi, bo moduł klientów jeszcze nie
  powstał (pozycja 1 z planu).
- Import danych przez BOK (dziś tylko Ty, właścicielko, możesz importować plik).

## Rzeczy wspólne dla wszystkich ról — zaplanowane, nie zrobione

- **Analityka portfela i zespołu** (pozycja 2 planu): wartości zagrożone,
  prognozy, ranking handlowców.
- **Ocena opłacalności zerwania umowy** przy spadku cen na giełdzie — wymaga
  osobnej integracji z danymi rynkowymi (TGE: fixing, RDN). Dziś mamy tylko
  produkt i kolor jako podpowiedź, nie wyliczenie.
- **Import przez innych niż właściciel**, konwerter mapujący kolumny z obcych
  CRM-ów, lista braków z przypisaną rolą odpowiedzialną.
- **Logo firmy i raporty PDF** — razem z modułem ofertowania.
- Pełna lista otwartych pytań branżowych: `docs/WIEDZA-BRANZOWA.md` i sekcja
  „Otwarte pytania” w `CLAUDE.md`.

## Co konkretnie przetestować teraz (checklista czynności)

1. [ ] Wczytaj dane demonstracyjne (Konto → Import danych).
2. [ ] Zaloguj się jako menedżer (Michał Lex) — sprawdź listę umów zespołu,
       filtry, sortowanie, plakietki produktów.
3. [ ] Zaloguj się jako handlowiec z „najgorszym portfelem” (Paweł Kamiński) —
       sprawdź, że widzi tylko swoje umowy.
4. [ ] Zaloguj się jako BOK (Jessica Kowal albo Joanna Dąbrowska) z wyłączonym przełącznikiem — sprawdź
       brak dostępu do Zespołu.
5. [ ] Włącz BOK-owi „Widzi prowizje…” i sprawdź, że wtedy widzi zespół i może
       zresetować hasło jednego z handlowców, ale nie Twoje.
6. [ ] Na koncie handlowca sprawdź „Ostatnie logowanie” i „Wyloguj wszystkie inne
       urządzenia”.
7. [ ] Usuń dane demonstracyjne (ten sam import, przycisk cofnięcia), żeby
       sprawdzić, że nic prawdziwego nie zostało naruszone.
