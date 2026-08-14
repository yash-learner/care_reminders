from django.contrib import admin

from care_reminders.models import NotificationDelivery, ReminderOccurrence, ReminderSchedule

admin.site.register(ReminderSchedule)
admin.site.register(ReminderOccurrence)
admin.site.register(NotificationDelivery)
