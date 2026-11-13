# Projekt: marszruta klienta na telefonie i zdjęcia faktur (13.11.2026, do akceptacji)

Pytanie właścicielki: czy kartę klienta na telefonie da się zrobić jako „marszrutę”,
ekrany przesuwane w prawo i w lewo jak kolejne etapy (biuro, faktury, teren z kalkulatorem),
i czy handlowiec może zrobić zdjęcie faktury, z którego dane trafią do BOK i kalkulatora.
Wsparcie merytoryczne (rozmowa, obiekcje) jest osobnym tematem; tu tylko miejsca na nie.

Stan kodu (13.11.2026): karta klienta to jedna długa strona (następny krok, NIP w BOK,
oferty, listy wymagań, dane, historia). Platforma nie przechowuje plików poza importem Excela
i nie korzysta z żadnej usługi AI.

## 1. Marszruta: ekrany przesuwane palcem

Technicznie: tak, bez aplikacji ze sklepu i bez JavaScriptu (przewijanie poziome
z „przyciąganiem” do ekranu, CSS scroll-snap). Działa na Androidzie i iPhonie.

Ważne ograniczenie: **czytnik ekranu używa przesunięcia w prawo i w lewo do przechodzenia
między elementami** (TalkBack, VoiceOver). Sam slider byłby dla osoby z czytnikiem
nieużywalny. Dlatego marszruta ma trzy drogi do tego samego:

- przesunięcie palcem (handlowiec widzący);
- pasek etapów na górze: cztery przyciski z numerem i stanem, np.
  „2. Dane: faktura u BOK”, „3. Teren: 4 spółki wolne” (każdy jest zwykłym linkiem);
- dla czytnika każdy etap to sekcja z nagłówkiem, czytana po kolei.

Karta otwiera się od razu na etapie, na którym jest klient. Na górze, zawsze widoczne:
nazwa, etap, następny krok, duży przycisk „Zadzwoń”.

### Ekrany marszruty

1. **Kontakt** (biuro): „Zadzwoń”, szybki wynik rozmowy (nie odbiera, oddzwonić,
   umówione spotkanie z godziną i adresem, nie zainteresowany z powodem), notatka
   z dyktowaniem klawiaturą, następny krok. Miejsce na podpowiedzi do rozmowy.
2. **Dane**: „Zrób zdjęcie faktury”, stan rozpoznania („u BOK”, „gotowe”), punkty poboru
   (numer, grupa taryfowa, zużycie, sprzedawca, koniec umowy, okres wypowiedzenia),
   „Wyślij NIP do BOK” i wynik rezerwacji w spółkach.
3. **Teren** (u klienta): skrót najważniejszych danych z faktury, spółki z wolnym NIP-em,
   szybki kalkulator. Marża zmieniana przyciskami „minus 5 zł” i „plus 5 zł” plus pole
   liczby; suwak tylko jako dodatek, bo jest nieprecyzyjny palcem i z czytnikiem.
   Wynik: cena dla klienta, marża, prowizja handlowca, ostrzeżenia (limit, wycena
   indywidualna). Miejsce na obiekcje.
4. **Oferta i umowa**: zapis oferty, decyzja klienta, umowa do podpisu, przekazanie do BOK.

### Dzień handlowca w tej nawigacji (zarys)

- Rano „Mój dzień”: lista telefonów i spotkań z godziną. Stuknięcie w klienta otwiera
  marszrutę na właściwym ekranie.
- Telefon: „Zadzwoń”, rozmowa, powrót do platformy, jeden przycisk z wynikiem.
  Następny krok ustawia się sam.
- Spotkanie: z „Mój dzień” do adresu w mapach telefonu. U klienta ekran „Teren”:
  zdjęcie faktury, kalkulator, oferta.
- Po spotkaniu: notatka dyktowana, następny krok, ewentualnie oferta.

## 2. Zdjęcie faktury

### Samo zdjęcie: proste

Przycisk „Zrób zdjęcie faktury” otwiera aparat telefonu bezpośrednio ze strony
(standardowe pole pliku), bez instalowania aplikacji. Kilka zdjęć na raz (strony faktury).

Wymaga decyzji, która już czeka: **magazyn plików w UE i okres przechowywania (RODO)**.
Faktury zawierają dane klienta; trzeba je gdzieś trzymać i po czasie usuwać.

### Rozpoznanie danych: możliwe, ale nie bez człowieka

Odczyt danych ze zdjęcia przez model AI (NIP, nazwa, adres, numer punktu poboru, grupa
taryfowa, moc umowna, zużycie w okresie i strefach, sprzedawca, operator sieci) jest
technicznie wykonalny i dobrze działa na czytelnych, drukowanych fakturach. Ograniczenia:

- zdjęcia krzywe, nieostre, z odbiciem światła dają błędy; liczby trzeba sprawdzić;
- faktura obejmuje okres rozliczeniowy, więc zużycie roczne wymaga kilku faktur albo
  danych z historii zużycia (sposób liczenia do potwierdzenia z właścicielką);
- data końca obecnej umowy i okres wypowiedzenia zwykle nie są na fakturze;
- wysłanie faktury do zewnętrznej usługi AI to przetwarzanie danych klienta przez
  podmiot zewnętrzny: umowa powierzenia, lokalizacja przetwarzania, zgoda właścicielki;
- koszt rozpoznania jednej faktury: do sprawdzenia w aktualnym cenniku przed decyzją.

### Proponowany proces: „terminal faktur” z dwiema prędkościami

1. Handlowiec u klienta robi zdjęcia. Prowadzi rozmowę dalej.
2. Zdjęcia trafiają do nowej kolejki BOK „Faktury do wprowadzenia”.
3. (Opcja z AI) W kilka sekund platforma wypełnia projekt danych z faktury. Handlowiec
   widzi je od razu z oznaczeniem „niesprawdzone przez BOK” i może już liczyć wstępnie.
4. BOK sprawdza i poprawia projekt (krótkie zadanie zamiast przepisywania), zatwierdza.
   Dane trafiają do punktów poboru na karcie i do kalkulatora.
5. Handlowiec dostaje informację „dane z faktury gotowe” (patrz powiadomienia
   w `docs/PROJEKT-PROCES-TEREN.md`).

Bez AI proces też działa: BOK przepisuje dane ze zdjęcia. Wolniej, ale bez zewnętrznej
usługi. Dlatego kolejność: najpierw kolejka zdjęć dla BOK, AI jako dodatek po decyzji.

## Kolejność wdrożenia (propozycja)

1. Marszruta: pasek etapów i ekrany na telefonie z obecnych sekcji karty (bez nowych danych).
2. Szybki wynik rozmowy, spotkanie z godziną i adresem, notatka (z `PROJEKT-PROCES-TEREN`).
3. Punkty poboru na karcie i w kalkulatorze; szybki kalkulator na ekranie „Teren”.
4. Zdjęcia faktur i kolejka BOK (po decyzji o magazynie plików).
5. Rozpoznanie faktur przez AI (po decyzji o usłudze zewnętrznej i koszcie).
6. Podpowiedzi rozmów i obiekcji w przygotowanych miejscach (osobna rozmowa).

## Pytania do właścicielki

1. Czy cztery ekrany (Kontakt, Dane, Teren, Oferta i umowa) oddają pracę handlowca?
2. Ile faktur zwykle trzeba, żeby policzyć zużycie roczne, i skąd bierze się dziś ta liczba?
3. Czy BOK jest dostępny w czasie spotkań handlowców (godziny), żeby wprowadzić dane
   w trakcie rozmowy?
4. Czy zgadzasz się na wysyłanie zdjęć faktur do usługi AI (po sprawdzeniu umowy
   powierzenia i lokalizacji danych), czy tylko BOK?
5. Jak długo trzymać zdjęcia faktur po wprowadzeniu danych?

## Odpowiedzi i stan (13.11.2026)

Odpowiedzi: 1) cztery ekrany tak; 2) wolumen z 6 faktur albo z dwóch oddalonych o co najmniej
10 miesięcy (różnica stanów licznika), 6 faktur pokazuje też sezonowość; 3) BOK zwykle dostępny
w trakcie spotkań; 4) pilotaż bez AI: dane wpisuje BOK („odeślij do BOK”) albo sam handlowiec,
AI jako przyszła płatna opcja, architektura ma na nią miejsce; 5) okres przechowywania zdjęć:
bez odpowiedzi, przyjęte: zdjęcia usuwane, gdy BOK zamknie zadanie.

ZROBIONE: marszruta (cztery ekrany, pasek etapów z `aria-current="step"`, przesuwanie palcem
przez CSS scroll-snap tylko na telefonie, linki z „Mój dzień” prowadzą do właściwego ekranu),
punkty poboru (`MeteringPoint`), dane z faktur (`InvoiceReading`, źródło handlowiec/BOK/ai,
`verified`), wolumen roczny i profil (`app/faktury.py`), termin wypowiedzenia, kalkulator
z wolumenem i grupą z karty, „Odeślij zdjęcia faktur do BOK” (`InvoiceTask`, `InvoicePhoto`,
zdjęcia pomniejszane do JPEG, PDF bez zmian), kolejka BOK
„Faktury do wprowadzenia”, „dane z faktur gotowe” w „Mój dzień”. Miejsce na AI: `extractor()`
zwraca None. Nie zrobione: szybki wynik rozmowy, spotkanie z godziną i adresem, kalendarz ICS,
kalkulator z przyciskami ±5 zł, podpowiedzi rozmów.

## Archiwizacja faktur przez BOK (decyzja 13.11.2026)

Zdjęcia faktur są potrzebne biuru w dokumentacji dla spółki obrotu, więc nie znikają przy
zamknięciu zadania. BOK pobiera je (paczka ZIP albo pojedyncze pliki; nazwy: klient, NIP, data),
zapisuje na dysku biura i dopiero wtedy, po pytaniu „czy faktury są zapisane w dokumentacji
biura?” i potwierdzeniu, usuwa z platformy. Platforma zapisuje, kto i kiedy pobrał każdy plik;
niepobrane pliki wymagają osobnego potwierdzenia. Później możliwy bezpośredni zapis na dysk
biura (Google Drive, OneDrive lub SharePoint) — po ustaleniu, z czego biuro korzysta.
