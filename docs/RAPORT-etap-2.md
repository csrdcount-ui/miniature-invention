# Raport: platforma brokerska, etap 2

Data: 13 listopada 2026

## W skrócie

Platforma ma rejestr rozliczeń. Właściciel wpisuje, co spółka obrotu faktycznie przelała, a system sam liczy, ile z tego należy się handlowcowi i menedżerowi, co czeka na wypłatę i co jest zagrożone korektą. 43 automatyczne testy przechodzą.

## Co doszło

### 1. Wpływy od spółek

Na karcie umowy właściciel wpisuje kwotę z zestawienia prowizyjnego spółki i wybiera rodzaj wpisu: pierwsza transza, prowizja z zapłaconych faktur albo korekta.

Podział jest proporcjonalny. Jeśli spółka przelała 30% udziału brokera, handlowiec i menedżer dostają po 30% swojej prognozy. Reszta to marża właściciela. Kwoty są zapisywane w chwili wpisu, więc historia się nie przesuwa.

Przykład na umowie z testów: 100 MWh rocznie, 5 lat, narzut 100 zł, broker 77%, handlowiec 40%, override 5% narzutu. Transza od spółki to 11 550 zł. Handlowiec dostaje 6 000 zł, menedżer 750 zł, właścicielowi zostaje 4 800 zł.

Status umowy w lejku sam przechodzi na „Transza 1 wypłacona” albo „Rozliczenia bieżące”. Nigdy się przy tym nie cofa.

### 2. Korekty

Korektę wpisuje się jako kwotę dodatnią, a system zapisuje ją z minusem i dzieli tak samo jak wpływ. Można od razu oznaczyć umowę jako zerwaną.

System nie przyjmie korekty większej niż suma dotychczasowych wpływów z umowy. Na karcie umowy właściciel widzi podpowiedź, ile wyniosłaby korekta proporcjonalna, gdyby klient zerwał umowę dzisiaj.

### 3. Zagrożone korektą

Dla każdej strony system pokazuje kwotę rozliczoną ponad część umowy zrealizowaną do dziś. Część zrealizowaną liczy z pełnych miesięcy od startu dostaw. Przed startem dostaw całe rozliczenie jest zaliczką.

Przykład: rok dostaw z umowy na 5 lat to 20% zrealizowane. Z transzy 11 550 zł zagrożone jest 3 850 zł, w tym 2 000 zł handlowca.

### 4. Wypłaty dla zespołu

Każdy wpis ma osobny znacznik „rozliczono z handlowcem” i „rozliczono z menedżerem”. Strona Rozliczenia pokazuje listę pozycji do wypłaty z przyciskiem przy każdej z nich. Etykieta przycisku zawiera osobę i klienta, więc czytnik ekranu przeczyta, czego dotyczy.

Błędny wpis można usunąć tylko wtedy, gdy nie został jeszcze rozliczony z zespołem. Później poprawia się go korektą.

### 5. Strona Rozliczenia i pulpit

- Tabela: prognoza, rozliczone, pozostało, zagrożone korektą i kwota do wypłaty dla każdej strony.
- Właściciel widzi dodatkowo udział brokera w podziale na spółki obrotu.
- Pulpit ma nową sekcję „Pieniądze w drodze”.
- Eksport historii do pliku CSV, który otwiera się w polskim Excelu: średnik, przecinek dziesiętny, polskie znaki.

### 6. Poufność

Handlowiec i menedżer nie widzą kwoty od spółki, marży właściciela ani uwag do zestawień. Dotyczy to strony, pulpitu i pliku CSV. Wpływy i wypłaty wpisuje tylko właściciel. Jest na to osobny test.

### 7. Poprawka przy okazji

Kwota wklejona z Excela albo z wyciągu bankowego często ma twardą spację jako separator tysięcy. Wcześniej formularz jej nie przyjmował, teraz ją przyjmuje.

## Uruchomienie w internecie

Plik konfiguracyjny Render wskazuje teraz gałąź ccr-4dec9584-0v620t. Jeśli usługa na Render jest już podpięta pod starą gałąź ccr-fcf28ba4-j6eqkl, trzeba zmienić gałąź w ustawieniach usługi. Bez tego Render nie zobaczy etapu 2.

Nowa tabela tworzy się sama przy starcie. Istniejących tabel nie zmieniałem, więc baza z etapu 1 działa bez migracji.

## Nadal otwarte pytania

1. Ile zwykle wynosi override menedżera i od czego jest liczony?
2. Jak spółki płacą resztę po pierwszej transzy: miesięcznie, kwartalnie, rocznie? Rejestr przyjmuje dowolny rytm, ale odpowiedź pozwoli prognozować przepływy w czasie.
3. Jak liczona jest korekta w praktyce: od wolumenu czy od miesięcy? Przez jaki okres broker za nią odpowiada? Teraz system liczy od miesięcy, a właściciel zawsze wpisuje kwotę z zestawienia spółki.

## Proponowany następny krok

Cenniki spółek i porównywarka ofert. To funkcja, której nie da żaden CRM spółki obrotu.
