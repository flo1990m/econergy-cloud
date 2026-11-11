"""Validation helpers for Econergy weekly comfort periods."""
from __future__ import annotations

from datetime import time
from typing import Any


EMPTY_TIME = "00:00"
MAX_PERIODS_PER_DAY = 3


def format_time(value: time) -> str:
    """Format a Home Assistant time value as HH:MM."""
    return value.strftime("%H:%M")


def parse_time(value: str) -> int:
    """Return minutes since midnight; Econergy accepts ten-minute increments."""
    try:
        hour_text, minute_text = value.split(":", 1)
        hour, minute = int(hour_text), int(minute_text)
    except (AttributeError, TypeError, ValueError) as err:
        raise ValueError(f"Heure invalide : {value!r}.") from err

    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"Heure invalide : {value!r}.")
    if minute % 10:
        raise ValueError("Les horaires Econergy doivent être réglés par pas de 10 minutes.")
    return hour * 60 + minute


def validate_periods(periods: Any) -> list[dict[str, str]]:
    """Validate active periods and return the normalized API payload."""
    if not isinstance(periods, list):
        raise ValueError("Les créneaux doivent être une liste.")
    if len(periods) > MAX_PERIODS_PER_DAY:
        raise ValueError("Trois créneaux Confort maximum par jour.")

    normalized: list[dict[str, str]] = []
    previous_end = -1
    for index, period in enumerate(periods, start=1):
        if not isinstance(period, dict):
            raise ValueError(f"Créneau {index} invalide.")
        start = str(period.get("start") or "")
        end = str(period.get("end") or "")
        start_minutes = parse_time(start)
        end_minutes = parse_time(end)
        if end_minutes <= start_minutes:
            raise ValueError(f"Créneau {index} : l'heure de fin doit être après l'heure de début.")
        if start_minutes < previous_end:
            raise ValueError("Les créneaux doivent être dans l'ordre et ne pas se chevaucher.")
        previous_end = end_minutes
        normalized.append({"start": start, "end": end})
    return normalized


def periods_from_api(value: Any) -> list[dict[str, str]]:
    """Extract at most three valid-looking periods from an API day value."""
    if not isinstance(value, list):
        return []
    periods: list[dict[str, str]] = []
    for item in value[:MAX_PERIODS_PER_DAY]:
        if not isinstance(item, dict):
            continue
        start, end = item.get("start"), item.get("end")
        if isinstance(start, str) and isinstance(end, str):
            periods.append({"start": start, "end": end})
    return periods


def format_schedule(periods: Any) -> str:
    """Format API periods for the read-only weekly-program sensor."""
    if not isinstance(periods, list):
        return ""
    parts: list[str] = []
    for item in periods:
        if not isinstance(item, dict):
            continue
        start, end = item.get("start"), item.get("end")
        if isinstance(start, str) and isinstance(end, str):
            parts.append(f"{start}-{end}")
    return ",".join(parts)
