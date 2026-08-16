"""Build ReminderOccurrence rows from a ReminderSchedule + active window."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.utils import timezone

from care_reminders.models import ReminderOccurrence, ReminderSchedule
from care_reminders.settings import plugin_settings


def _instant(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(microsecond=0)


class OccurrenceGenerator:
    def __init__(self, schedule: ReminderSchedule, *, starts_on, ends_on, now=None):
        self.schedule = schedule
        self.starts_on = starts_on
        self.ends_on = ends_on
        self.now = now or timezone.now()

    def call(self) -> list[ReminderOccurrence]:
        # Taken / skipped / missed / sent keep the unique (schedule, time) slot.
        # Only pending rows are rebuilt so a second Home sync does not collide.
        self.schedule.occurrences.filter(status="pending").delete()
        if not self.schedule.enabled:
            return []

        occupied = {
            _instant(at)
            for at in ReminderOccurrence.objects.filter(reminder_schedule=self.schedule).values_list(
                "scheduled_at", flat=True
            )
        }
        created: list[ReminderOccurrence] = []
        for timestamp in self._timestamps():
            instant = _instant(timestamp)
            if instant in occupied:
                continue
            occupied.add(instant)
            status = "missed" if timestamp < self.now else "pending"
            try:
                with transaction.atomic():
                    created.append(
                        ReminderOccurrence.objects.create(
                            reminder_schedule=self.schedule,
                            patient=self.schedule.patient,
                            medication_request=self.schedule.medication_request,
                            medication_name=self.schedule.medication_name,
                            scheduled_at=timestamp,
                            channel=self.schedule.channel,
                            status=status,
                        )
                    )
            except IntegrityError:
                continue
        return created

    def _zone(self) -> ZoneInfo:
        return ZoneInfo(plugin_settings.TIME_ZONE)

    def _clock(self):
        if self.schedule.time_of_day:
            return self.schedule.time_of_day
        morning = plugin_settings.DAY_PART_TIMES.get("morning", "09:00")
        hour, minute = (int(part) for part in morning.split(":")[:2])
        from datetime import time as dt_time

        return dt_time(hour, minute)

    def _horizon_end(self, start_at: datetime) -> datetime:
        if self.ends_on:
            return self.ends_on
        return start_at + timedelta(days=int(plugin_settings.OCCURRENCE_HORIZON_DAYS))

    def _timestamps(self) -> list[datetime]:
        zone = self._zone()
        start_at = self.starts_on.astimezone(zone) if self.starts_on else self.now.astimezone(zone)
        finish_at = self._horizon_end(start_at).astimezone(zone)
        clock = self._clock()
        day_part = self.schedule.day_part

        if day_part == "stat":
            return [max(start_at, self.now)]
        if day_part == "interval":
            return self._interval_times(start_at, finish_at, clock, int(self.schedule.interval_hours or 0), zone)
        step = {"weekly": 7, "monthly": 30, "alternate_day": 2}.get(day_part, 1)
        return self._step_days(start_at, finish_at, clock, step, zone)

    def _step_days(self, start_at, finish_at, clock, step, zone) -> list[datetime]:
        date = start_at.date()
        last = finish_at.date()
        times = []
        while date <= last:
            timestamp = datetime(date.year, date.month, date.day, clock.hour, clock.minute, clock.second, tzinfo=zone)
            if timestamp >= start_at and timestamp < finish_at:
                times.append(timestamp)
            date += timedelta(days=step)
        return times

    def _interval_times(self, start_at, finish_at, clock, hours, zone) -> list[datetime]:
        if hours <= 0:
            return []
        cursor = datetime(
            start_at.year, start_at.month, start_at.day, clock.hour, clock.minute, clock.second, tzinfo=zone
        )
        while cursor < start_at:
            cursor += timedelta(hours=hours)
        times = []
        while cursor < finish_at:
            times.append(cursor)
            cursor += timedelta(hours=hours)
        return times
