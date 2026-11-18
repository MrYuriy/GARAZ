# GARAZ — backend

Rejestr uprawnień operatorów i zdarzeń wózków widłowych (MVP). FastAPI + Postgres.
Aplikacja kliencka (Flutter, web + Android): repozytorium `GARAZ_app`.

Plan, ustalenia i otwarte pytania: [docs/MVP_PLAN.md](docs/MVP_PLAN.md).

## Lokalnie

```bash
uv sync --group dev
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```

Uruchomienie z bazą (Docker):

```bash
cp .env.sample .env   # uzupełnij hasła i sekrety
docker compose up -d --build
```

API: `http://localhost:<PORT>/api`, dokumentacja: `http://localhost:<PORT>/docs`.
Pierwszy SUPER_ADMIN powstaje przy starcie z `ADMIN_BOOTSTRAP_LOGIN` / `ADMIN_BOOTSTRAP_PASSWORD`.

## Co już działa

- Logowanie loginem (jak w WMS) + hasło; e-mail opcjonalny, tylko do powiadomień, JWT z rotacją refresh tokenów, wylogowanie (jedna sesja / wszystkie), zmiana hasła.
- Hasła bez reguł siły; administrator może wymusić zmianę hasła przy następnym logowaniu.
- Role `SUPER_ADMIN` / `ADMIN` / `MANAGER` (podgląd), zarządzanie kontami (bez usuwania — dezaktywacja).
- Słowniki (`/api/dictionaries/{kind}`): lokalizacje, kategorie uprawnień, typy wózków, pracodawcy, kategorie zdarzeń (z typami zdarzeń i domyślnym „wyłączony”). Pozycje się wyłącza, nie usuwa.
- Producenci i modele wózków (`/api/truck-manufacturers`, `/api/truck-models`): lista, z której wybiera się markę wózka. Usunięcie pozycji używanej przez wózki jest odrzucane (409 z listą tych wózków).
- Rejestr wózków (`/api/trucks`): numer, producent i model (z listy), typ, lokalizacja, status (aktywny / wyłączony z eksploatacji / nieaktywny). Każdy wózek ma kod QR (link `BASE_URL/t/<token>`): podgląd PNG, nowy kod (stara naklejka przestaje działać), PDF z etykietami A4 (8 na arkusz). Wózek dodany przez pomyłkę można usunąć.
- Rejestr operatorów (`/api/operators`): imię i nazwisko, pracodawca, nr karty Hyster Tracker, aktywny/nieaktywny. Operator nie ma konta — identyfikuje go kod QR (losowy token, bez danych osobowych): podgląd PNG, nowy kod, PDF z kartami A4.
- Uprawnienia (`/api/permits`): nr pozwolenia, kategoria, rodzaje wózków, data wydania, ważne do, dokument-podstawa (nazwa, numer, data) + opcjonalny skan (PDF/JPEG/PNG/WebP). Statusy: Aktywne, Zawieszone (ręcznie), Wygasłe (codziennie ok. 00:05 czasu lokalnego). Filtr „wygasające w ciągu N dni”.
- Dziennik zdarzeń (audit log) dla logowań, zmian kont, słowników, wózków, operatorów i uprawnień.
- Limity zapytań (Redis), nagłówki bezpieczeństwa, serwowanie buildu Flutter web pod `/app`.
