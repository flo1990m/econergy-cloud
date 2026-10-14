"""Compute the indicated target temperature from Econergy schedule data.

Pure logic, no write to Econergy. Local day 1=Monday, 7=Sunday;
start/end are minute counts since midnight and end is exclusive.
"""
from __future__ import annotations
from datetime import datetime


def _float_or_none(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def effective_target_temperature(config: dict, now: datetime) -> float | None:
    """Return displayed setpoint, not an independently measured thermostat target."""
    if not isinstance(config, dict):
        return None
    mode = config.get("mode")
    if mode == 0:  # off: no active setpoint
        return None
    if mode == 1:  # frost protection in Econergy application
        return 7.0
    if mode == 3:  # manual
        return _float_or_none(config.get("setPoint"))
    if mode != 4:
        return None
    # Invalid/incomplete schedule: don't fabricate Eco/Confort transition.
    programs = config.get("programs")
    if not isinstance(programs, list) or len(programs) != 21:
        return None
    minute = now.hour * 60 + now.minute
    day = now.isoweekday()
    for program in programs:
        if not isinstance(program, dict) or program.get("isActive") is not True:
            continue
        if program.get("day") != day:
            continue
        start, end = program.get("startTime"), program.get("endTime")
        if (isinstance(start, int) and not isinstance(start, bool)
                and isinstance(end, int) and not isinstance(end, bool)
                and 0 <= start < end <= 1440 and start <= minute < end):
            return _float_or_none(config.get("comfort"))
    return _float_or_none(config.get("eco"))
