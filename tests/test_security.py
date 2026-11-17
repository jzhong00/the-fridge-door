"""Password hashing, the password policy, and session tokens (app/security.py)."""

from __future__ import annotations

import base64
import hashlib
import string

import pytest
from argon2 import PasswordHasher, extract_parameters, profiles
from argon2.exceptions import InvalidHashError

from app import security
from app.exceptions import WeakPasswordError
from app.security import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    PASSWORD_PARAMETERS,
    check_password_policy,
    hash_password,
    hash_session_token,
    needs_rehash,
    new_session_token,
    verify_password,
)

PASSWORD = "correct horse battery staple"


# --- Hashing -----------------------------------------------------------------


def test_hash_is_argon2id_with_the_pinned_parameters() -> None:
    stored = hash_password(PASSWORD)

    assert stored.startswith("$argon2id$")
    assert extract_parameters(stored) == PASSWORD_PARAMETERS
    assert PASSWORD_PARAMETERS == profiles.RFC_9106_LOW_MEMORY


def test_the_stored_hash_never_contains_the_password() -> None:
    stored = hash_password(PASSWORD)

    assert PASSWORD not in stored
    assert "horse" not in stored


def test_each_hash_has_its_own_salt() -> None:
    # Two people with the same password must not have the same hash, or one
    # cracked hash cracks both, and a precomputed table works.
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_the_right_password_verifies() -> None:
    assert verify_password(hash_password(PASSWORD), PASSWORD) is True


@pytest.mark.parametrize(
    "attempt",
    [
        "correct horse battery stapler",
        "Correct horse battery staple",  # no case folding
        " correct horse battery staple",  # no trimming
        "correct horse battery staple ",
        "",
    ],
)
def test_anything_else_does_not(attempt: str) -> None:
    assert verify_password(hash_password(PASSWORD), attempt) is False


def test_the_same_password_typed_on_different_keyboards_matches() -> None:
    composed = "café au lait 2026"  # é as one code point
    decomposed = "café au lait 2026"  # e + combining acute accent
    assert composed != decomposed

    assert verify_password(hash_password(composed), decomposed) is True
    assert verify_password(hash_password(decomposed), composed) is True


# --- Unknown accounts take as long as wrong passwords ------------------------


def test_an_unknown_account_still_runs_a_full_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked: list[str] = []
    real_verify = security._verify

    def spy(stored_hash: str, candidate: str) -> bool:
        checked.append(stored_hash)
        return real_verify(stored_hash, candidate)

    monkeypatch.setattr(security, "_verify", spy)

    assert verify_password(None, PASSWORD) is False
    assert len(checked) == 1, "no account must still cost one argon2 verification"
    # Same cost as a real account's hash, so the timing matches too.
    assert extract_parameters(checked[0]) == PASSWORD_PARAMETERS


def test_an_unknown_account_never_matches_even_the_dummy_password() -> None:
    # Whatever the dummy hash was made from, None means no account: False.
    assert verify_password(None, "") is False
    assert verify_password(None, PASSWORD) is False


# --- Changing the parameters later -------------------------------------------


def test_hashes_made_with_older_parameters_still_verify_and_ask_for_a_rehash() -> None:
    older = PasswordHasher.from_parameters(profiles.CHEAPEST).hash(PASSWORD)

    assert verify_password(older, PASSWORD) is True
    assert needs_rehash(older) is True


def test_a_current_hash_does_not_ask_for_a_rehash() -> None:
    assert needs_rehash(hash_password(PASSWORD)) is False


def test_a_corrupt_stored_hash_fails_loudly() -> None:
    # Not a wrong password: corrupt data, which should surface as an error
    # rather than quietly locking the account forever.
    with pytest.raises(InvalidHashError):
        verify_password("not-an-argon2-hash", PASSWORD)


# --- Policy ------------------------------------------------------------------


@pytest.mark.parametrize(
    "password",
    [
        "tq9vmz4w",  # exactly the minimum
        "a" * MAX_PASSWORD_LENGTH,
        "spoonsfornorthwind",  # no digits or symbols: composition rules are absent
        "ぱすわーどですよ",  # length is counted in characters, not bytes
        "🥕🥔🧅🍅🌶🥦🍆🧄",
    ],
)
def test_passwords_within_the_length_limits_are_accepted(password: str) -> None:
    check_password_policy(password)


@pytest.mark.parametrize(
    ("password", "message"),
    [
        ("", f"at least {MIN_PASSWORD_LENGTH}"),
        ("a" * (MIN_PASSWORD_LENGTH - 1), f"at least {MIN_PASSWORD_LENGTH}"),
        ("a" * (MAX_PASSWORD_LENGTH + 1), f"at most {MAX_PASSWORD_LENGTH}"),
    ],
)
def test_passwords_outside_the_limits_are_refused_with_a_reason(
    password: str, message: str
) -> None:
    with pytest.raises(WeakPasswordError, match=message):
        check_password_policy(password)


def test_length_is_counted_after_normalisation() -> None:
    # Seven characters typed as fourteen code points (each é decomposed)
    # is still seven characters, and too short.
    seven_decomposed = "é" * (MIN_PASSWORD_LENGTH - 1)
    assert len(seven_decomposed) >= MIN_PASSWORD_LENGTH

    with pytest.raises(WeakPasswordError):
        check_password_policy(seven_decomposed)


# --- Session tokens ----------------------------------------------------------


def test_a_token_carries_256_bits_of_randomness_in_a_cookie_safe_form() -> None:
    token = new_session_token()

    assert set(token) <= set(string.ascii_letters + string.digits + "-_")
    raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    assert len(raw) == security.SESSION_TOKEN_BYTES == 32


def test_tokens_do_not_repeat() -> None:
    tokens = {new_session_token() for _ in range(1000)}
    assert len(tokens) == 1000


def test_the_token_hash_is_sha256_hex_and_stable() -> None:
    token = new_session_token()
    stored = hash_session_token(token)

    assert stored == hash_session_token(token)
    assert stored == hashlib.sha256(token.encode()).hexdigest()
    assert len(stored) == 64 and set(stored) <= set("0123456789abcdef")
    assert token not in stored


def test_the_token_hash_matches_a_published_sha256_vector() -> None:
    # FIPS 180-2's "abc" example: proves this is SHA-256 and not some
    # other digest of the same length.
    assert hash_session_token("abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


@pytest.mark.parametrize("cookie", ["", "x", "🍪" * 50, "a" * 10_000, "a\x00b"])
def test_any_cookie_a_client_sends_hashes_without_error(cookie: str) -> None:
    # A tampered or malformed cookie simply matches no session row.
    assert len(hash_session_token(cookie)) == 64


@pytest.mark.parametrize(
    "password", ["password", "Password1", "PASSWORD1", "iloveyou", "qwertyuiop"]
)
def test_the_most_common_passwords_are_refused_whatever_their_case(
    password: str,
) -> None:
    with pytest.raises(WeakPasswordError, match="most common"):
        check_password_policy(password)


def test_every_listed_password_passes_the_length_rule_so_the_list_is_not_dead_weight() -> (
    None
):
    from app.common_passwords import COMMON_PASSWORDS

    assert len(COMMON_PASSWORDS) == 10_000
    assert all(
        MIN_PASSWORD_LENGTH <= len(entry) <= MAX_PASSWORD_LENGTH
        for entry in COMMON_PASSWORDS
    )


@pytest.mark.parametrize("password", ["riley.cooks@example.com", "Riley.Cooks"])
def test_a_password_made_of_the_email_is_refused(password: str) -> None:
    with pytest.raises(WeakPasswordError, match="email"):
        check_password_policy(password, email="riley.cooks@example.com")


def test_a_password_merely_containing_a_common_word_is_fine() -> None:
    check_password_policy("password lettuce harbour", email="cook@example.com")
