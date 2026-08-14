from django.http import HttpResponse
from django.urls import path

from care_reminders.api.views import AlarmActionView, AlarmCalendarView, SyncView


def healthy(request):
    return HttpResponse("OK")


urlpatterns = [
    path("health", healthy),
    path("sync/", SyncView.as_view(), name="care-reminders-sync"),
    path("alarms/", AlarmCalendarView.as_view(), name="care-reminders-alarms"),
    path(
        "alarms/<uuid:external_id>/<str:action>/",
        AlarmActionView.as_view(),
        name="care-reminders-alarm-action",
    ),
]
