"""Domain errors raised by the repositories.

Each carries a message written for the person using the app, so the UI can
surface `str(exc)` directly instead of translating error codes.
"""

from __future__ import annotations


class MealPlannerError(Exception):
    """Base class for every expected, user-facing failure."""


class DuplicateNameError(MealPlannerError):
    """A meal with that name (ignoring case) already exists."""


class MealNotFoundError(MealPlannerError):
    """The requested meal id doesn't exist."""


class UnitMismatchError(MealPlannerError):
    """An ingredient is already on the meal measured in a different unit."""


class IngredientNotOnMealError(MealPlannerError):
    """The meal exists, but that ingredient is not attached to it."""


class InvalidDayError(MealPlannerError):
    """A day was given that is not one of the seven weekdays."""


class WeakPasswordError(MealPlannerError):
    """A password chosen at signup is too short, too long or too common."""


# --- Accounts ----------------------------------------------------------------


class NotSignedInError(MealPlannerError):
    """No session cookie, or one for a session that has ended."""


class InvalidCredentialsError(MealPlannerError):
    """Login failed. Deliberately does not say whether the email exists."""


class InvalidEmailError(MealPlannerError):
    """A signup email that is not shaped like an address."""


class EmailTakenError(MealPlannerError):
    """Signup with an email that already has an account."""


class AlreadySignedUpError(MealPlannerError):
    """Signup while signed in to an account (rather than a guest)."""


class CrossSiteRequestError(MealPlannerError):
    """A state-changing request sent from another website."""
