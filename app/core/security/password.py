# Password hashing/verification helpers (bcrypt).
#
# No strength rules on purpose: administrators hand out a starting password
# and the user picks their own on first sign-in (`must_change_password`).
import bcrypt

# bcrypt only reads the first 72 bytes, and bcrypt>=5 refuses longer input
# outright. Cutting both sides the same way keeps long passphrases working.
_BCRYPT_MAX_BYTES = 72


def _encode(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_encode(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_encode(password), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
