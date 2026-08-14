"""Port of care_fe MEDICATION_REQUEST_TIMING_OPTIONS + MAN_FREQUENCY_PRESETS."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

MAN_SLOT_RE = re.compile(r"^\d+(?:/\d+)?$")
MAN_FULL_RE = re.compile(r"^\d+(?:/\d+)?(?:-\d+(?:/\d+)?){1,3}$")

PRESETS = {
    "1-0-1": {"label": "Twice a day", "timing_key": "BID", "parts": ["morning", "night"]},
    "1-1-1": {
        "label": "Thrice a day",
        "timing_key": "TID",
        "parts": ["morning", "noon", "night"],
    },
    "1-0-0": {"label": "Morning only", "timing_key": "AM", "parts": ["morning"]},
    "0-0-1": {"label": "Night only", "timing_key": "PM", "parts": ["night"]},
    "0-1-0": {"label": "Noon only", "timing_key": "NOON", "parts": ["noon"]},
    "1-1-0": {
        "label": "Morning & Noon",
        "timing_key": "BID_MORNING_NOON",
        "parts": ["morning", "noon"],
    },
    "0-1-1": {
        "label": "Noon & Night",
        "timing_key": "BID_NOON_NIGHT",
        "parts": ["noon", "night"],
    },
    "1-1-1-1": {
        "label": "Four times a day",
        "timing_key": "QID",
        "parts": ["morning", "noon", "evening", "night"],
    },
}

SLOT_PARTS_BY_COUNT = {
    2: ["morning", "night"],
    3: ["morning", "noon", "night"],
    4: ["morning", "noon", "evening", "night"],
}

BID_DISPLAY_PARTS = {
    "two times a day": ["morning", "night"],
    "morning and noon": ["morning", "noon"],
    "noon and night": ["noon", "night"],
}

CODE_PARTS = {
    "AM": ["morning"],
    "NOON": ["noon"],
    "PM": ["night"],
    "BED": ["night"],
    "HS": ["night"],
    "BID": ["morning", "night"],
    "TID": ["morning", "noon", "night"],
    "QID": ["morning", "noon", "evening", "night"],
    "QD": ["morning"],
    "AC": ["morning", "noon", "night"],
    "PC": ["morning", "noon", "night"],
}

INTERVAL_HOURS = {
    "Q1H": 1,
    "Q2H": 2,
    "Q3H": 3,
    "Q4H": 4,
    "Q6H": 6,
    "Q8H": 8,
    "Q12H": 12,
}


def is_man(value: str | None) -> bool:
    return bool(value and MAN_FULL_RE.match(value.strip()))


def eval_slot(slot: str | None) -> Decimal:
    if not slot:
        return Decimal("0")
    text = slot.strip()
    try:
        if "/" in text:
            numerator, denominator = (Decimal(part) for part in text.split("/", 1))
            if denominator == 0:
                return Decimal("0")
            return numerator / denominator
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def parts_for_man(man_string: str) -> list[str]:
    preset = PRESETS.get(man_string)
    if preset:
        return list(preset["parts"])
    slots = man_string.split("-")
    return list(SLOT_PARTS_BY_COUNT.get(len(slots), []))
