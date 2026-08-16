from django.http import HttpResponse
from django.urls import path

from care_reminders.api.views import (
    AlarmActionView,
    AlarmCalendarView,
    ArmView,
    ClockView,
    DisarmView,
    SyncView,
)


def healthy(request):
    return HttpResponse("OK")


urlpatterns = [
    path("health", healthy),
    path("sync/", SyncView.as_view(), name="care-reminders-sync"),
    path("alarms/", AlarmCalendarView.as_view(), name="care-reminders-alarms"),
    path("clocks/", ClockView.as_view(), name="care-reminders-clocks"),
    path("arm/", ArmView.as_view(), name="care-reminders-arm"),
    path("disarm/", DisarmView.as_view(), name="care-reminders-disarm"),
    path(
        "alarms/<uuid:external_id>/<str:action>/",
        AlarmActionView.as_view(),
        name="care-reminders-alarm-action",
    ),
]
