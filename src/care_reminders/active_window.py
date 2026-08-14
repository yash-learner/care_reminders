"""Mirrors care_fe getMedicationActiveWindow / convertToHours."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

HOURS = {
    "h": Decimal("1"),
    "d": Decimal("24"),
    "wk": Decimal(24 * 7),
    "mo": Decimal(24 * 30),
    "a": Decimal(24 * 365),
}

INACTIVE_STATUSES = {
    "ended",
    "completed",
    "cancelled",
    "entered_in_error",
    "stopped",
}


def parse_datetime(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def hours_for(quantity: dict | None) -> Decimal:
    if not quantity:
        return Decimal("0")
    try:
        value = Decimal(str(quantity.get("value") or 0))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")
    unit = str(quantity.get("unit") or "")
    return value * HOURS.get(unit, Decimal("0"))


@dataclass(frozen=True)
class Window:
    start: datetime
    end: datetime | None


class ActiveWindow:
    def __init__(self, medication_payload: dict | None, *, now: datetime | None = None):
        self.payload = medication_payload or {}
        self.now = now or datetime.now(UTC)

    def call(self) -> Window:
        authored = parse_datetime(self.payload.get("authored_on")) or self.now
        instructions = self.payload.get("dosage_instruction") or []
        if not isinstance(instructions, list) or not instructions:
            instructions = [None]

        start_at: datetime | None = None
        end_at: datetime | None = None
        open_ended = False

        for instruction in instructions:
            repeat = {}
            if isinstance(instruction, dict):
                timing = instruction.get("timing") or {}
                if isinstance(timing, dict):
                    repeat = timing.get("repeat") or {}
            bounds = self._timing_bounds(repeat if isinstance(repeat, dict) else {})
            if bounds and bounds["type"] == "period" and bounds.get("start"):
                instruction_start = bounds["start"]
            else:
                instruction_start = authored
            start_at = instruction_start if start_at is None else min(start_at, instruction_start)

            instruction_end = None
            if bounds:
                if bounds["type"] == "period":
                    instruction_end = bounds.get("end")
                elif bounds["type"] == "duration":
                    instruction_end = instruction_start + timedelta(hours=float(hours_for(bounds["duration"])))
                elif bounds["type"] == "range":
                    instruction_end = instruction_start + timedelta(hours=float(hours_for(bounds["high"])))

            if instruction_end is None:
                open_ended = True
            else:
                end_at = instruction_end if end_at is None else max(end_at, instruction_end)

        start_at = start_at or authored
        final_end = None if open_ended else end_at

        status = str(self.payload.get("status") or "")
        if status in INACTIVE_STATUSES:
            stopped_at = parse_datetime(self.payload.get("modified_date"))
            if stopped_at:
                final_end = stopped_at if final_end is None else min(final_end, stopped_at)

        return Window(start=start_at, end=final_end)

    def _timing_bounds(self, repeat: dict) -> dict | None:
        if repeat.get("bounds_range"):
            return {"type": "range", "high": (repeat.get("bounds_range") or {}).get("high")}
        if repeat.get("bounds_period"):
            period = repeat.get("bounds_period") or {}
            return {
                "type": "period",
                "start": parse_datetime(period.get("start")),
                "end": parse_datetime(period.get("end")),
            }
        duration = repeat.get("bounds_duration") or {}
        if str(duration.get("value") or "") not in {"", "0"}:
            return {"type": "duration", "duration": duration}
        return None
