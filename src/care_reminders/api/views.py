from care.emr.models.medication_request import MedicationRequest
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
from care_reminders.arming import (
    arm_medication_request,
    armed_medication_ids,
    disarm_medication_request,
    disarm_patients,
    update_patient_clock,
)
from care_reminders.clocks import ensure_patient_clock, serialize_clock
from care_reminders.models import NotificationDelivery, ReminderOccurrence, ReminderSchedule
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

    def patients(self, request):
        return list(Patient.objects.filter(phone_number=request.user.phone_number))

    def patient_ids(self, request):
        return [patient.id for patient in self.patients(request)]


def _payload(view, request, *, clock=None, extra=None):
    patient_ids = view.patient_ids(request)
    patients = list(Patient.objects.filter(phone_number=request.user.phone_number))
    body = {
        "ok": True,
        "armed_medication_ids": armed_medication_ids(patient_ids),
        "clocks": [serialize_clock(ensure_patient_clock(patient)) for patient in patients],
        **Calendar(patient_ids=patient_ids).to_h(),
    }
    if clock is not None:
        body["clock"] = serialize_clock(clock)
    if extra:
        body.update(extra)
    return Response(body)


def _medication_on_phone(request, medication_request_id: str) -> MedicationRequest:
    medication = get_object_or_404(MedicationRequest, external_id=medication_request_id)
    phone = getattr(request.user, "phone_number", None)
    if not phone or medication.patient.phone_number != phone:
        raise PermissionDenied("This medicine is not on the signed-in number.")
    return medication


class SyncView(OTPAlarmView):
    def post(self, request):
        summary = sync_phone_number(request.user.phone_number)
        return _payload(self, request, extra=summary)


class AlarmCalendarView(OTPAlarmView):
    def get(self, request):
        return Response(Calendar(patient_ids=self.patient_ids(request)).to_h())


class ClockView(OTPAlarmView):
    def get(self, request):
        patients = self.patients(request)
        return Response(
            {
                "clocks": [serialize_clock(ensure_patient_clock(patient)) for patient in patients],
                "armed_medication_ids": armed_medication_ids([patient.id for patient in patients]),
            }
        )

    def patch(self, request):
        patients = self.patients(request)
        if not patients:
            return Response({"ok": False, "error": "No patient on this number."}, status=404)

        payload = request.data if isinstance(request.data, dict) else {}
        patient_id = str(payload.get("patient_id") or "")
        if patient_id:
            patient = next((item for item in patients if str(item.external_id) == patient_id), None)
            if patient is None:
                raise PermissionDenied("This patient is not on the signed-in number.")
        elif len(patients) == 1:
            patient = patients[0]
        else:
            return Response({"ok": False, "error": "patient_id is required."}, status=422)

        try:
            clock, _changed = update_patient_clock(patient, payload)
        except ValueError as error:
            return Response({"ok": False, "error": str(error)}, status=422)

        return _payload(self, request, clock=clock)


class ArmView(OTPAlarmView):
    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        medication_request_id = str(payload.get("medication_request_id") or "")
        if not medication_request_id:
            return Response({"ok": False, "error": "medication_request_id is required."}, status=422)

        medication = _medication_on_phone(request, medication_request_id)
        try:
            clock, _changed = update_patient_clock(medication.patient, payload)
        except ValueError as error:
            return Response({"ok": False, "error": str(error)}, status=422)

        created = arm_medication_request(medication)
        if created == 0 and not ReminderSchedule.objects.filter(medication_request=medication).exists():
            return Response(
                {"ok": False, "error": "This medicine has no scheduled times (for example SOS)."},
                status=422,
            )
        return _payload(self, request, clock=clock, extra={"occurrences_created": created})


class DisarmView(OTPAlarmView):
    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        medication_request_id = str(payload.get("medication_request_id") or "")
        if medication_request_id:
            medication = _medication_on_phone(request, medication_request_id)
            disarm_medication_request(medication)
            clock = ensure_patient_clock(medication.patient)
        else:
            disarm_patients(self.patient_ids(request))
            patients = self.patients(request)
            clock = ensure_patient_clock(patients[0]) if patients else None
        return _payload(self, request, clock=clock)


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
