import hashlib
import hmac
import secrets

_ITER = 260_000
# bez znaków mylących się na ekranie i w czytniku (0/o, 1/l/i)
_PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def new_password() -> str:
    """12 znaków w trzech grupach, np. k7mp-2qax-9tde: łatwe do odczytania czytnikiem ekranu."""
    groups = ["".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(4)) for _ in range(3)]
    return "-".join(groups)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITER).hex()
    return f"pbkdf2_sha256${_ITER}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt, digest = stored.split("$")
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters)).hex()
    return hmac.compare_digest(check, digest)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)
