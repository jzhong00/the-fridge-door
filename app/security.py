"""Password hashing and session tokens.

Pure functions: no database, no HTTP, no clock. The auth endpoints (Phase 1,
step 4) build on these, and everything that is easy to get subtly wrong
about credentials is decided and tested here, in one place.

Passwords and session tokens are hashed differently, on purpose:

- A **password** is low-entropy and chosen by a person, so a leaked hash can
  be attacked by guessing. It gets argon2id, a deliberately slow,
  memory-hard hash with a random salt per password.
- A **session token** is 256 bits from the OS's secure random generator, so
  there is nothing to guess. It gets plain SHA-256, which is fast enough to
  run on every request and deterministic, so the hash itself is the
  `sessions` primary key and a lookup is one index probe. Storing only the
  hash means a copy of the table cannot be replayed as live sessions.
"""

from __future__ import annotations

import hashlib
import secrets
import unicodedata
from functools import cache

from argon2 import PasswordHasher, profiles
from argon2.exceptions import VerifyMismatchError

from app.exceptions import WeakPasswordError

# --- Passwords ---------------------------------------------------------------

#: RFC 9106's recommended profile for memory-constrained hosts: argon2id,
#: 64 MiB, 3 passes, 4 lanes. It is argon2-cffi's default, named here so a
#: library upgrade cannot change it silently. About 40 ms on a laptop. When
#: this changes, existing hashes keep verifying and `needs_rehash` reports
#: them, so they are upgraded at the user's next login.
PASSWORD_PARAMETERS = profiles.RFC_9106_LOW_MEMORY

#: Length is the only rule. No "one uppercase, one symbol" rules, because
#: they push people towards predictable patterns (NIST SP 800-63B). The
#: minimum is OWASP ASVS's floor. The maximum is generous enough for any
#: passphrase or password manager and stops a megabyte "password" from
#: becoming a way to keep the server hashing.
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

_hasher = PasswordHasher.from_parameters(PASSWORD_PARAMETERS)


def _normalise(password: str) -> str:
    """NFKC, so the same password typed on two keyboards is the same password.

    "café" can arrive as one code point for "é" or as "e" plus a combining
    accent depending on the device. Without normalising, someone who signed
    up on a phone could not log in from a laptop. NIST SP 800-63B recommends
    this. Nothing else is changed: no trimming, no case folding.
    """
    return unicodedata.normalize("NFKC", password)


def check_password_policy(password: str) -> None:
    """Raise WeakPasswordError if the password is not acceptable for signup."""
    length = len(_normalise(password))
    if length < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(
            f"Use at least {MIN_PASSWORD_LENGTH} characters for your password."
        )
    if length > MAX_PASSWORD_LENGTH:
        raise WeakPasswordError(
            f"Use at most {MAX_PASSWORD_LENGTH} characters for your password."
        )


def hash_password(password: str) -> str:
    """The argon2id hash to store. It includes its own salt and parameters."""
    return _hasher.hash(_normalise(password))


def verify_password(stored_hash: str | None, password: str) -> bool:
    """Whether `password` matches `stored_hash`, taking the same time either way.

    Pass None when no account has the email being tried. The password is
    then checked against a dummy hash with the same parameters and the
    result discarded, so an unknown email costs exactly as long as a wrong
    password. Otherwise response time alone would say which emails have
    accounts, however carefully the error message is worded.

    A stored hash that is not a valid argon2 hash raises rather than
    returning False. That is corrupt data, and it should fail loudly instead
    of looking like a wrong password forever.
    """
    candidate = _normalise(password)
    if stored_hash is None:
        _verify(_dummy_hash(), candidate)
        return False
    return _verify(stored_hash, candidate)


def needs_rehash(stored_hash: str) -> bool:
    """Whether the hash was made with parameters other than the current ones."""
    return _hasher.check_needs_rehash(stored_hash)


def _verify(stored_hash: str, candidate: str) -> bool:
    try:
        return _hasher.verify(stored_hash, candidate)
    except VerifyMismatchError:
        return False


@cache
def _dummy_hash() -> str:
    # Made on first use, not at import: a serverless cold start should not
    # pay for a hash that most requests never need.
    return _hasher.hash(secrets.token_urlsafe(32))


# --- Session tokens ----------------------------------------------------------

#: 32 bytes = 256 bits of entropy, the same as the August plan's design and
#: far past guessing range.
SESSION_TOKEN_BYTES = 32


def new_session_token() -> str:
    """A fresh token for the cookie. Never stored; only its hash is."""
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def hash_session_token(token: str) -> str:
    """The `sessions.token_hash` for a cookie value: SHA-256, hex.

    Safe to call on anything a client sends: an unknown, malformed or
    tampered cookie just hashes to a value no row has. No comparison happens
    in Python, so there is no timing to equalise here; the database matches
    hashes, and timing there could reveal at most part of a hash, which is
    no help in forging a token.
    """
    return hashlib.sha256(token.encode()).hexdigest()
