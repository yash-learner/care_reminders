from decimal import Decimal, InvalidOperation

from care.utils.models.base import BaseModel
from django.db import models

DAY_PARTS = (
    "morning",
    "noon",
    "evening",
    "night",
    "interval",
    "stat",
    "weekly",
    "monthly",
    "alternate_day",
)

CHANNELS = ("alarm", "push", "call", "sms", "whatsapp", "visit")

OCCURRENCE_STATUSES = ("pending", "sent", "taken", "skipped", "missed")


def format_dose(value) -> str:
    if value is None:
        return ""
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)
    if number == number.to_integral_value():
        return str(int(number))
    return format(number.normalize(), "f")


class ReminderSchedule(BaseModel):
    patient = models.ForeignKey(
        "emr.Patient",
        on_delete=models.CASCADE,
        related_name="care_reminder_schedules",
    )
    medication_request = models.ForeignKey(
        "emr.MedicationRequest",
        on_delete=models.CASCADE,
        related_name="care_reminder_schedules",
    )
    medication_name = models.CharField(max_length=255)
    day_part = models.CharField(max_length=32, choices=[(part, part) for part in DAY_PARTS])
    slot_index = models.PositiveSmallIntegerField(default=0)
    dose_amount = models.DecimalField(max_digits=20, decimal_places=6, default=1)
    dose_unit = models.CharField(max_length=64, blank=True, default="")
    frequency_text = models.CharField(max_length=64, blank=True, default="")
    time_of_day = models.TimeField(null=True, blank=True)
    interval_hours = models.PositiveSmallIntegerField(null=True, blank=True)
    enabled = models.BooleanField(default=True)
    channel = models.CharField(max_length=16, choices=[(item, item) for item in CHANNELS], default="alarm")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["medication_request", "day_part", "slot_index"],
                condition=models.Q(deleted=False),
                name="cr_rs_slot_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["patient", "enabled"], name="cr_rs_patient_en_idx"),
        ]

    def label(self) -> str:
        return self.day_part.replace("_", " ").capitalize()

    def dose_label(self) -> str:
        amount = format_dose(self.dose_amount)
        return " ".join(part for part in (amount, self.dose_unit) if part).strip()


class ReminderOccurrence(BaseModel):
    reminder_schedule = models.ForeignKey(
        ReminderSchedule,
        on_delete=models.CASCADE,
        related_name="occurrences",
    )
    patient = models.ForeignKey(
        "emr.Patient",
        on_delete=models.CASCADE,
        related_name="care_reminder_occurrences",
    )
    medication_request = models.ForeignKey(
        "emr.MedicationRequest",
        on_delete=models.CASCADE,
        related_name="care_reminder_occurrences",
    )
    medication_name = models.CharField(max_length=255)
    scheduled_at = models.DateTimeField()
    status = models.CharField(
        max_length=16,
        choices=[(item, item) for item in OCCURRENCE_STATUSES],
        default="pending",
    )
    notified_at = models.DateTimeField(null=True, blank=True)
    taken_at = models.DateTimeField(null=True, blank=True)
    channel = models.CharField(max_length=16, choices=[(item, item) for item in CHANNELS], default="alarm")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["reminder_schedule", "scheduled_at"],
                condition=models.Q(deleted=False),
                name="cr_ro_time_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["status", "scheduled_at"], name="cr_ro_status_at_idx"),
            models.Index(fields=["patient", "scheduled_at"], name="cr_ro_patient_at_idx"),
        ]

    def title(self) -> str:
        return f"Time to take {self.medication_name}"

    def body(self) -> str:
        schedule = self.reminder_schedule
        parts = []
        if schedule.dose_amount is not None:
            parts.append(schedule.dose_label())
        parts.append(schedule.label())
        if schedule.frequency_text:
            parts.append(schedule.frequency_text)
        return " · ".join(part for part in parts if part)


class NotificationDelivery(BaseModel):
    reminder_occurrence = models.ForeignKey(
        ReminderOccurrence,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    channel = models.CharField(max_length=16, default="alarm")
    status = models.CharField(max_length=16, default="sent")
    error_message = models.TextField(blank=True, default="")
    sent_at = models.DateTimeField(null=True, blank=True)
    payload = models.JSONField(default=dict)
