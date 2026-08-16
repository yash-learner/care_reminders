from datetime import UTC, timedelta
from urllib.parse import urlencode

from django.utils import timezone

from care_reminders.alarms import token as alarm_token
from care_reminders.models import ReminderOccurrence
from care_reminders.settings import plugin_settings


class Calendar:
    def __init__(self, *, patient_ids, now=None):
        self.patient_ids = patient_ids
        self.now = now or timezone.now()

    def to_h(self) -> dict:
        return {
            "generated_at": self.now.isoformat(),
            "snooze_minutes": int(plugin_settings.SNOOZE_MINUTES),
            "calendar_path": "/api/care_reminders/alarms/",
            "occurrences": [self.serialize(occurrence) for occurrence in self.occurrences()],
        }

    def occurrences(self):
        lookback = timedelta(hours=int(plugin_settings.ALARM_LOOKBACK_HOURS))
        horizon = timedelta(days=int(plugin_settings.ALARM_HORIZON_DAYS))
        return (
            ReminderOccurrence.objects.filter(
                patient_id__in=self.patient_ids,
                status__in=["pending", "sent"],
                scheduled_at__gte=self.now - lookback,
                scheduled_at__lte=self.now + horizon,
            )
            .select_related("reminder_schedule", "patient", "medication_request")
            .order_by("scheduled_at")
        )

    def serialize(self, occurrence, *, actions: bool = True) -> dict:
        taken_at = None
        if occurrence.taken_at:
            taken_at = occurrence.taken_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
        row = {
            "id": occurrence.pk,
            "external_id": str(occurrence.external_id),
            "scheduled_at": occurrence.scheduled_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "status": occurrence.status,
            "title": occurrence.title(),
            "body": occurrence.body(),
            "medication_name": occurrence.medication_name,
            "medication_request_id": str(occurrence.medication_request.external_id),
            "patient_id": str(occurrence.patient.external_id),
            "patient_name": occurrence.patient.name,
            "day_part": occurrence.reminder_schedule.day_part,
            "taken_at": taken_at,
        }
        if actions:
            row["take_path"] = self._action_path(occurrence, "take")
            row["skip_path"] = self._action_path(occurrence, "skip")
            row["snooze_path"] = self._action_path(occurrence, "snooze")
            row["fired_path"] = self._action_path(occurrence, "fired")
        return row

    def _action_path(self, occurrence, action: str) -> str:
        query = urlencode({"token": alarm_token.generate(occurrence, action)})
        return f"/api/care_reminders/alarms/{occurrence.external_id}/{action}/?{query}"


class DoseHistory(Calendar):
    """Taken / skipped / missed / upcoming rows for the prescription screen."""

    def occurrences(self):
        lookback = timedelta(days=int(plugin_settings.ALARM_HORIZON_DAYS))
        horizon = timedelta(days=int(plugin_settings.ALARM_HORIZON_DAYS))
        return (
            ReminderOccurrence.objects.filter(
                patient_id__in=self.patient_ids,
                scheduled_at__gte=self.now - lookback,
                scheduled_at__lte=self.now + horizon,
            )
            .select_related("reminder_schedule", "patient", "medication_request")
            .order_by("scheduled_at")
        )

    def to_h(self) -> dict:
        return {
            "generated_at": self.now.isoformat(),
            "occurrences": [self.serialize(occurrence, actions=False) for occurrence in self.occurrences()],
        }
