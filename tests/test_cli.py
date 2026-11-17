"""Claiming the pre-accounts data with `python -m app.cli claim-account`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from api_client import api_client

from app import cli
from app.auth import AuthService
from app.db import Database
from app.repositories import MealRepository, UserRepository

NOW = datetime(2026, 9, 1, tzinfo=UTC)
EMAIL = "riley@example.com"
PASSWORD = "lettuce harbour spoon"


def _owner(db: Database) -> int:
    """The unclaimed owner, as the accounts migration leaves it."""
    with db.transaction() as session:
        owner = UserRepository(session).create(is_guest=False)
        owner_id = owner.id or 0
        MealRepository(session, user_id=owner_id).add("Spaghetti Bolognese")
        MealRepository(session, user_id=owner_id).add("Tacos")
    return owner_id


def _run(answers: list[str], secrets: list[str]) -> tuple[int, list[str]]:
    said: list[str] = []
    code = cli.main(
        ["claim-account"],
        ask=lambda _prompt: answers.pop(0),
        ask_secret=lambda _prompt: secrets.pop(0),
        say=said.append,
        now=NOW,
    )
    return code, said


def _still_unclaimed(db: Database) -> bool:
    with db.transaction() as session:
        return len(UserRepository(session).unclaimed_owners()) == 1


def test_claiming_gives_the_old_data_a_login(db):
    _owner(db)

    code, said = _run([EMAIL, "yes"], [PASSWORD, PASSWORD])

    assert code == 0
    assert "holds 2 meals" in said[1]
    assert not _still_unclaimed(db)
    with api_client(as_guest=False) as client:
        login = client.post(
            "/api/auth/login", json={"email": EMAIL, "password": PASSWORD}
        )
        assert login.status_code == 200
        assert {m["name"] for m in client.get("/api/meals").json()} == {
            "Spaghetti Bolognese",
            "Tacos",
        }


def test_the_password_is_never_printed(db):
    _owner(db)
    _, said = _run([EMAIL, "yes"], [PASSWORD, PASSWORD])
    assert PASSWORD not in "\n".join(said)


@pytest.mark.parametrize(
    ("answers", "secrets", "reason"),
    [
        ([EMAIL, "yes"], [PASSWORD, "something else"], "didn't match"),
        ([EMAIL, "no"], [PASSWORD, PASSWORD], "Nothing was changed"),
        ([EMAIL, "yes"], ["password1", "password1"], "most common"),
        (["not-an-email", "yes"], [PASSWORD, PASSWORD], "email address"),
    ],
)
def test_anything_short_of_a_confirmed_valid_claim_changes_nothing(
    db, answers, secrets, reason
):
    _owner(db)
    code, said = _run(answers, secrets)

    assert code == 1
    assert reason in said[-1]
    assert _still_unclaimed(db)


def test_an_email_that_already_has_an_account_cannot_be_used(db):
    _owner(db)
    with api_client(as_guest=False) as client:
        client.post("/api/auth/signup", json={"email": EMAIL, "password": PASSWORD})

    code, said = _run([EMAIL, "yes"], [PASSWORD, PASSWORD])

    assert code == 1
    assert "already exists" in said[-1]
    assert _still_unclaimed(db)


def test_nothing_to_claim_is_not_an_error(db):
    code, said = _run([], [])
    assert code == 0
    assert "Nothing to do" in said[-1]


def test_two_unclaimed_accounts_are_refused_rather_than_guessed_between(db):
    _owner(db)
    _owner(db)
    code, said = _run([], [])
    assert code == 1
    assert "found 2" in said[-1]


def test_only_an_unclaimed_account_can_be_claimed(db):
    with db.transaction() as session:
        guest = UserRepository(session).create(is_guest=True)
    with db.transaction() as session, pytest.raises(ValueError):
        AuthService(session, now=NOW).claim(guest.id or 0, EMAIL, PASSWORD)
