# Platforma brokerska — energia elektryczna i gaz

Aplikacja dla firm brokerskich: umowy klientów, reguły prowizji per spółka obrotu,
podział narzutu między brokera, handlowca, menedżera i właściciela, z poufnością warunków.

## Uruchomienie lokalne

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m app.demo            # opcjonalnie: dane demo (hasło: demo-haslo-123)
uvicorn app.main:app --reload # http://localhost:8000
python -m pytest              # testy
```

Bez danych demo pierwsze wejście prowadzi do utworzenia konta właściciela.

## Zmienne środowiskowe

- `DATABASE_URL` — domyślnie SQLite `broker.db`; produkcyjnie PostgreSQL.
- `SECRET_KEY` — klucz podpisu sesji (wymagany na produkcji, inaczej sesje znikają po restarcie).
- `SECURE_COOKIES=1` — ciasteczka tylko po HTTPS.
- `OWNER_EMAIL`, `OWNER_PASSWORD`, `OWNER_NAME` — opcjonalnie tworzą właściciela przy pustej bazie.

## Struktura

- `app/engine.py` — silnik prowizji (czyste funkcje, Decimal). Baza procentów opisana w nagłówku pliku.
- `app/services.py` — reguły na dzień, tworzenie umów z zamrożeniem reguł, uprawnienia, widoki przycięte do roli.
- `app/models.py` — model danych (wersjonowane reguły spółek i stawki osób).
- `app/main.py` — strony i formularze (bez JavaScriptu, pod czytnik ekranu i telefon).
- `tests/` — testy silnika i testy poufności per rola.

## Zasady

- Każdy procent jest ustawieniem właściciela: per spółka (udział brokera, pierwsza transza,
  wyzwalacz, limit narzutu, okres nowych przyłączy, korekta) i per osoba (udział w narzucie, override).
- Zmiany reguł mają datę obowiązywania; umowa zamraża reguły z dnia podpisania.
- Handlowiec i menedżer nie dostają z serwera udziału brokera ani marży właściciela.
