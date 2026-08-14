from datetime import timedelta

from django.db import IntegrityError
from django.utils import timezone

from care_reminders.settings import plugin_settings


class Snoozer:
    MIN_MINUTES = 1
    MAX_MINUTES = 120

    def __init__(self, occurrence):
        self.occurrence = occurrence

    def call(self, minutes=None):
        if self.occurrence.status not in {"pending", "sent"}:
            raise ValueError(f"This dose is already {self.occurrence.status}.")

        delay = int(minutes or plugin_settings.SNOOZE_MINUTES)
        if delay < self.MIN_MINUTES or delay > self.MAX_MINUTES:
            delay = int(plugin_settings.SNOOZE_MINUTES)
        next_at = timezone.now() + timedelta(minutes=delay)

        for _ in range(5):
            try:
                self.occurrence.status = "pending"
                self.occurrence.scheduled_at = next_at
                self.occurrence.notified_at = None
                self.occurrence.taken_at = None
                self.occurrence.save(
                    update_fields=["status", "scheduled_at", "notified_at", "taken_at", "modified_date"]
                )
                return self.occurrence
            except IntegrityError:
                next_at += timedelta(minutes=1)

        raise ValueError("Could not snooze this dose; another reminder already uses that time.")
