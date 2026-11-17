"""What a login may look like.

Logins come from the WMS, where they are short account names ("jkowalski",
"PL.ANNA_N"). Matching is case-insensitive — nobody should be locked out by
Caps Lock — so logins are stored lowercased and compared that way.
"""

import re

LOGIN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")


def normalize_login(value: str) -> str:
    return value.strip().lower()


def validate_login(value: str) -> str:
    login = normalize_login(value)
    if not LOGIN_PATTERN.match(login):
        raise ValueError(
            "Login: 2–64 characters — letters, digits, dot, underscore or hyphen; starting with a letter or digit"
        )
    return login
