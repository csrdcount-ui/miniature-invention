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
- Czas rezerwacji zależy od spółki: od 30 do 90 dni. Można ją przedłużyć, jeśli są
  twarde dowody prowadzonych rozmów: e-maile, złożone oferty, e-mail od klienta, że
  wstrzymuje decyzję, ale negocjacje trwają.
- Klient z cennika: biuro obsługi (BOK) wpisuje NIP do systemu spółki i sprawdza,
  czy jest wolny. W mniej zaawansowanych spółkach wysyła prośbę e-mailem. Każda
  spółka ma własną strukturę tytułu i treści, np. „Rezerwacja: NIP: nazwa firmy”.
- Po podpisaniu umowy rezerwacja zostaje przy brokerze na cały okres umowy, żeby
  mógł ją przedłużyć przed końcem albo po nim.

## Jedna oferta na klienta

- W danej spółce obowiązuje jedna oferta dla jednego klienta, zarówno dla
  sprzedaży wewnętrznej spółki, jak i dla handlowców brokera.
- Wewnątrz biura klient należy do jednego handlowca. Broker może przepiąć klientów
  na innego handlowca, np. gdy ktoś odchodzi z zespołu.

## Dokumenty i weryfikacja klienta

- Wymagane dokumenty zależą od spółki. Zawsze: faktury dystrybucyjne.
- Pełnomocnictwo do wypowiedzenia starej umowy jest zwykle częścią nowej umowy,
  więc osobne pełnomocnictwo najczęściej nie jest potrzebne.
- Wypowiedzenie z wyprzedzeniem: gdy obecny sprzedawca ma np. 6-miesięczny okres
  wypowiedzenia, a moment na nową umowę jest niekorzystny, broker może w imieniu
  klienta wypowiedzieć starą umowę i w tym czasie szukać najlepszej oferty.
- Przy większych klientach scoring: sprawdzenie w wywiadowniach gospodarczych i
  rejestrach dłużników, a także informacji o zaległościach publikowanych na
  fakturach za energię.

## Biuro obsługi klienta (BOK)

- Centrum zarządzania danymi i całej operacji biura brokerskiego.
- Nie zna warunków umowy agencyjnej właściciela ze spółką.
- Rezerwuje NIP-y, kompletuje i sprawdza dokumenty, dołącza wyceny PDF od spółek
  do oferty brokera, pilnuje przepływu dokumentów do spółek.
- Jest najwyższą instancją w sprawie kompletności dokumentów i pilnuje handlowców,
  bo od kompletności zależy wypłata prowizji. Aplikacja ma mobilizować handlowca
  już przy wpisywaniu, a BOK zatwierdza.

## Cenniki i wycena

- Każda spółka ma cennik. Oferta = cena bazowa z cennika + narzut brokera.
- Dla większych klientów wycena indywidualna. Próg zależy od spółki: zwykle
  od 1, 2 albo 4 GWh rocznie. Składa się profil zużycia 15-minutowy lub godzinowy,
  a traderzy spółki wyceniają klienta osobnym procesem.
- Cennik zmienia się zwykle raz w tygodniu, częściej przy dynamicznej sytuacji
  na giełdzie.
- Cennik obowiązuje do wydania nowego. Po wydaniu nowego spółka zwykle gwarantuje
  ceny poprzedniego do końca doby, w której wydała nowy.
- Spółki z własnym systemem: ofertę generuje się w systemie spółki i system wysyła
  ją klientowi. Oferta zaakceptowana przez klienta jest zobowiązaniem do podpisania
  umowy; umowę ostateczną spółka przygotowuje w ciągu około tygodnia.
- Wyceny indywidualne przychodzą zwykle jako PDF, e-mailem albo do pobrania z
  systemu spółki. BOK dołącza je do oferty brokera.

## Karta spółki obrotu

- Część właściciela: umowa agencyjna, udział w narzucie, transze, korekty, rozliczenia.
- Część BOK: sposób rezerwacji NIP (system albo e-mail, adres, szablon tytułu i
  treści), czas rezerwacji i warunki przedłużenia, wymagane dokumenty, próg wyceny
  indywidualnej, kontakty w spółce.

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
8. Rola BOK z własnymi uprawnieniami: wszystkie klienci, umowy i dokumenty, bez
   warunków właściciela ze spółkami.
9. Szablony e-maili per spółka (rezerwacja, przedłużenie, wysyłka dokumentów) z
   polami podstawianymi automatycznie: NIP, nazwa klienta, numer punktu poboru.
10. Lista kontrolna dokumentów per spółka; umowa nie przejdzie do spółki, dopóki
    BOK nie potwierdzi kompletności.
11. Termin wypowiedzenia starej umowy jako twardy termin w kalendarzu: do kiedy
    klient musi mieć nową umowę.
12. Rezerwacja trwająca przez okres umowy jako podstawa przypomnień o odnowieniu.

## Do doprecyzowania

Lista otwartych pytań jest w rozmowie z właścicielką projektu; tu trafiają
tylko potwierdzone odpowiedzi.
