# GARAZ — project context for Claude

Web system for forklift operator permits (*uprawnienia*) and forklift incident
reports (*awarie, uszkodzenia, kolizje*), replacing Excel registers. This repo is
the **backend only** (FastAPI). The client is a Flutter app (web + Android APK) in
the separate repo `GARAZ_app`.

Requirements, agreed decisions, the phased plan and open questions live in
**`docs/MVP_PLAN.md`** — read it first and keep it current.

Architecture is modelled on LangUp (`D:\ceva_part_time\langup_backend`,
`D:\ceva_part_time\langup_mobile`).

## Architecture
Layered modular monolith, async-first. Request flow:
**router → service → repository → model (SQLAlchemy async) → Postgres**.
Pydantic `schemas/` cross the boundaries. DI via `Depends` aliases in `app/dependencies.py`.

New feature = one **vertical**, in this order:
`model → migration → repository → schema → service → router (+ dependencies.py) → tests`.

## Rules that differ from LangUp
- **Repositories never commit** (`repositories/base.py` flushes). The service owns the
  unit of work and commits once at the end, so a change and its audit entry land together.
- **Every change goes through `AuditService.record(...)`** in the same transaction.
- **Time is aware UTC everywhere**: `app.core.time.utcnow()`, columns `UTCDateTime`
  (`models/base.py`). Naive datetimes are refused at the DB boundary. Display zone:
  `settings.app.TIMEZONE` (Europe/Warsaw).
- **Sign-in is by `login`** (the person's WMS login), not email. Logins are stored and
  matched lowercased (`core/security/login.py`). `email` is optional, not unique, and only
  for notifications.
- **No sign-up.** Panel accounts are created by admins. Roles: `SUPER_ADMIN`, `ADMIN`,
  `MANAGER` (read-only panel). Who may manage whom: `MANAGEABLE_ROLES` in `core/security/rbac.py`.
  Deps: `StaffUserDep` (look), `AdminUserDep` (change).
- **Operators are not users** — they never sign in; identified by their QR token.
- Accounts are **disabled, never deleted** (audit keeps pointing at them).
- Refresh tokens rotate. Only a *rotated* token replayed after the grace window counts
  as theft (revokes all sessions); a token retired by logout / logout-all / password
  change / disable just gets 401.
- Outside `ENV=local|test` the app refuses to start on placeholder JWT secrets.

## Commands (uv)
- Tests: `uv run pytest -q` (sqlite in memory; `tests/conftest.py` sets DATABASE_URL itself)
- Lint/format: `uv run ruff check . && uv run ruff format .` (both must pass)
- Migrations: `uv run alembic upgrade head`; drift check: `uv run alembic check`
- Run locally: `uv run python -m app.main` (needs a `.env`, see `.env.sample`)

## DB migrations
Hand-written, zero-padded ids (`00001`, `00002`…), `down_revision` = previous.
`00001` users · refresh_tokens · audit_logs.
Run automatically on start (`entrypoint.sh` → `alembic upgrade head`), then
`scripts/bootstrap_admin.py` seeds the first SUPER_ADMIN from `ADMIN_BOOTSTRAP_*`.

## Conventions
- **Do NOT commit/push/deploy unless explicitly asked — each time separately.** Small logical commits.
- **Never add co-authorship / "Generated with Claude".** Author = the user. Commit without gpg-sign.
- Branches: `main` (releases) + `dev` (integration, deploy from `dev`); work in `feat/*`.
- Models must be cross-dialect (sqlite tests + Postgres): `UUIDType`, `JSONType`, `UTCDateTime`.
- Tests: add new tables to `TEST_TABLES` in `tests/conftest.py`; fixtures `make_user`,
  `login`, `auth_headers(role)`. Test emails use `@garaz.pl` (email-validator rejects `.test`).

## Deploy (planned)
Separate docker compose stack on the home Ubuntu server, behind Cloudflare, own subdomain.
Container names are prefixed `garaz-`; only the API publishes a port (pick a free one —
LangUp uses 8008). The Flutter web build is bind-mounted into `webapp/` and served at
`/app/v/<stamp>/`. Object storage is not in compose yet (the `minio/minio` Docker Hub
image is no longer available) — decide on an S3 store with the first file-storing vertical.
