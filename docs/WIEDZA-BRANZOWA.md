# Wiedza branżowa: ofertowanie i rezerwacja NIP

Źródło: właścicielka projektu, praktyka rynkowa. Szkic sekcji do skilla
„rynek-brokerski-energii-pl”. Opis praktyki, nie przepisów. Parametry różnią się
między spółkami obrotu, więc w aplikacji mają być konfigurowalne per spółka.

## Rezerwacja NIP

- Rezerwacja dotyczy konkretnej spółki obrotu. Blokuje klienta w tej spółce tak,
  że ofertę może złożyć tylko podmiot, który ma rezerwację.
- Cel: spółka nie licytuje ceny sama ze sobą. Bez rezerwacji trzech brokerów i
  sprzedaż wewnętrzna spółki składaliby oferty temu samemu klientowi.
- Sposób: najczęściej portal partnerski spółki; w spółkach bez systemu e-mail
  (coraz rzadziej).
- Gdy NIP jest już zarezerwowany przez innego agenta albo sprzedaż wewnętrzną:
  odmowa rezerwacji, nie można ofertować w tej spółce. Można ofertować w innej
  spółce. Dlatego brokerzy mają kilka spółek w portfelu.
- Wyjątek: przy prawdziwej relacji z klientem i jego pisemnym poświadczeniu, że
  chce oferty od danego brokera, można rozmawiać z dyrektorem sprzedaży spółki o
  przepięciu rezerwacji na siebie.
- Walka o rezerwacje to codzienność branży: kto ma rezerwację, ten może składać ofertę.

## Jedna oferta na klienta

- W danej spółce obowiązuje jedna oferta dla jednego klienta, zarówno dla
  sprzedaży wewnętrznej spółki, jak i dla handlowców brokera.
- Wewnątrz biura klient należy do jednego handlowca. Broker może przepiąć klientów
  na innego handlowca, np. gdy ktoś odchodzi z zespołu.

## Cenniki i wycena

- Każda spółka ma cennik. Oferta = cena bazowa z cennika + narzut brokera.
- Dla większych klientów wycena indywidualna. Próg zależy od spółki: zwykle
  od 1, 2 albo 4 GWh rocznie. Składa się profil zużycia 15-minutowy lub godzinowy,
  a traderzy spółki wyceniają klienta osobnym procesem.
- Cennik zmienia się zwykle raz w tygodniu, częściej przy dynamicznej sytuacji
  na giełdzie.
- Cennik obowiązuje do wydania nowego. Po wydaniu nowego spółka zwykle gwarantuje
  ceny poprzedniego do końca doby, w której wydała nowy.

## Wnioski dla aplikacji

1. Rezerwacja jako osobny obiekt: klient (NIP) i spółka, handlowiec, status
   (wniosek, potwierdzona, odmowa, wygasła, przepięta), daty, sposób (portal,
   e-mail), numer potwierdzenia, powód odmowy.
2. Ofertę w spółce można utworzyć tylko przy potwierdzonej rezerwacji.
3. Mapa dostępności klienta: dla danego NIP widać, w których spółkach można
   ofertować, a w których klient jest zablokowany.
4. Wniosek o przepięcie rezerwacji z poświadczeniem klienta jako załącznikiem.
5. Własność klienta wewnątrz biura i hurtowe przepinanie klientów na innego
   handlowca, z historią.
6. Cennik w wersjach z datą i godziną wydania. Oferta zapamiętuje wersję cennika.
   Po wydaniu nowego cennika aplikacja ostrzega: „cena z oferty ważna do dziś 23:59”.
7. Próg wyceny indywidualnej per spółka. Powyżej progu zamiast ceny z cennika
   wniosek o wycenę z profilem zużycia.

## Do doprecyzowania

- Czas trwania rezerwacji, przedłużanie, wymagane dane, co po podpisaniu umowy.
- Forma cenników (portal, Excel, PDF) i możliwość importu.
- Ważność wyceny indywidualnej i format profilu.
- Dokumenty przed podpisaniem, gospodarstwa domowe, klienci z wieloma punktami
  poboru, zakres pracy biura obsługi, migracja danych.
