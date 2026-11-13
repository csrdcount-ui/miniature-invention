# Projekt: proces handlowca w terenie, od telefonu do umowy (13.11.2026, do akceptacji)

Powód: pierwsza informacja zwrotna od handlowca i menedżera (13.11.2026): kierunek dobry,
czytelne na telefonie, ale proces w terenie trzeba dopracować. Ten dokument przechodzi cały
proces krok po kroku i dla każdego kroku mówi: co platforma robi dziś, czego brakuje, co
proponuję. Wszystko opiera się na stanie kodu z 13.11.2026 (commit po f53634e).

## Proces, jak go opisałaś

1. Telefon do klienta, umówienie spotkania.
2. Wpis do kalendarza.
3. Notatka ze spotkania.
4. Karta klienta.
5. Sprawdzenie NIP przez BOK, informacja zwrotna.
6. Ofertowanie.
7. Co dalej: decyzja klienta, umowa, przekazanie do BOK, spółka.

## Krok po kroku

### 1. Telefon i umówienie spotkania

Dziś:
- „Szybki lead” (nazwa firmy, telefon, opcjonalnie NIP, notatka) z „Mój dzień”.
- Numer telefonu jest linkiem: stuknięcie dzwoni.
- Po rozmowie: „Zapisz rozmowę i następny krok” (rodzaj: telefon, spotkanie, e-mail; wynik;
  następny krok z datą).

Brak:
- Następny krok ma **tylko datę**: bez godziny, miejsca i adresu. „Spotkanie we wtorek” bez
  godziny nie jest spotkaniem.
- Po rozmowie trzeba wypełnić formularz. W terenie to za dużo.

Propozycja:
- **Szybki wynik rozmowy w dwóch stuknięciach**: po telefonie na karcie przyciski
  „Nie odbiera”, „Oddzwonić (kiedy)”, „Umówione spotkanie”, „Nie zainteresowany (powód)”,
  „Wyślij ofertę”. Każdy sam ustawia następny krok.
- **Spotkanie jako osobny wpis**: data, godzina, miejsce lub adres (link do mapy w telefonie),
  osoba, z którą się spotykamy.

### 2. Kalendarz

Dziś: lista „Dziś” i „Tydzień” w „Mój dzień”, tylko daty. Nie ma kalendarza w telefonie.

Propozycja (zgodnie z `docs/PROJEKT-DZIEN-HANDLOWCA.md`):
- **Subskrypcja ICS**: spotkania i zadania handlowca pojawiają się w kalendarzu telefonu
  (Google lub Samsung) z jego własnymi przypomnieniami. Działa z aplikacji do telefonu.
- Widok „Tydzień” jako lista dzień po dniu, nie siatka (czytnik ekranu).
- Dwustronna synchronizacja z Google Calendar: dopiero jeśli okaże się potrzebna.

### 3. Notatka

Dziś: pole „wynik rozmowy” w formularzu rozmowy, oś zdarzeń na karcie (kto, co, kiedy).

Propozycja:
- **„Notatka” jako szybki przycisk na karcie**, z dyktowaniem klawiaturą telefonu (nie
  potrzeba nowej technologii). Możliwa też bez wybierania etapu.
- Notatka pojawia się na osi zdarzeń i widzi ją menedżer (do wglądu w pracę zespołu).

### 4. Karta klienta

Dziś: nazwa, NIP z sumą kontrolną, osoba kontaktowa, telefon, e-mail, źródło, etap, następny
krok, oś zdarzeń, oferty. Jeden NIP, jeden opiekun w biurze.

Brak:
- Nazwa firmy z wykazu podatników po NIP (zapisane jako otwarte).
- Punkty poboru (adres, numer, grupa taryfowa, roczne zużycie, data końca obecnej umowy,
  okres wypowiedzenia). To jest dane potrzebne do oferty, a dziś nie ma gdzie ich wpisać.
- Dokumenty klienta (faktury dystrybucyjne, profil zużycia).

Propozycja:
- **Punkty poboru** na karcie klienta (wchodzą do kalkulatora: grupa i wolumen z karty, nie
  z ręcznego wpisu). Data końca umowy i okres wypowiedzenia zasilają „Okazje” w „Mój dzień”.
- Dokumenty: najpierw lista „czego brakuje” (jest w formie list wymagań). Same pliki wymagają
  decyzji o magazynie plików w UE i okresie przechowywania (RODO), która jest otwarta.

### 5. Sprawdzenie NIP w BOK

Dziś: handlowiec wybiera spółki, BOK w kolejce wpisuje wynik (zarezerwowany do daty, zajęty,
negatywny scoring), wynik jest na karcie klienta i w „Mój dzień”.

Brak:
- **Powiadomienie.** Handlowiec dowiaduje się o odpowiedzi BOK dopiero po otwarciu
  platformy. W terenie to oznacza godziny opóźnienia.
- Brak terminu: jak długo BOK ma na odpowiedź, i alarmu, gdy BOK nie odpowiada.

Propozycja (od najprostszej):
- Licznik „Od BOK” przy pozycji „Mój dzień” w dolnej belce (widać bez wchodzenia).
- **Powiadomienie e-mail** o odpowiedzi BOK (wymaga skrzynki nadawczej i zgody, patrz
  pytania).
- Powiadomienie w telefonie (aplikacja zainstalowana na ekranie głównym): osobna, większa
  praca; decyzja po teście z handlowcem.
- Cel odpowiedzi BOK ustawiany przez właściciela i alarm dla menedżera po jego przekroczeniu.

### 6. Ofertowanie

Dziś: oferta tylko w spółce z potwierdzoną rezerwacją, kalkulator z cenników (2 do 5 lat),
oferta ważna 7 dni, telefon po 3 dniach, ostrzeżenie o limicie marży i o wycenie
indywidualnej.

Brak:
- Dane z punktów poboru w kalkulatorze (patrz krok 4).
- **Wysłanie oferty klientowi z platformy** (PDF z logo biura albo wiadomość). Nie wiemy, czy
  to potrzebne: otwarte pytanie „ofertownik” z `CLAUDE.md`.

### 7. Co dalej po ofercie

Dziś: „Klient podpisał: zapisz umowę” (formularz umowy wypełniony z oferty) albo „Klient
odrzucił ofertę” (z powodem). Umowa ma statusy od „Umowa podpisana” do „Rozliczenia bieżące”,
które aktualizuje BOK.

Brak:
- **Przekazanie do BOK.** Po podpisaniu umowy BOK nie dostaje zlecenia „przygotuj umowę”
  z listą braków (faktury, dokumenty spółki, numery punktów poboru, sposób podpisu).
- Pomiędzy „oferta” a „umowa podpisana” brakuje etapu **„umowa do podpisu”**: wysłana do
  klienta, czeka na Autenti, SMS albo papier.
- Brak widoku „co BOK musi zrobić z tą umową”, w którym handlowiec widzi postęp (weryfikacja
  spółki, zmiana sprzedawcy, start dostaw).

Propozycja:
- Etap „Umowa do podpisu” z polem „sposób podpisu” i listą wymagań („Co jest potrzebne do
  przygotowania umowy”), którą dziś właściciel edytuje, a handlowiec widzi.
- **Kolejka BOK „Do przygotowania umów”** obok „Do sprawdzenia NIP”: lista braków przy umowie,
  BOK zmienia status, handlowiec widzi go na karcie.

## Kolejność wdrożenia (propozycja)

1. **Spotkanie z godziną i miejscem, szybki wynik rozmowy, szybka notatka** (kroki 1 i 3).
   Najczęściej używane w terenie.
2. **Kalendarz ICS** (krok 2).
3. **Punkty poboru i dane do kalkulatora** (kroki 4 i 6).
4. **Powiadomienie od BOK, licznik w belce, termin odpowiedzi** (krok 5).
5. **Etap „umowa do podpisu” i kolejka BOK „Do przygotowania umów”** (krok 7).
6. Wycena indywidualna, dokumenty w magazynie plików, PDF oferty: po decyzjach.

Każdy etap wdrażamy osobno, z testem na danych demo, a potem z handlowcem, który już zna
platformę.

## Test z handlowcem

Po etapie 1 proponuję jeden prawdziwy dzień pracy handlowca z platformą, z listą: ile
stuknięć zajmuje telefon z wynikiem, ile spotkanie, ile notatka. Mierzymy liczbę stuknięć i
miejsca, w których handlowiec wraca do notatnika albo kalendarza w telefonie. To pokaże, co
jeszcze zmienić, lepiej niż projekt przy biurku.

## Pytania do właścicielki

1. W terenie bywa brak zasięgu? Jeśli tak, czy handlowiec musi móc zapisać notatkę bez
   internetu i wysłać ją później? To duża różnica w pracy (osobny etap).
2. Czy handlowiec ma w telefonie Google Calendar, kalendarz Samsunga, czy Outlook? Od tego
   zależy, jak zrobić ICS.
3. Powiadomienie od BOK: e-mail wystarczy, czy ma być powiadomienie w telefonie?
4. Ile czasu BOK ma zwykle na odpowiedź w sprawie NIP (godziny, dzień)?
5. Umowa: który sposób podpisu jest najczęstszy (Autenti, SMS, papier)? To zmienia etap
   „do podpisu”.
6. Czy handlowiec wysyła ofertę klientowi z platformy (PDF, wiadomość), czy robi to we
   własnym narzędziu spółki?
7. Kto zamyka sprawę po umowie: BOK całkowicie, czy handlowiec nadal pilnuje do
   „startu dostaw”?
