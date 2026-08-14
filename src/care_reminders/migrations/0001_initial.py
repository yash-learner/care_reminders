import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("emr", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReminderSchedule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("external_id", models.UUIDField(db_index=True, default=uuid.uuid4, unique=True)),
                ("created_date", models.DateTimeField(auto_now_add=True, blank=True, db_index=True, null=True)),
                ("modified_date", models.DateTimeField(auto_now=True, blank=True, db_index=True, null=True)),
                ("deleted", models.BooleanField(db_index=True, default=False)),
                ("medication_name", models.CharField(max_length=255)),
                ("day_part", models.CharField(max_length=32)),
                ("slot_index", models.PositiveSmallIntegerField(default=0)),
                ("dose_amount", models.DecimalField(decimal_places=6, default=1, max_digits=20)),
                ("dose_unit", models.CharField(blank=True, default="", max_length=64)),
                ("frequency_text", models.CharField(blank=True, default="", max_length=64)),
                ("time_of_day", models.TimeField(blank=True, null=True)),
                ("interval_hours", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("enabled", models.BooleanField(default=True)),
                ("channel", models.CharField(default="alarm", max_length=16)),
                (
                    "medication_request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="care_reminder_schedules",
                        to="emr.medicationrequest",
                    ),
                ),
                (
                    "patient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="care_reminder_schedules",
                        to="emr.patient",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ReminderOccurrence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("external_id", models.UUIDField(db_index=True, default=uuid.uuid4, unique=True)),
                ("created_date", models.DateTimeField(auto_now_add=True, blank=True, db_index=True, null=True)),
                ("modified_date", models.DateTimeField(auto_now=True, blank=True, db_index=True, null=True)),
                ("deleted", models.BooleanField(db_index=True, default=False)),
                ("medication_name", models.CharField(max_length=255)),
                ("scheduled_at", models.DateTimeField()),
                ("status", models.CharField(default="pending", max_length=16)),
                ("notified_at", models.DateTimeField(blank=True, null=True)),
                ("taken_at", models.DateTimeField(blank=True, null=True)),
                ("channel", models.CharField(default="alarm", max_length=16)),
                (
                    "medication_request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="care_reminder_occurrences",
                        to="emr.medicationrequest",
                    ),
                ),
                (
                    "patient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="care_reminder_occurrences",
                        to="emr.patient",
                    ),
                ),
                (
                    "reminder_schedule",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="occurrences",
                        to="care_reminders.reminderschedule",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="NotificationDelivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("external_id", models.UUIDField(db_index=True, default=uuid.uuid4, unique=True)),
                ("created_date", models.DateTimeField(auto_now_add=True, blank=True, db_index=True, null=True)),
                ("modified_date", models.DateTimeField(auto_now=True, blank=True, db_index=True, null=True)),
                ("deleted", models.BooleanField(db_index=True, default=False)),
                ("channel", models.CharField(default="alarm", max_length=16)),
                ("status", models.CharField(default="sent", max_length=16)),
                ("error_message", models.TextField(blank=True, default="")),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("payload", models.JSONField(default=dict)),
                (
                    "reminder_occurrence",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deliveries",
                        to="care_reminders.reminderoccurrence",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="reminderschedule",
            constraint=models.UniqueConstraint(
                condition=models.Q(("deleted", False)),
                fields=("medication_request", "day_part", "slot_index"),
                name="uniq_care_reminders_schedule_slot",
            ),
        ),
        migrations.AddIndex(
            model_name="reminderschedule",
            index=models.Index(fields=["patient", "enabled"], name="care_remind_patient_enabled_idx"),
        ),
        migrations.AddConstraint(
            model_name="reminderoccurrence",
            constraint=models.UniqueConstraint(
                condition=models.Q(("deleted", False)),
                fields=("reminder_schedule", "scheduled_at"),
                name="uniq_care_reminders_occurrence_time",
            ),
        ),
        migrations.AddIndex(
            model_name="reminderoccurrence",
            index=models.Index(fields=["status", "scheduled_at"], name="care_remind_status_sched_idx"),
        ),
        migrations.AddIndex(
            model_name="reminderoccurrence",
            index=models.Index(fields=["patient", "scheduled_at"], name="care_remind_patient_sched_idx"),
        ),
    ]
