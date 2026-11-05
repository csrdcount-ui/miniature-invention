# Raport: platforma brokerska, etap 1

Data: 5 listopada 2026

## W skrócie

Pierwsza wersja działa lokalnie i przechodzi 34 automatyczne testy. Kod jest w repozytorium miniature-invention, na gałęzi ccr-fcf28ba4-j6eqkl. Aplikacja nie jest jeszcze dostępna w internecie, bo do tego potrzebna jest Twoja zgoda.

## Co zostało zrobione

### 1. Silnik prowizji

To serce systemu. Silnik bierze umowę i reguły jej spółki, a wylicza:
- wolumen z całego okresu umowy;
- całą masę narzutu;
- udział brokera od spółki obrotu;
- prowizję handlowca, liczoną od całego narzutu;
- override menedżera, liczony od całego narzutu albo od prowizji handlowca, zależnie od ustawienia;
- marżę właściciela.

Każda kwota jest dodatkowo rozbita w czasie na pierwszą transzę i resztę płaconą po zapłaconych fakturach. Dla nowych przyłączy dochodzi trzecia część: prowizja z faktur przez pierwsze miesiące, zwykle 12. Pierwsza transza jest wtedy liczona od reszty umowy.

Silnik liczy też korektę przy zerwaniu umowy. Działa proporcjonalnie do niezrealizowanej części umowy i przenosi korektę na handlowca i menedżera. Ta funkcja nie ma jeszcze ekranu.

Kontrola na Twoim przykładzie: 100 MWh rocznie, 5 lat, narzut 100 zł, broker 75%, handlowiec 40%, transza 50%. Wynik: masa narzutu 50 000 zł, broker 37 500 zł, handlowiec 20 000 zł, właściciel 17 500 zł, transza brokera 18 750 zł, transza handlowca 10 000 zł. Zgadza się z Twoimi liczbami.

### 2. Reguły ustawiane przez właściciela, nic nie jest zaszyte na stałe

Dla każdej spółki obrotu osobno właściciel ustawia:
- udział brokera, na przykład 77, 75 albo 70 i pół procenta;
- procent pierwszej transzy;
- kiedy spółka płaci pierwszą transzę: po weryfikacji, po zmianie sprzedawcy albo po starcie dostaw;
- limit narzutu, na przykład 200 zł za MWh, albo brak limitu;
- przez ile miesięcy nowe przyłącza rozliczane są z faktur;
- czy spółka stosuje korektę.

Dla każdej osoby osobno ustawia procent od całego narzutu, a dla menedżera także override i to, od czego jest liczony.

Każda zmiana ma datę, od której obowiązuje. Umowa w dniu zapisu zamraża obowiązujące wtedy procenty. Zmiana warunków ze spółką albo stawki handlowca nie przelicza więc wstecz starych umów. Jest na to test.

### 3. Trzy role i poufność

Handlowiec widzi tylko swoje umowy: cenę dla klienta, cały narzut i swoją prowizję z transzami.

Menedżer widzi swoje umowy i umowy zespołu, prowizje handlowców i swój override.

Właściciel widzi wszystko: udział brokera, marżę netto i warunki każdej spółki.

Blokada działa po stronie serwera. Handlowiec nie dostaje tych danych nawet w kodzie strony. Testy sprawdzają, że na jego stronie nie pojawia się ani udział brokera, ani marża, ani procent spółki. Umowę spoza swoich uprawnień system pokazuje jako „nie znaleziono”, żeby nie zdradzać, że w ogóle istnieje.

### 4. Ekrany

- Logowanie i pierwsze uruchomienie, czyli utworzenie konta właściciela.
- Pulpit z podsumowaniem portfela, inny dla każdej roli.
- Lista umów i karta umowy z tabelą podziału prowizji.
- Formularz nowej umowy. Sprawdza limit narzutu spółki i sumę kontrolną NIP, a blokuje spółkę, która nie ma ustawionych reguł.
- Status umowy w lejku, 11 etapów od leada do zakończenia albo zerwania.
- Panel spółek i reguł z historią zmian.
- Panel zespołu i stawek z historią zmian.
- Zmiana hasła.

### 5. Dostępność i telefon

Strony działają bez JavaScriptu. Każde pole formularza ma etykietę i podpowiedź, które czyta czytnik ekranu. Komunikaty o błędach są ogłaszane automatycznie. Jest odnośnik „Przejdź do treści”, a nagłówki mają poprawną hierarchię.

Kwoty w tabelach mają opisane wiersze i kolumny. Czytnik przeczyta na przykład „Twoja prowizja, Pierwsza transza, 48 768,75 zł”. Przyciski mają co najmniej 44 piksele. Działa tryb ciemny.

Sprawdziłem to na emulacji telefonu i na drzewie dostępności, czyli na tym, co dostaje czytnik ekranu.

### 6. Bezpieczeństwo

- Hasła są przechowywane jako bezpieczny skrót, nie jako tekst.
- Każdy formularz jest chroniony przed podszywaniem się pod użytkownika.
- Sesja wygasa po 12 godzinach.
- Żadne hasło ani klucz nie trafiło do kodu.

## Jak to wypróbować

Potrzebny jest komputer z Pythonem albo uruchomienie w chmurze, opisane niżej. Polecenie `python -m app.demo` tworzy dane przykładowe: dwie spółki (Alfa 77% i transza 30%, Beta 70% i transza 50%), menedżera, dwóch handlowców i pięć umów.

Konta demo, wszystkie z hasłem demo-haslo-123:
- wlasciciel@demo.pl
- menedzer@demo.pl
- handlowiec@demo.pl
- junior@demo.pl

## Czego jeszcze nie ma

1. Uruchomienia w internecie. Plik konfiguracyjny dla Render jest gotowy, ale wymaga Twojej zgody, bo to koszt około 7 dolarów miesięcznie za serwer plus baza danych.
2. Rejestru wypłat: co spółka faktycznie zapłaciła, co jest zaległe, co zagrożone korektą. Silnik korekty już działa, brakuje ekranu i zapisu wypłat.
3. Cenników spółek i porównywarki ofert.
4. Importu i eksportu do Excela.

## Pytania do Ciebie

Domyślne wartości są tylko przykładowe, więc potrzebuję trzech informacji z rynku:
1. Ile zwykle wynosi override menedżera i czy jest liczony od całego narzutu, czy od prowizji handlowca. Obie opcje już działają, chodzi o domyślną.
2. Jak spółki płacą resztę po pierwszej transzy: miesięcznie z każdej faktury, kwartalnie, rocznie?
3. Jak w praktyce liczona jest korekta: proporcjonalnie do niewykorzystanego wolumenu czy do pozostałych miesięcy? Przez jaki okres broker za nią odpowiada?

## Proponowany następny krok

1. Uruchomienie w internecie, żebyś mógł przetestować aplikację na telefonie. Wymaga Twojej zgody.
2. Rejestr wypłat i korekt.
3. Cenniki i porównywarka ofert.
