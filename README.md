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
- Dziennik zdarzeń (audit log) dla logowań, zmian kont i słowników.
- Limity zapytań (Redis), nagłówki bezpieczeństwa, serwowanie buildu Flutter web pod `/app`.
