# Projekt: skrót na telefon dla właściciela i menedżera (12.11.2026, do akceptacji)

Cel: po otwarciu platformy na telefonie w kilka sekund widać kluczowe parametry,
bez przewijania wielu ekranów. Szczegóły zostają tam, gdzie są, o jedno stuknięcie dalej.

## Co pokazał pomiar (emulacja iPhone 13, dane demo, 12.11.2026)

- Strony nie są pomniejszane: nic nie wystaje w bok, tekst ma 18 px (więcej niż
  domyślne 16 px). Najmniejszy tekst (14 px) to podpisy w dolnej belce.
- Prawdziwy problem to ilość treści i kolejność:
  - pulpit: 4,5 ekranu, 9 sekcji zwijanych;
  - Zespół: 12 ekranów u właściciela, 7,6 u menedżera;
  - lista umów: 40 ekranów (wszystkie umowy naraz);
  - pierwszy ekran zajmują nazwa firmy, belka podsekcji, ramka „Dane demonstracyjne”
    i tytuł strony; pierwsza liczba (procent targetu) jest na samym dole ekranu.
- Platforma nie korzysta z systemowej wielkości tekstu na iPhonie (Ustawienia,
  Ekran i jasność, Wielkość tekstu). Kto ma w telefonie powiększony tekst, w platformie
  widzi zwykły rozmiar. Na Androidzie przeglądarka Chrome zwykle to uwzględnia.

## Zasady skrótu

1. Jeden ekran, najwyżej półtora. Do 6 kafelków.
2. Kafelek: nagłówek (do nawigacji czytnikiem po nagłówkach), jedna duża liczba,
   jedno zdanie porównania, link „Szczegóły”. Zero tabel.
3. Najpierw „Wymaga uwagi” (tylko gdy jest coś do zrobienia), potem liczby.
4. Kwoty zaokrąglone, np. „687 tys. zł” zamiast „686 900,00 zł”. Krócej dla oka i dla
   czytnika. Pełna kwota w szczegółach.
5. Na skrócie bez belki podsekcji; ramka demo skrócona do jednego wiersza.
6. Poufność bez zmian: menedżer nie widzi udziału brokera, przychodu spółki ani
   kwoty masy marży całego biura.

## Dolna belka (najwyżej 5 pozycji)

- Właściciel: **Start** (skrót) · Portfel · Zespół · Spółki · **Więcej** (Klienci,
  Konto, Import, Listy wymagań).
- Menedżer: **Start** (skrót) · Mój dzień · Klienci · Zespół · **Więcej** (Portfel,
  Konto).
- Handlowiec i BOK: bez zmian.
- Podpisy w belce z 14 px na 16 px. Aktywna pozycja jak dziś: pogrubienie, kreska
  i `aria-current`.

## Skrót właściciela („Start”)

1. **Wymaga uwagi** (tylko gdy coś jest): oferty czekające 3 dni i dłużej, cenniki
   wygasłe, zlecenia BOK czekające, osoby z „trwałą tendencją spadkową”, alarm małego
   lejka. Każda pozycja to jedno zdanie z liczbą i linkiem.
2. **Sprzedaż miesiąca**: procent targetu biura, masa marży, ile brakuje do targetu.
3. **Przychód spółki w miesiącu** (tylko właściciel) i porównanie z poprzednim
   miesiącem w tym samym dniu.
4. **Zespół**: najlepsza osoba i liczba osób poniżej 50% targetu; link do rankingu.
5. **Oferty złożone**: liczba i prognoza masy marży.
6. **Transza A z umów miesiąca**: ile spółki mają zapłacić biuru (prognoza).

## Skrót menedżera („Start”)

1. **Wymaga uwagi**: osoby z alarmem małego lejka, ze słabszym udziałem drugi miesiąc
   z rzędu lub z trwałą tendencją spadkową, oferty zespołu czekające 3 dni i dłużej.
2. **Sprzedaż zespołu**: procent targetu zespołu, masa marży, ile brakuje.
3. **Mój override w miesiącu** (prognoza).
4. **Udział zespołu w masie marży biura**: bieżący miesiąc i średnia z 5 poprzednich,
   ocena. Tylko procenty.
5. **Mój dzień**: liczba zadań na dziś i zaległych; link.
6. **Lejek zespołu**: klienci w toku według etapów (kontakt, dane, oferta).

## Pozostałe strony na telefonie

- Lista umów: pierwsze 20 i przycisk „Pokaż kolejne 20” zamiast 40 ekranów. Filtry
  bez zmian.
- Zespół: karta osoby skrócona do imienia, procentu targetu i oceny; reszta w
  „Szczegółach”.
- Systemowa wielkość tekstu na iPhonie: włączyć (zmiana w stylach, bez ryzyka dla
  innych telefonów). Sprawdzić przy największym rozmiarze, że nic nie wystaje w bok.

## Etapy

- **A.** Systemowa wielkość tekstu, większe podpisy w belce, krótsza ramka demo.
  Mała zmiana, od razu do sprawdzenia na Twoim telefonie.
- **B.** Skrót właściciela i menedżera, nowa dolna belka z „Start” i „Więcej”.
- **C.** Lista umów po 20 i skrócone karty w Zespole.

## Testy

- Emulacja telefonu (iPhone, Android): skrót mieści się w 1,5 ekranu przy domyślnym
  tekście; przy największym tekście systemowym nic nie wystaje w bok.
- Czytnik ekranu: drzewo dostępności, kolejność nagłówków, `aria-current` w belce,
  każdy kafelek czytany jednym zdaniem.
- Poufność: na skrócie menedżera nie ma udziału brokera, przychodu spółki ani kwoty
  masy marży biura; handlowiec i BOK nie mają skrótu właściciela ani menedżera.
- Liczby na skrócie równe liczbom na stronach szczegółowych.

## Pytania do właścicielki

1. Na jakim telefonie i w jakiej przeglądarce widać małe literki (iPhone, Android;
   Safari, Chrome)? Czy w telefonie jest ustawiony większy tekst albo powiększenie?
   Kto to zauważył: Ty z czytnikiem czy osoba widząca?
2. Czy kolejność i zawartość kafelków się zgadza? Co usunąć, co dodać?
3. Kwoty na skrócie: „687 tys. zł” czy pełne „686 900 zł” (bez groszy)?
4. Belka: czy „Więcej” dla rzadziej używanych zakładek jest w porządku? Które pozycje
   właściciel otwiera najczęściej?
5. Czy skrót ma być stroną startową po zalogowaniu (zamiast pulpitu u właściciela i
   „Mojego dnia” u menedżera)?
