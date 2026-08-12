"""Turning what a person types into a number a telephony API will accept.

Recruiters type phone numbers the way they read them -- "98765 43210",
"098765-43210", "+91 98765 43210". Hunar needs strict E.164. Rather than push
that formatting burden onto the user, normalize here and let the UI accept
whatever is natural.
"""

from __future__ import annotations

import re

from app.config import settings


class InvalidPhoneNumber(ValueError):
    """The input could not be read as a phone number."""


_NON_DIGITS = re.compile(r"[^\d+]")

# Longest possible E.164 subscriber number is 15 digits.
MAX_DIGITS = 15
MIN_DIGITS = 7


def normalize_phone(raw: str, default_country_code: str | None = None) -> str:
    """Normalize a typed phone number to E.164 (`+<country><subscriber>`).

    Accepts, in order of preference:
      - already-E.164 input:            "+919876543210"
      - international prefix:           "00919876543210"
      - a national number with a trunk  "09876543210"
      - a bare national number:         "9876543210"

    The last two need a country code, which comes from `DEFAULT_COUNTRY_CODE`.
    """
    if raw is None:
        raise InvalidPhoneNumber("Enter a phone number.")

    original = str(raw).strip()
    cleaned = _NON_DIGITS.sub("", original)
    if not cleaned:
        if original:
            raise InvalidPhoneNumber(f"'{original}' doesn't look like a phone number.")
        raise InvalidPhoneNumber("Enter a phone number.")

    # A '+' is only meaningful at the start.
    plus = cleaned.startswith("+")
    digits = cleaned.replace("+", "")

    if not digits.isdigit():
        raise InvalidPhoneNumber("A phone number can only contain digits.")

    if not plus:
        if digits.startswith("00"):
            # International access code, e.g. 0091...
            digits = digits[2:]
            plus = True
        else:
            cc = (default_country_code or settings.default_country_code).lstrip("+")
            if not cc:
                raise InvalidPhoneNumber(
                    "Include the country code, for example +919876543210."
                )
            # A single leading 0 is a national trunk prefix and is dropped when
            # the number is written internationally.
            national = digits[1:] if digits.startswith("0") else digits
            # Already carries the country code but no '+' (e.g. 919876543210).
            digits = national if national.startswith(cc) else cc + national

    if len(digits) < MIN_DIGITS:
        raise InvalidPhoneNumber(f"'{raw}' is too short to be a phone number.")
    if len(digits) > MAX_DIGITS:
        raise InvalidPhoneNumber(f"'{raw}' is too long to be a phone number.")

    return f"+{digits}"
