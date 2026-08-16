"""Opt-in: schedules exist after sync, but the phone only rings after the patient arms."""

from __future__ import annotations

from care.emr.models.medication_request import MedicationRequest
from care.emr.models.patient import Patient

from care_reminders.clocks import (
    CLOCK_FIELDS,
    _window_for,
    apply_patient_clocks,
    ensure_patient_clock,
    parse_clock,
    time_of_day_for,
)
from care_reminders.models import CLOCK_PARTS, ReminderOccurrence, ReminderSchedule
from care_reminders.occurrence_generator import OccurrenceGenerator
from care_reminders.prescription_sync import sync_medication_request


def armed_medication_ids(patient_ids) -> list[str]:
    values = (
        ReminderSchedule.objects.filter(patient_id__in=patient_ids, enabled=True)
        .values_list("medication_request__external_id", flat=True)
        .distinct()
    )
    return [str(item) for item in values]


def update_patient_clock(patient: Patient, payload: dict):
    clock = ensure_patient_clock(patient)
    changed: list[str] = []
    for field in CLOCK_FIELDS:
        if field not in payload:
            continue
        value = parse_clock(payload[field])
        if getattr(clock, field) != value:
            setattr(clock, field, value)
            changed.append(field.removesuffix("_at"))
    if changed:
        clock.save()
        apply_patient_clocks(patient, changed)
    return clock, changed


def arm_medication_request(request: MedicationRequest, *, now=None) -> int:
    sync_medication_request(request, now=now)
    schedules = list(ReminderSchedule.objects.filter(medication_request=request).select_related("medication_request"))
    if not schedules:
        return 0
    clock = ensure_patient_clock(request.patient)
    created = 0
    for schedule in schedules:
        part = schedule.day_part if schedule.day_part in CLOCK_PARTS else "morning"
        schedule.enabled = True
        schedule.time_of_day = time_of_day_for(part, clock)
        schedule.save(update_fields=["enabled", "time_of_day", "modified_date"])
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


def disarm_medication_request(request: MedicationRequest) -> int:
    updated = ReminderSchedule.objects.filter(medication_request=request, enabled=True).update(enabled=False)
    ReminderOccurrence.objects.filter(medication_request=request, status="pending").delete()
    return updated


def disarm_patients(patient_ids) -> int:
    updated = ReminderSchedule.objects.filter(patient_id__in=patient_ids, enabled=True).update(enabled=False)
    ReminderOccurrence.objects.filter(patient_id__in=patient_ids, status="pending").delete()
    return updated
