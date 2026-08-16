from django.db import migrations, models


def disable_auto_armed(apps, schema_editor):
    ReminderSchedule = apps.get_model("care_reminders", "ReminderSchedule")
    ReminderOccurrence = apps.get_model("care_reminders", "ReminderOccurrence")
    ReminderSchedule.objects.filter(deleted=False, enabled=True).update(enabled=False)
    ReminderOccurrence.objects.filter(deleted=False, status="pending").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("care_reminders", "0002_reminderpatientclock"),
    ]

    operations = [
        migrations.AlterField(
            model_name="reminderschedule",
            name="enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(disable_auto_armed, migrations.RunPython.noop),
    ]
