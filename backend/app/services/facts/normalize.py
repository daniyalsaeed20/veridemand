"""Normalize raw evidence values without inventing replacements."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

_DATE_PATTERNS = (
    (re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$"), "%Y-%m-%d"),
    (re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$"), "%m/%d/%Y"),
    (re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$"), "%m-%d-%Y"),
    (re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$"), "%m.%d.%Y"),
)

_MONTH_NAME = re.compile(
    r"^(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+(\d{1,2}),?\s+(\d{4})$",
    re.I,
)

_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM|am|pm)?$")

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_PHONE_DIGITS = re.compile(r"\D+")
_CPT_RE = re.compile(r"^\d{5}$")
_ICD10_RE = re.compile(r"^[A-TV-Z][0-9][0-9A-Z](?:\.[0-9A-Z]{1,4})?$", re.I)
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_/\.]{1,48}$")


def normalize_date(raw: str) -> tuple[str | None, str | None]:
    """Return (YYYY-MM-DD, warning). Null normalized means review/reject."""
    text = raw.strip()
    if not text:
        return None, "empty_date"

    # Ambiguous day/month when both <= 12 and European-looking separator with day first cue
    mdy = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", text)
    if mdy:
        a, b, y = int(mdy.group(1)), int(mdy.group(2)), int(mdy.group(3))
        if a > 12 and b <= 12:
            # day/month/year European — do not silently swap without label
            return None, "ambiguous_day_month_order"
        if a <= 12 and b <= 12 and a != b:
            # Ambiguous US vs EU — keep as needs review unless we later have label
            try:
                dt = datetime(y, a, b)
                return dt.strftime("%Y-%m-%d"), "ambiguous_day_month_order"
            except ValueError:
                return None, "invalid_date"

    for pattern, fmt in _DATE_PATTERNS:
        if pattern.match(text):
            try:
                dt = datetime.strptime(text, fmt)
                return dt.strftime("%Y-%m-%d"), None
            except ValueError:
                return None, "invalid_date"

    m = _MONTH_NAME.match(text)
    if m:
        try:
            dt = datetime.strptime(f"{m.group(1)[:3]} {m.group(2)} {m.group(3)}", "%b %d %Y")
            return dt.strftime("%Y-%m-%d"), None
        except ValueError:
            return None, "invalid_date"

    return None, "unrecognized_date_format"


def normalize_time(raw: str) -> tuple[str | None, str | None]:
    text = raw.strip()
    m = _TIME_RE.match(text)
    if not m:
        return None, "invalid_time"
    hour = int(m.group(1))
    minute = int(m.group(2))
    ampm = m.group(4)
    if ampm:
        ampm_u = ampm.upper()
        if hour < 1 or hour > 12:
            return None, "invalid_time"
        if ampm_u == "PM" and hour != 12:
            hour += 12
        if ampm_u == "AM" and hour == 12:
            hour = 0
    elif hour > 23:
        return None, "invalid_time"
    if minute > 59:
        return None, "invalid_time"
    return f"{hour:02d}:{minute:02d}", None


def normalize_currency(raw: str) -> tuple[str | None, str | None]:
    text = raw.strip()
    if not text:
        return None, "empty_currency"
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    text = text.replace("$", "").replace(",", "").replace(" ", "")
    if text.startswith("-"):
        negative = True
        text = text[1:]
    if not re.match(r"^\d+(\.\d{1,2})?$", text):
        # OCR digit confusion — do not invent
        if re.search(r"[OIlS]", text):
            return None, "ocr_confused_digits"
        return None, "invalid_decimal"
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None, "invalid_decimal"
    if negative:
        value = -value
    return format(value, "f"), None


def normalize_phone(raw: str) -> tuple[str | None, str | None]:
    digits = _PHONE_DIGITS.sub("", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return None, "invalid_phone"
    return f"+1{digits}", None


def normalize_email(raw: str) -> tuple[str | None, str | None]:
    text = raw.strip()
    # Light OCR fix for spaces only — not inventing domain
    text = text.replace(" ", "")
    if not _EMAIL_RE.match(text):
        return None, "invalid_email"
    return text.lower(), None


def normalize_identifier(raw: str) -> tuple[str | None, str | None]:
    text = re.sub(r"\s+", "", raw.strip())
    if not text or not _ID_RE.match(text):
        return None, "invalid_identifier"
    return text.upper() if text.isalnum() else text, None


def normalize_cpt(raw: str) -> tuple[str | None, str | None]:
    text = re.sub(r"\s+", "", raw.strip())
    if not _CPT_RE.match(text):
        return None, "invalid_cpt"
    return text, None


def normalize_icd10(raw: str) -> tuple[str | None, str | None]:
    text = re.sub(r"\s+", "", raw.strip()).upper()
    if not _ICD10_RE.match(text):
        return None, "invalid_icd10"
    return text, None


def normalize_name(raw: str) -> tuple[str | None, str | None]:
    text = re.sub(r"\s+", " ", raw.strip())
    if len(text) < 2:
        return None, "invalid_name"
    # Reject obvious non-names
    if re.search(r"\d{3,}", text):
        return None, "name_looks_like_id"
    return text, None


def normalize_pronoun_set(raw: str) -> tuple[str | None, str | None]:
    text = raw.strip().lower()
    mapping = {
        "m": "he",
        "male": "he",
        "he": "he",
        "him": "he",
        "f": "she",
        "female": "she",
        "she": "she",
        "her": "she",
        "x": "they",
        "they": "they",
        "them": "they",
        "nonbinary": "they",
    }
    value = mapping.get(text)
    if value is None:
        return None, "invalid_pronoun"
    return value, None


def normalize_text(raw: str) -> tuple[str | None, str | None]:
    text = re.sub(r"\s+", " ", raw.strip())
    if not text:
        return None, "empty_text"
    return text, None


def normalize_candidate(value_kind: str, raw: str) -> tuple[str | None, str | None, str | None]:
    """Return (normalized, display, warning)."""
    kind = value_kind
    if kind == "date":
        norm, warn = normalize_date(raw)
        return norm, norm, warn
    if kind == "time":
        norm, warn = normalize_time(raw)
        return norm, norm, warn
    if kind == "money":
        norm, warn = normalize_currency(raw)
        display = (
            f"${norm}" if norm and not norm.startswith("-") else (f"-${norm[1:]}" if norm else None)
        )
        return norm, display, warn
    if kind == "phone":
        norm, warn = normalize_phone(raw)
        if norm and len(norm) == 12:
            d = norm[2:]
            display = f"({d[:3]}) {d[3:6]}-{d[6:]}"
        else:
            display = norm
        return norm, display, warn
    if kind == "email":
        norm, warn = normalize_email(raw)
        return norm, norm, warn
    if kind == "identifier":
        norm, warn = normalize_identifier(raw)
        return norm, norm, warn
    if kind == "cpt":
        norm, warn = normalize_cpt(raw)
        return norm, norm, warn
    if kind == "icd10":
        norm, warn = normalize_icd10(raw)
        return norm, norm, warn
    if kind == "name":
        norm, warn = normalize_name(raw)
        return norm, norm, warn
    if kind == "pronoun":
        norm, warn = normalize_pronoun_set(raw)
        return norm, norm, warn
    if kind == "text":
        norm, warn = normalize_text(raw)
        return norm, norm, warn
    return None, None, "unknown_value_kind"
