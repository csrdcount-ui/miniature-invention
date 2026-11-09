# Checklista po rolach: co jest wdrożone a co czeka

Stan na 9.11.2026, commit `979292b`. Pierwsza kolumna zasad: wszystko tu opisane
jest w kodzie na `main`. „Wdrożone” znaczy: na serwerze po ostatnim ręcznym
„Manual Deploy” — sprawdź numer commitu na https://platforma-brokerska.onrender.com/wersja.

Role w aplikacji dziś: **Właściciel**, **Menedżer**, **Handlowiec**, **BOK**.
Zaloguj się do każdej przez dane demonstracyjne (zakładka Konto → Import danych →
„Sprawdź dane demonstracyjne” → zatwierdź → hasła pokażą się raz na ekranie wyniku).

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
  warunkami, 6 handlowców, 1 menedżer, 1 BOK, 60 umów ze scenariuszami (zerwania
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
2. [ ] Zaloguj się jako menedżer (Tomasz Zieliński) — sprawdź listę umów zespołu,
       filtry, sortowanie, plakietki produktów.
3. [ ] Zaloguj się jako handlowiec z „najgorszym portfelem” (Paweł Kamiński) —
       sprawdź, że widzi tylko swoje umowy.
4. [ ] Zaloguj się jako BOK (Joanna Dąbrowska) z wyłączonym przełącznikiem — sprawdź
       brak dostępu do Zespołu.
5. [ ] Włącz BOK-owi „Widzi prowizje…” i sprawdź, że wtedy widzi zespół i może
       zresetować hasło jednego z handlowców, ale nie Twoje.
6. [ ] Na koncie handlowca sprawdź „Ostatnie logowanie” i „Wyloguj wszystkie inne
       urządzenia”.
7. [ ] Usuń dane demonstracyjne (ten sam import, przycisk cofnięcia), żeby
       sprawdzić, że nic prawdziwego nie zostało naruszone.
