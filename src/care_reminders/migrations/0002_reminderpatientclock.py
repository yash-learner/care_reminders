import datetime
import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("emr", "0001_initial"),
        ("care_reminders", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReminderPatientClock",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("external_id", models.UUIDField(db_index=True, default=uuid.uuid4, unique=True)),
                ("created_date", models.DateTimeField(auto_now_add=True, blank=True, db_index=True, null=True)),
                ("modified_date", models.DateTimeField(auto_now=True, blank=True, db_index=True, null=True)),
                ("deleted", models.BooleanField(db_index=True, default=False)),
                ("time_zone", models.CharField(default="Asia/Kolkata", max_length=64)),
                ("morning_at", models.TimeField(default=datetime.time(9, 0))),
                ("noon_at", models.TimeField(default=datetime.time(13, 0))),
                ("evening_at", models.TimeField(default=datetime.time(18, 0))),
                ("night_at", models.TimeField(default=datetime.time(21, 0))),
                (
                    "patient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="care_reminder_clocks",
                        to="emr.patient",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="reminderpatientclock",
            constraint=models.UniqueConstraint(
                condition=models.Q(("deleted", False)),
                fields=("patient",),
                name="cr_rpc_patient_uniq",
            ),
        ),
    ]
