"""Rebuild schedules + occurrences from live CARE MedicationRequest rows."""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal, InvalidOperation

from care.emr.models.medication_request import MedicationRequest
from care.emr.models.patient import Patient
from django.utils import timezone

from care_reminders.active_window import INACTIVE_STATUSES, ActiveWindow
from care_reminders.dosage_parser import DosageParser
from care_reminders.models import ReminderSchedule
from care_reminders.occurrence_generator import OccurrenceGenerator
from care_reminders.settings import plugin_settings


def _decimal(value, default=Decimal("1")) -> Decimal:
    if value is None or value == "":
        return default
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default
    return parsed if parsed > 0 else default


def _parse_clock(value: str) -> time:
    hour, minute, *rest = (int(part) for part in value.split(":"))
    second = rest[0] if rest else 0
    return time(hour, minute, second)


def medication_name(request: MedicationRequest) -> str:
    medication = request.medication or {}
    if isinstance(medication, dict) and medication.get("display"):
        return str(medication["display"])
    product = getattr(request, "requested_product", None)
    if product is not None and getattr(product, "name", None):
        return product.name
    return "Unnamed medicine"


def dose_quantity_and_unit(instruction: dict) -> tuple[Decimal, str]:
    dose_and_rate = instruction.get("dose_and_rate") or {}
    quantity = dose_and_rate.get("dose_quantity") or {}
    unit = quantity.get("unit") or {}
    unit_label = ""
    if isinstance(unit, dict):
        unit_label = str(unit.get("display") or unit.get("code") or "")
    return _decimal(quantity.get("value"), Decimal("1")), unit_label


def time_of_day_for(day_part: str) -> time | None:
    clocks = plugin_settings.DAY_PART_TIMES
    if day_part in clocks:
        return _parse_clock(clocks[day_part])
    return _parse_clock(clocks.get("morning", "09:00"))


def is_schedulable(request: MedicationRequest, parsed) -> bool:
    if request.do_not_perform:
        return False
    if str(request.status or "") in INACTIVE_STATUSES:
        return False
    if parsed.as_needed:
        return False
    return bool(parsed.slots)


def sync_medication_request(request: MedicationRequest, *, now=None) -> int:
    now = now or timezone.now()
    instructions = request.dosage_instruction or []
    instruction = instructions[0] if instructions else {}
    if not isinstance(instruction, dict):
        instruction = {}
    dose_value, dose_unit = dose_quantity_and_unit(instruction)
    parsed = DosageParser(instruction, dose_quantity=dose_value).parse()
    window = ActiveWindow(
        {
            "authored_on": request.authored_on,
            "modified_date": request.modified_date,
            "status": request.status,
            "dosage_instruction": instructions,
        },
        now=now,
    ).call()

    enabled = is_schedulable(request, parsed)
    name = medication_name(request)
    keep_ids: list[int] = []
    created = 0

    for slot in parsed.slots:
        schedule, _ = ReminderSchedule.objects.update_or_create(
            medication_request=request,
            day_part=slot.day_part,
            slot_index=slot.slot_index,
            defaults={
                "patient": request.patient,
                "medication_name": name,
                "dose_amount": slot.dose_amount,
                "dose_unit": dose_unit,
                "frequency_text": parsed.frequency_text or "",
                "time_of_day": time_of_day_for(slot.day_part)
                if slot.day_part in {"morning", "noon", "evening", "night"}
                else time_of_day_for("morning"),
                "interval_hours": slot.interval_hours,
                "enabled": enabled,
                "channel": "alarm",
                "deleted": False,
            },
        )
        keep_ids.append(schedule.id)
        if enabled:
            created += len(
                OccurrenceGenerator(
                    schedule,
                    starts_on=window.start,
                    ends_on=window.end,
                    now=now,
                ).call()
            )
        else:
            schedule.occurrences.filter(status="pending").delete()

    ReminderSchedule.objects.filter(medication_request=request).exclude(id__in=keep_ids).delete()
    return created


def sync_phone_number(phone_number: str, *, now: datetime | None = None) -> dict:
    patients = Patient.objects.filter(phone_number=phone_number)
    requests = MedicationRequest.objects.filter(patient__in=patients).select_related("patient", "requested_product")
    occurrence_count = 0
    for request in requests:
        occurrence_count += sync_medication_request(request, now=now)
    return {
        "ok": True,
        "patients": patients.count(),
        "medication_requests": requests.count(),
        "occurrences_created": occurrence_count,
    }
