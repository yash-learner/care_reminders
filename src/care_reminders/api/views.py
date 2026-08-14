from care.emr.models.patient import Patient
from config.patient_otp_authentication import (
    JWTTokenPatientAuthentication,
    OTPAuthenticatedPermission,
)
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from care_reminders.alarms import token as alarm_token
from care_reminders.alarms.calendar import Calendar
from care_reminders.alarms.snoozer import Snoozer
from care_reminders.models import NotificationDelivery, ReminderOccurrence
from care_reminders.prescription_sync import sync_phone_number

ACTIONS = {"take", "skip", "snooze", "fired"}


def _token_from(request) -> str:
    return request.query_params.get("token") or request.data.get("token") or ""


class AlarmActionPermission(BasePermission):
    def has_permission(self, request, view):
        if _token_from(request):
            return True
        return OTPAuthenticatedPermission().has_permission(request, view)


class OTPAlarmView(APIView):
    authentication_classes = [JWTTokenPatientAuthentication]
    permission_classes = [OTPAuthenticatedPermission]

    def patient_ids(self, request):
        return list(Patient.objects.filter(phone_number=request.user.phone_number).values_list("id", flat=True))


class SyncView(OTPAlarmView):
    def post(self, request):
        summary = sync_phone_number(request.user.phone_number)
        calendar = Calendar(patient_ids=self.patient_ids(request)).to_h()
        return Response({**summary, **calendar})


class AlarmCalendarView(OTPAlarmView):
    def get(self, request):
        return Response(Calendar(patient_ids=self.patient_ids(request)).to_h())


class AlarmActionView(APIView):
    authentication_classes = [JWTTokenPatientAuthentication]
    permission_classes = [AlarmActionPermission]

    def post(self, request, external_id, action):
        if action not in ACTIONS:
            return Response({"ok": False, "error": "Unknown action."}, status=404)

        occurrence = get_object_or_404(ReminderOccurrence, external_id=external_id)
        token = _token_from(request)
        if token:
            try:
                alarm_token.verify(token, occurrence_id=str(occurrence.external_id), action=action)
            except alarm_token.InvalidToken as error:
                return Response({"ok": False, "error": str(error)}, status=401)
        else:
            phone = getattr(request.user, "phone_number", None)
            if not phone or occurrence.patient.phone_number != phone:
                raise PermissionDenied("This dose does not belong to the signed-in patient.")

        handler = getattr(self, f"do_{action}")
        return handler(request, occurrence)

    def do_take(self, request, occurrence):
        if occurrence.status not in {"taken", "skipped", "missed"}:
            occurrence.status = "taken"
            occurrence.taken_at = timezone.now()
            occurrence.save(update_fields=["status", "taken_at", "modified_date"])
        self._record_delivery(occurrence, "take")
        return Response({"ok": True, "status": occurrence.status})

    def do_skip(self, request, occurrence):
        if occurrence.status not in {"taken", "skipped", "missed"}:
            occurrence.status = "skipped"
            occurrence.save(update_fields=["status", "modified_date"])
        self._record_delivery(occurrence, "skip")
        return Response({"ok": True, "status": occurrence.status})

    def do_snooze(self, request, occurrence):
        minutes = request.data.get("minutes") if isinstance(request.data, dict) else None
        try:
            Snoozer(occurrence).call(minutes=minutes)
        except ValueError as error:
            return Response({"ok": False, "error": str(error)}, status=422)
        return Response(
            {
                "ok": True,
                "status": occurrence.status,
                "scheduled_at": occurrence.scheduled_at.isoformat(),
            }
        )

    def do_fired(self, request, occurrence):
        self._record_delivery(occurrence, "fired")
        if occurrence.notified_at is None:
            occurrence.notified_at = timezone.now()
            occurrence.save(update_fields=["notified_at", "modified_date"])
        return Response({"ok": True, "status": occurrence.status})

    def _record_delivery(self, occurrence, action: str):
        NotificationDelivery.objects.create(
            reminder_occurrence=occurrence,
            channel="alarm",
            status="sent",
            sent_at=timezone.now(),
            payload={"source": "android_alarm", "action": action},
        )
