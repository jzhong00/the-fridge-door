"""The owner's commands: `python -m app.cli claim-account` and `set-password`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from api_client import api_client
from fastapi.testclient import TestClient

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


def _run(
    answers: list[str], secrets: list[str], command: str = "claim-account"
) -> tuple[int, list[str]]:
    said: list[str] = []
    code = cli.main(
        [command],
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


# --- set-password --------------------------------------------------------------

NEW_PASSWORD = "copper kettle meadow"


def _sign_up(browser: TestClient, email: str = EMAIL) -> None:
    """Sign this browser up to a new account, which gets one meal."""
    signup = browser.post(
        "/api/auth/signup", json={"email": email, "password": PASSWORD}
    )
    assert signup.is_success, signup.text
    browser.post("/api/meals", json={"name": "Shakshuka", "servings": 2})


def _account() -> None:
    with api_client(as_guest=False) as browser:
        _sign_up(browser)


def _logs_in(email: str, password: str) -> bool:
    with api_client(as_guest=False) as client:
        response = client.post(
            "/api/auth/login", json={"email": email, "password": password}
        )
        return response.status_code == 200


def _set_password(answers: list[str], secrets: list[str]) -> tuple[int, list[str]]:
    return _run(answers, secrets, command="set-password")


def test_a_new_password_replaces_the_old_one_and_keeps_the_data(db):
    _account()

    code, said = _set_password([EMAIL, "yes"], [NEW_PASSWORD, NEW_PASSWORD])

    assert code == 0
    assert said[-1].startswith("Done.")
    assert not _logs_in(EMAIL, PASSWORD)
    with api_client(as_guest=False) as client:
        client.post("/api/auth/login", json={"email": EMAIL, "password": NEW_PASSWORD})
        assert [m["name"] for m in client.get("/api/meals").json()] == ["Shakshuka"]


def test_a_new_password_signs_the_account_out_everywhere_and_no_one_else(db):
    with (
        api_client(as_guest=False) as my_browser,
        api_client(as_guest=False) as their_browser,
    ):
        _sign_up(my_browser)
        _sign_up(their_browser, "someone@example.com")

        code, said = _set_password([EMAIL.upper(), "yes"], [NEW_PASSWORD] * 2)

        assert code == 0
        assert "Ended 1 session." in said[-1]
        assert my_browser.get("/api/auth/me").status_code == 401
        assert their_browser.get("/api/auth/me").status_code == 200


def test_the_new_password_is_never_printed(db):
    _account()
    _, said = _set_password([EMAIL, "yes"], [NEW_PASSWORD, NEW_PASSWORD])
    assert NEW_PASSWORD not in "\n".join(said)


@pytest.mark.parametrize(
    ("answers", "secrets", "reason"),
    [
        ([EMAIL, "yes"], [NEW_PASSWORD, "something else"], "didn't match"),
        ([EMAIL, "no"], [NEW_PASSWORD, NEW_PASSWORD], "Nothing was changed"),
        ([EMAIL, "yes"], ["password1", "password1"], "most common"),
        ([EMAIL, "yes"], [EMAIL, EMAIL], "email"),
    ],
)
def test_anything_short_of_a_confirmed_valid_password_changes_nothing(
    db, answers, secrets, reason
):
    with api_client(as_guest=False) as browser:
        _sign_up(browser)

        code, said = _set_password(answers, secrets)

        assert code == 1
        assert reason in said[-1]
        assert browser.get("/api/auth/me").status_code == 200
    assert _logs_in(EMAIL, PASSWORD)


def test_an_email_with_no_account_is_said_so_before_any_password_is_asked(db):
    code, said = _set_password(["nobody@example.com"], [])
    assert code == 1
    assert "No account has the email nobody@example.com" in said[-1]


def test_only_an_account_with_a_login_can_be_given_a_password(db):
    with db.transaction() as session:
        guest = UserRepository(session).create(is_guest=True)
    with db.transaction() as session, pytest.raises(ValueError):
        AuthService(session, now=NOW).set_password(guest.id or 0, NEW_PASSWORD)
