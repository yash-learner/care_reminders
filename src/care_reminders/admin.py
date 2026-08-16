from django.contrib import admin

from care_reminders.models import (
    NotificationDelivery,
    ReminderOccurrence,
    ReminderPatientClock,
    ReminderSchedule,
)

admin.site.register(ReminderSchedule)
admin.site.register(ReminderOccurrence)
admin.site.register(ReminderPatientClock)
admin.site.register(NotificationDelivery)
