"""Parse CARE FHIR dosage_instruction into day-part / interval slots."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from care_reminders import timing as timing_map


def _as_decimal(value, default: Decimal = Decimal("0")) -> Decimal:
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _humanize(part: str) -> str:
    return part.replace("_", " ").capitalize()


@dataclass(frozen=True)
class Slot:
    kind: str
    day_part: str
    slot_index: int
    dose_amount: Decimal
    interval_hours: int | None
    label: str


@dataclass(frozen=True)
class ParseResult:
    as_needed: bool
    frequency_text: str | None
    timing_code: str | None
    timing_display: str | None
    label: str
    slots: list[Slot]


class DosageParser:
    def __init__(self, instruction: dict | None, dose_quantity=1):
        self.instruction = instruction or {}
        quantity = _as_decimal(dose_quantity, Decimal("1"))
        self.dose_quantity = quantity if quantity > 0 else Decimal("1")

    def parse(self) -> ParseResult:
        if self._as_needed():
            return self._prn_result()

        text = str(self.instruction.get("text") or "").strip()
        code = self._timing_code()
        display = self._timing_display()

        if text.upper() == "SOS":
            return self._prn_result()

        if text.upper() == "STAT" or code == "STAT":
            return self._result_for(
                kind="stat",
                parts=["stat"],
                text=text or "STAT",
                code="STAT",
                display=display or "Immediately",
            )

        if timing_map.is_man(text):
            return self._parse_man(text, code=code, display=display)

        if code in timing_map.INTERVAL_HOURS:
            return self._interval_result(timing_map.INTERVAL_HOURS[code], text=text, code=code, display=display)

        if code == "WK":
            return self._special_result("weekly", text=text, code=code, display=display or "Weekly")
        if code == "MO":
            return self._special_result("monthly", text=text, code=code, display=display or "Monthly")
        if code == "QOD":
            return self._special_result(
                "alternate_day",
                text=text,
                code=code,
                display=display or "Alternate days",
            )

        parts = self._parts_from_code(code, display)
        if parts:
            return self._result_for(kind="daily", parts=parts, text=text, code=code, display=display)

        parts = self._parts_from_frequency()
        if parts:
            inferred = text or f"{len(parts)}x daily"
            return self._result_for(kind="daily", parts=parts, text=inferred, code=code, display=display)

        return ParseResult(
            as_needed=False,
            frequency_text=text or None,
            timing_code=code,
            timing_display=display,
            label=display or text or "Unscheduled",
            slots=[],
        )

    def _as_needed(self) -> bool:
        return _truthy(self.instruction.get("as_needed_boolean"))

    def _timing(self) -> dict:
        timing = self.instruction.get("timing") or {}
        return timing if isinstance(timing, dict) else {}

    def _timing_code(self) -> str | None:
        code = (self._timing().get("code") or {}).get("code")
        return str(code).strip() if code else None

    def _timing_display(self) -> str | None:
        display = (self._timing().get("code") or {}).get("display")
        return str(display).strip() if display else None

    def _repeat(self) -> dict:
        repeat = self._timing().get("repeat") or {}
        return repeat if isinstance(repeat, dict) else {}

    def _prn_result(self) -> ParseResult:
        return ParseResult(
            as_needed=True,
            frequency_text="SOS",
            timing_code=None,
            timing_display=None,
            label="SOS (as needed)",
            slots=[],
        )

    def _parse_man(self, text: str, code: str | None, display: str | None) -> ParseResult:
        preset = timing_map.PRESETS.get(text)
        slot_values = [timing_map.eval_slot(slot) for slot in text.split("-")]
        parts = timing_map.SLOT_PARTS_BY_COUNT.get(len(slot_values), [])
        built: list[Slot] = []
        for index, part in enumerate(parts):
            amount = slot_values[index]
            if amount <= 0:
                continue
            built.append(
                Slot(
                    kind="daily",
                    day_part=part,
                    slot_index=index,
                    dose_amount=amount * self.dose_quantity,
                    interval_hours=None,
                    label=_humanize(part),
                )
            )
        return ParseResult(
            as_needed=False,
            frequency_text=text,
            timing_code=code or (preset["timing_key"] if preset else None),
            timing_display=display or (preset["label"] if preset else None),
            label=f"{text} ({preset['label']})" if preset else text,
            slots=built,
        )

    def _result_for(
        self,
        *,
        kind: str,
        parts: list[str],
        text: str | None,
        code: str | None,
        display: str | None,
    ) -> ParseResult:
        slots = [
            Slot(
                kind=kind,
                day_part=part,
                slot_index=index,
                dose_amount=self.dose_quantity,
                interval_hours=None,
                label=_humanize(part),
            )
            for index, part in enumerate(parts)
        ]
        return ParseResult(
            as_needed=False,
            frequency_text=text or None,
            timing_code=code,
            timing_display=display,
            label=display or text or ", ".join(_humanize(part) for part in parts),
            slots=slots,
        )

    def _interval_result(self, hours: int, *, text: str | None, code: str | None, display: str | None) -> ParseResult:
        return ParseResult(
            as_needed=False,
            frequency_text=text or code,
            timing_code=code,
            timing_display=display,
            label=display or f"Every {hours} hour{'s' if hours != 1 else ''}",
            slots=[
                Slot(
                    kind="interval",
                    day_part="interval",
                    slot_index=0,
                    dose_amount=self.dose_quantity,
                    interval_hours=hours,
                    label=f"Every {hours}h",
                )
            ],
        )

    def _special_result(self, kind: str, *, text: str | None, code: str | None, display: str | None) -> ParseResult:
        return ParseResult(
            as_needed=False,
            frequency_text=text or code,
            timing_code=code,
            timing_display=display,
            label=display or kind,
            slots=[
                Slot(
                    kind=kind,
                    day_part=kind,
                    slot_index=0,
                    dose_amount=self.dose_quantity,
                    interval_hours=None,
                    label=display or _humanize(kind),
                )
            ],
        )

    def _parts_from_code(self, code: str | None, display: str | None) -> list[str] | None:
        if code == "BID":
            mapped = timing_map.BID_DISPLAY_PARTS.get((display or "").lower())
            if mapped:
                return mapped
        if code:
            return timing_map.CODE_PARTS.get(code)
        return None

    def _parts_from_frequency(self) -> list[str] | None:
        repeat = self._repeat()
        if str(repeat.get("period_unit") or "") != "d":
            return None
        if _as_decimal(repeat.get("period")) != Decimal("1"):
            return None
        try:
            frequency = int(repeat.get("frequency") or 0)
        except (TypeError, ValueError):
            return None
        return {
            1: ["morning"],
            2: ["morning", "night"],
            3: ["morning", "noon", "night"],
            4: ["morning", "noon", "evening", "night"],
        }.get(frequency)
