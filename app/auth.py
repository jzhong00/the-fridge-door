"""Accounts and sessions: guests, signup, login, logout, and who is asking.

No HTTP here. The routes in server/routers/auth.py move tokens in and out
of cookies; everything that decides who someone is lives in this module,
with the clock passed in so expiry and refresh can be tested exactly.

The rules, and why:

- **A session is a random token in a cookie**, stored only as its SHA-256
  (app/security.py). Database sessions rather than signed tokens, so a
  session can actually be revoked: logout deletes the row.
- **The token changes whenever who you are changes**: at login, and when a
  guest signs up. Otherwise a token captured before signup (on a shared
  computer, say) would carry into the new account. This is the defence
  against session fixation.
- **Sessions expire after 30 days without a visit.** A visit pushes the
  expiry back, but at most once an hour, so ordinary reads are not writes.
- **Login never says which half was wrong**, and costs the same time either
  way (`verify_password`), so it cannot be used to discover who has an
  account. Signup, unavoidably, says an email is taken; how often one
  network may hear that is limited, and it is the trade-off every signup
  form makes until email verification exists (Phase 2).
- **Guessing is throttled** (app/ratelimit.py): per account and network,
  with a higher ceiling per account. While throttled, even the right
  password is refused, without being checked.
- **Each of these is a security event** (app/events.py).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlmodel import Session

from app import events
from app.db import act_as
from app.exceptions import (
    AlreadySignedUpError,
    EmailTakenError,
    InvalidCredentialsError,
    InvalidEmailError,
    NotSignedInError,
    TooManyAttemptsError,
)
from app.models import User, persisted_id
from app.ratelimit import (
    GUESTS_PER_NETWORK,
    LOGIN_PER_ACCOUNT,
    LOGIN_PER_ACCOUNT_AND_NETWORK,
    TAKEN_EMAILS_PER_NETWORK,
    RateLimiter,
    Rule,
    network_of,
    subject,
)
from app.repositories import SessionRepository, UserRepository
from app.samples import add_samples
from app.security import (
    check_password_policy,
    hash_password,
    hash_session_token,
    needs_rehash,
    new_session_token,
    verify_password,
)

#: How long a session survives without a visit.
SESSION_LIFETIME = timedelta(days=30)
#: How stale an expiry may get before a visit pushes it back. Without this,
#: every request, reads included, would write to the sessions table.
REFRESH_INTERVAL = timedelta(hours=1)

MAX_EMAIL_LENGTH = 254


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """Who a request is from, as established from its session cookie."""

    id: int
    email: str | None
    is_guest: bool
    #: Identifies the session itself, so logout and token rotation can end it.
    token_hash: str


@dataclass(frozen=True, slots=True)
class SignedIn:
    """The result of starting a session: the account, and the new token the
    caller must put in the cookie. The token exists nowhere else."""

    user: CurrentUser
    token: str


def normalise_email(raw: str) -> str:
    """Trimmed, lower-cased, and checked to be shaped like an address.

    Deliberately loose: the only real test of an address is sending to it
    (email verification, Phase 2). This catches typos such as a missing @,
    not unusual but valid addresses.
    """
    email = raw.strip().lower()
    local, at, domain = email.rpartition("@")
    if (
        not at
        or not local
        or len(email) > MAX_EMAIL_LENGTH
        or "." not in domain
        or domain.startswith(".")
        or domain.endswith(".")
        or any(character.isspace() for character in email)
    ):
        raise InvalidEmailError("Enter an email address like name@example.com.")
    return email


class AuthService:
    """Account operations within one transaction, at one moment in time,
    for a request from one network (its IP address, or "unknown")."""

    def __init__(
        self, session: Session, *, now: datetime, address: str = "unknown"
    ) -> None:
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        self._session = session
        self._users = UserRepository(session)
        self._sessions = SessionRepository(session)
        self._limits = RateLimiter(session, now=now)
        self._now = now
        self._network = network_of(address)

    # --- Who is asking ------------------------------------------------------

    def authenticate(self, token: str | None) -> CurrentUser:
        """The user a session cookie belongs to. Raises NotSignedInError.

        A missing, unknown, tampered or expired token all look the same to
        the caller: not signed in.
        """
        if not token:
            raise NotSignedInError("Sign in, or continue as a guest, to do that.")
        token_hash = hash_session_token(token)
        found = self._sessions.find_live(token_hash, self._now)
        if found is None:
            raise NotSignedInError(
                "Your session has ended. Sign in again, or continue as a guest."
            )
        row, user = found

        if _as_utc(row.expires_at) - self._now < SESSION_LIFETIME - REFRESH_INTERVAL:
            self._sessions.extend(token_hash, self._now + SESSION_LIFETIME)
            self._users.touch(persisted_id(user), self._now)

        return _current(user, token_hash)

    # --- Starting and ending sessions ---------------------------------------

    def start_guest(self, sample_week: date | None = None) -> SignedIn:
        """A new account with no credentials, and a session for it.

        With `sample_week`, the account starts with sample meals planned in
        that week (app/samples.py), so the first screen has something on it.
        """
        network = subject("network", self._network)
        self._refuse_if_throttled(
            GUESTS_PER_NETWORK,
            network,
            "Too many new sessions have started from your network. "
            "Try again in {wait}.",
        )
        user = self._users.create(is_guest=True)
        self._limits.record(GUESTS_PER_NETWORK, network)
        if sample_week is not None:
            # From here the transaction acts as the new guest, so the
            # samples are written through row-level security like any other
            # of their writes.
            act_as(self._session, persisted_id(user))
            add_samples(self._session, persisted_id(user), sample_week)
        events.record("guest_started", user_id=persisted_id(user))
        return self._start_session(user)

    def sign_up(
        self, current: CurrentUser | None, email: str, password: str
    ) -> SignedIn:
        """Create an account, or turn the caller's guest account into one.

        A guest keeps the same row, so every meal and plan they made comes
        with them; only the session token changes.
        """
        if current is not None and not current.is_guest:
            raise AlreadySignedUpError(
                "You're already signed in to an account. Log out to create another."
            )
        network = subject("network", self._network)
        self._refuse_if_throttled(
            TAKEN_EMAILS_PER_NETWORK,
            network,
            "Too many signup attempts from your network. Try again in {wait}.",
        )
        email = normalise_email(email)
        check_password_policy(password, email=email)
        if self._users.find_by_email(email) is not None:
            # Keeps writes: the only thing written so far is this record
            # (and perhaps a session refresh), which must outlive the error.
            self._limits.record(TAKEN_EMAILS_PER_NETWORK, network)
            events.record("signup_email_taken", subject=network)
            raise EmailTakenError(
                "An account with that email already exists. Log in instead."
            )

        password_hash = hash_password(password)
        if current is None:
            user = self._users.create_account(email, password_hash)
            outcome = "account_created"
        else:
            user = self._users.get(current.id)
            if user is None:  # pragma: no cover - authenticate just found it
                raise NotSignedInError("Your session has ended.")
            self._users.set_credentials(user, email, password_hash)
            self._sessions.delete(current.token_hash)
            outcome = "guest_upgraded"
        events.record("signed_up", user_id=persisted_id(user), outcome=outcome)
        return self._start_session(user)

    def log_in(
        self, current: CurrentUser | None, email: str, password: str
    ) -> SignedIn:
        """Start a session for the account with these credentials.

        Raises InvalidCredentialsError, with the same message and the same
        cost whether the email is unknown or the password is wrong, and
        TooManyAttemptsError while throttled. Throttling is keyed on the
        email as typed, account or not, so it reveals nothing either.
        """
        email_key = email.strip().lower()
        per_network = subject("login", email_key, self._network)
        per_account = subject("login", email_key)
        for rule, key in (
            (LOGIN_PER_ACCOUNT_AND_NETWORK, per_network),
            (LOGIN_PER_ACCOUNT, per_account),
        ):
            self._refuse_if_throttled(
                rule, key, "Too many failed attempts. Try again in {wait}."
            )

        user = self._users.find_by_email(email_key)
        stored_hash = user.password_hash if user is not None else None
        if not verify_password(stored_hash, password) or user is None:
            # Keeps writes: nothing but these records (and perhaps a session
            # refresh) has been written, and they must outlive the error.
            for rule, key in (
                (LOGIN_PER_ACCOUNT_AND_NETWORK, per_network),
                (LOGIN_PER_ACCOUNT, per_account),
            ):
                bucket = self._limits.record(rule, key)
                if bucket.blocked_until is not None:
                    events.record(
                        "login_throttle_started",
                        rule=rule.scope,
                        subject=key,
                        retry_after_seconds=_seconds(bucket.blocked_until - self._now),
                    )
            events.record(
                "login_failed",
                user_id=persisted_id(user) if user is not None else None,
                subject=per_account,
            )
            raise InvalidCredentialsError(
                "That email and password don't match an account."
            )

        # Hashes made under older parameters are upgraded now, the one time
        # the password is in hand.
        if stored_hash is not None and needs_rehash(stored_hash):
            self._users.set_password_hash(user, hash_password(password))

        # Proof of the password ends the throttling for this account.
        self._limits.clear(LOGIN_PER_ACCOUNT_AND_NETWORK, per_network)
        self._limits.clear(LOGIN_PER_ACCOUNT, per_account)

        # A new token, never the one presented: this is where session
        # fixation is stopped. A guest who logs in leaves their guest data
        # behind, to be cleaned up with the guest.
        if current is not None:
            self._sessions.delete(current.token_hash)
        events.record("logged_in", user_id=persisted_id(user))
        return self._start_session(user)

    def log_out(self, current: CurrentUser) -> None:
        self._sessions.delete(current.token_hash)
        events.record("logged_out", user_id=current.id)

    # --- Helpers ---------------------------------------------------------------

    def _refuse_if_throttled(self, rule: Rule, key: str, message: str) -> None:
        wait = self._limits.wait_remaining(rule, key)
        if wait is None:
            return
        events.record(
            "throttled",
            rule=rule.scope,
            subject=key,
            retry_after_seconds=_seconds(wait),
        )
        raise TooManyAttemptsError(
            message.format(wait=_describe(wait)), retry_after=wait
        )

    def _start_session(self, user: User) -> SignedIn:
        token = new_session_token()
        token_hash = hash_session_token(token)
        user_id = persisted_id(user)
        self._sessions.create(token_hash, user_id, self._now + SESSION_LIFETIME)
        self._users.touch(user_id, self._now)
        return SignedIn(user=_current(user, token_hash), token=token)


def _current(user: User, token_hash: str) -> CurrentUser:
    return CurrentUser(
        id=persisted_id(user),
        email=user.email,
        is_guest=user.is_guest,
        token_hash=token_hash,
    )


def _seconds(wait: timedelta) -> int:
    return max(1, math.ceil(wait.total_seconds()))


def _describe(wait: timedelta) -> str:
    """'45 seconds', '1 minute', '15 minutes': rounded up, never 'now'."""
    seconds = _seconds(wait)
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    minutes = math.ceil(seconds / 60)
    return f"{minutes} minute{'s' if minutes != 1 else ''}"


def _as_utc(moment: datetime) -> datetime:
    """SQLite hands timestamps back without a zone; they were stored as UTC."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
