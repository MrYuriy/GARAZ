#!/usr/bin/env python3
"""Make sure the instance has a SUPER_ADMIN.

There is no sign-up — only administrators create accounts — so a fresh or
emptied database leaves nobody able to sign in. This closes that gap from
ADMIN_BOOTSTRAP_LOGIN / ADMIN_BOOTSTRAP_PASSWORD.

Run from entrypoint.sh on every container start, deliberately not as a
migration: a migration runs once, and the case that matters is the second time
a database is emptied. The work sits behind an "is there already a
SUPER_ADMIN" check, so every start but the one that needs it is a no-op.

Silent when the variables are unset, and it never fails the start.

    uv run python -m scripts.bootstrap_admin
"""

import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("bootstrap_admin")


async def ensure_admin(sessionmaker=None) -> str:
    """Create or promote the configured SUPER_ADMIN. Returns what happened."""
    from app.core import settings
    from app.core.security.login import validate_login
    from app.core.security.password import hash_password
    from app.enums.user import RoleEnum, UserStatus
    from app.repositories.user import UserRepository

    raw_login = (settings.auth.ADMIN_BOOTSTRAP_LOGIN or "").strip()
    password = settings.auth.ADMIN_BOOTSTRAP_PASSWORD
    if not raw_login or not password:
        return "not configured"
    login = validate_login(raw_login)

    if sessionmaker is None:
        from app.database.postgres import async_session

        sessionmaker = async_session

    async with sessionmaker() as session:
        users = UserRepository(session)
        if await users.any_with_role((RoleEnum.SUPER_ADMIN.value,)):
            return "a SUPER_ADMIN already exists"

        existing = await users.get_by_login(login)
        if existing:
            # Created before the variable was set. Promoting beats refusing.
            await users.update_one(existing, {"role": RoleEnum.SUPER_ADMIN.value, "status": UserStatus.ACTIVE.value})
            outcome = f"promoted {login} to SUPER_ADMIN"
        else:
            await users.create_one(
                {
                    "login": login,
                    "hashed_password": hash_password(password),
                    "role": RoleEnum.SUPER_ADMIN.value,
                    "status": UserStatus.ACTIVE.value,
                }
            )
            outcome = f"created {login} as SUPER_ADMIN"
        await session.commit()
        return outcome


def main() -> int:
    try:
        logger.info("bootstrap_admin: %s", asyncio.run(ensure_admin()))
    except Exception:  # noqa: BLE001 — seeding must never stop the app starting
        logger.exception("bootstrap_admin: failed, carrying on")
    return 0


if __name__ == "__main__":
    sys.exit(main())
