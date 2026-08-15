from django.http import HttpResponse
from django.urls import path

from care_reminders.api.views import AlarmActionView, AlarmCalendarView, ClockView, SyncView


def healthy(request):
    return HttpResponse("OK")


urlpatterns = [
    path("health", healthy),
    path("sync/", SyncView.as_view(), name="care-reminders-sync"),
    path("alarms/", AlarmCalendarView.as_view(), name="care-reminders-alarms"),
    path("clocks/", ClockView.as_view(), name="care-reminders-clocks"),
    path(
        "alarms/<uuid:external_id>/<str:action>/",
        AlarmActionView.as_view(),
        name="care-reminders-alarm-action",
    ),
]
