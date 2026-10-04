import bcrypt

# PHP's password_hash() with PASSWORD_BCRYPT/PASSWORD_DEFAULT produces hashes
# prefixed "$2y$...". bcrypt itself doesn't distinguish "$2y$" from "$2b$" at
# verification time (that prefix distinction is a historical quirk from old
# crypt() implementations), so your existing PHP-hashed passwords in the DB
# keep working unchanged. New hashes created here use "$2b$", which PHP's
# password_verify() also accepts - safe in both directions during a staged
# migration.
#
# Uses the `bcrypt` package directly rather than passlib: passlib is
# effectively unmaintained and breaks on bcrypt>=4.1 (AttributeError:
# module 'bcrypt' has no attribute '__about__').

_BCRYPT_MAX_BYTES = 72


def _prepare(password: str) -> bytes:
    # bcrypt only uses the first 72 bytes of a password - the same limit
    # PHP's password_hash()/password_verify() silently apply. Truncate
    # explicitly so a long password gets truncated (matching old PHP
    # behavior) instead of bcrypt raising a ValueError.
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plain_password: str) -> str:
    hashed = bcrypt.hashpw(_prepare(plain_password), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(plain_password), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed/unrecognized hash in the DB - treat as no match rather
        # than raising 500s on login attempts.
        return False
