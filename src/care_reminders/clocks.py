"""Patient day-part clocks (all morning meds share one time)."""

from __future__ import annotations

from datetime import time

from care.emr.models.patient import Patient
from django.db import IntegrityError

from care_reminders.active_window import ActiveWindow
from care_reminders.models import CLOCK_PARTS, ReminderPatientClock, ReminderSchedule
from care_reminders.occurrence_generator import OccurrenceGenerator
from care_reminders.settings import plugin_settings

CLOCK_FIELDS = tuple(f"{part}_at" for part in CLOCK_PARTS)


def parse_clock(value) -> time:
    if isinstance(value, time):
        return time(value.hour, value.minute)
    text = str(value or "").strip()
    parts = text.split(":")
    if len(parts) < 2:
        raise ValueError("Use HH:MM.")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as error:
        raise ValueError("Use HH:MM.") from error
    if hour > 23 or minute > 59 or hour < 0 or minute < 0:
        raise ValueError("Use HH:MM.")
    return time(hour, minute)


def format_clock(value: time) -> str:
    return f"{value.hour:02d}:{value.minute:02d}"


def _default_time(day_part: str) -> time:
    clocks = plugin_settings.DAY_PART_TIMES
    raw = clocks.get(day_part) or clocks.get("morning") or "09:00"
    return parse_clock(raw)


def ensure_patient_clock(patient: Patient) -> ReminderPatientClock:
    existing = ReminderPatientClock.objects.filter(patient=patient, deleted=False).select_related("patient").first()
    if existing:
        return existing
    defaults = {
        "time_zone": plugin_settings.TIME_ZONE,
        "morning_at": _default_time("morning"),
        "noon_at": _default_time("noon"),
        "evening_at": _default_time("evening"),
        "night_at": _default_time("night"),
    }
    try:
        return ReminderPatientClock.objects.create(patient=patient, **defaults)
    except IntegrityError:
        return ReminderPatientClock.objects.get(patient=patient, deleted=False)


def serialize_clock(clock: ReminderPatientClock) -> dict:
    return {
        "patient_id": str(clock.patient.external_id),
        "patient_name": clock.patient.name,
        "time_zone": clock.time_zone,
        "morning_at": format_clock(clock.morning_at),
        "noon_at": format_clock(clock.noon_at),
        "evening_at": format_clock(clock.evening_at),
        "night_at": format_clock(clock.night_at),
    }


def time_of_day_for(day_part: str, clock: ReminderPatientClock | None = None) -> time:
    if clock is not None:
        return clock.time_for(day_part)
    return _default_time(day_part if day_part in CLOCK_PARTS else "morning")


def _window_for(schedule: ReminderSchedule, *, now):
    request = schedule.medication_request
    instructions = request.dosage_instruction or []
    return ActiveWindow(
        {
            "authored_on": request.authored_on,
            "modified_date": request.modified_date,
            "status": request.status,
            "dosage_instruction": instructions,
        },
        now=now,
    ).call()


def apply_patient_clocks(patient: Patient, day_parts: list[str], *, now=None) -> int:
    clock = ensure_patient_clock(patient)
    parts = [part for part in day_parts if part in CLOCK_PARTS]
    if not parts:
        return 0
    created = 0
    schedules = ReminderSchedule.objects.filter(
        patient=patient,
        day_part__in=parts,
        enabled=True,
        deleted=False,
    ).select_related("medication_request")
    for schedule in schedules:
        schedule.time_of_day = clock.time_for(schedule.day_part)
        schedule.save(update_fields=["time_of_day", "modified_date"])
        window = _window_for(schedule, now=now)
        created += len(
            OccurrenceGenerator(
                schedule,
                starts_on=window.start,
                ends_on=window.end,
                now=now,
            ).call()
        )
    return created
