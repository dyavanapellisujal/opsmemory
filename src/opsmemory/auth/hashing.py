"""Password hashing and token generation (standard library only).

PBKDF2-HMAC-SHA256 with a per-password random salt — dependency-free and
sufficient for the MVP. Swap for argon2/bcrypt behind this module if needed.
"""

import hashlib
import hmac
import secrets

_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    """Hash a password, returning ``pbkdf2_sha256$iters$salt$hash``."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITERATIONS).hex()
    return f"pbkdf2_sha256${_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    """Verify a password against a stored PBKDF2 hash (constant-time)."""
    try:
        algorithm, iterations, salt, expected = stored.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations)).hex()
    return hmac.compare_digest(digest, expected)


def generate_token() -> str:
    """Generate an opaque session token."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256 of a token, for storage (never store the raw token)."""
    return hashlib.sha256(token.encode()).hexdigest()
