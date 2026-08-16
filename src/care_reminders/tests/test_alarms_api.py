from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from care.utils.tests.base import CareAPITestBase
from config.patient_otp_token import PatientToken
from model_bakery import baker
from rest_framework.test import APIClient

from care_reminders.alarms import token as alarm_token
from care_reminders.arming import arm_medication_request
from care_reminders.models import ReminderOccurrence, ReminderSchedule
from care_reminders.prescription_sync import sync_medication_request, sync_phone_number
from care_reminders.settings import plugin_settings


class AlarmApiTest(CareAPITestBase):
    def setUp(self):
        super().setUp()
        self.user = self.create_user()
        self.facility = self.create_facility(user=self.user)
        self.organization = self.create_facility_organization(facility=self.facility)
        self.patient = self.create_patient(phone_number="+919999999999", name="Ada")
        self.encounter = self.create_encounter(
            patient=self.patient,
            facility=self.facility,
            organization=self.organization,
        )
        self.client = APIClient()
        token = PatientToken()
        token["phone_number"] = self.patient.phone_number
        self.otp_token = str(token)

    def _auth(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.otp_token}")

    def _instruction(self, text="1-0-1", code="BID", display="Two times a day", days="14"):
        return {
            "text": text,
            "as_needed_boolean": False,
            "timing": {
                "code": {"code": code, "display": display},
                "repeat": {
                    "frequency": 2,
                    "period": "1",
                    "period_unit": "d",
                    "bounds_duration": {"value": days, "unit": "d"},
                },
            },
            "dose_and_rate": {
                "type": "ordered",
                "dose_quantity": {
                    "value": "1",
                    "unit": {"code": "{tbl}", "display": "tablets"},
                },
            },
        }

    def _make_request(self, **kwargs):
        data = {
            "patient": self.patient,
            "encounter": self.encounter,
            "status": "active",
            "intent": "order",
            "category": "outpatient",
            "priority": "routine",
            "do_not_perform": False,
            "medication": {
                "display": "Paracetamol 500 mg oral tablet",
                "system": "http://snomed.info/sct",
                "code": "322236009",
            },
            "dosage_instruction": [self._instruction()],
            "authored_on": datetime.now(UTC),
        }
        data.update(kwargs)
        return baker.make("emr.MedicationRequest", **data)

    def _arm(self, request):
        return arm_medication_request(request)

    def _arm_api(self, request, **clocks):
        self._auth()
        body = {"medication_request_id": str(request.external_id), **clocks}
        return self.client.post("/api/care_reminders/arm/", body, format="json")

    def test_sync_builds_morning_and_night_for_1_0_1(self):
        request = self._make_request()
        sync_medication_request(request)
        parts = list(
            ReminderSchedule.objects.filter(medication_request=request)
            .order_by("slot_index")
            .values_list("day_part", flat=True)
        )
        self.assertEqual(["morning", "night"], parts)
        self.assertFalse(ReminderOccurrence.objects.filter(medication_request=request).exists())
        self._arm(request)
        self.assertTrue(ReminderOccurrence.objects.filter(medication_request=request).exists())

    def test_bid_morning_noon_display_does_not_use_night(self):
        request = self._make_request(
            dosage_instruction=[self._instruction(text="", code="BID", display="Morning and noon")]
        )
        sync_medication_request(request)
        parts = list(
            ReminderSchedule.objects.filter(medication_request=request)
            .order_by("slot_index")
            .values_list("day_part", flat=True)
        )
        self.assertEqual(["morning", "noon"], parts)

    def test_otp_sync_returns_calendar(self):
        self._make_request()
        self._auth()
        response = self.client.post("/api/care_reminders/sync/")
        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual([], body["occurrences"])
        self.assertEqual([], body["armed_medication_ids"])
        request = ReminderSchedule.objects.get(day_part="morning").medication_request
        armed = self._arm_api(request)
        self.assertEqual(200, armed.status_code)
        calendar = armed.json()
        self.assertGreaterEqual(len(calendar["occurrences"]), 1)
        first = calendar["occurrences"][0]
        self.assertIn("take_path", first)
        self.assertIn("scheduled_at", first)
        self.assertEqual(str(self.patient.external_id), first["patient_id"])
        self.assertEqual("Paracetamol 500 mg oral tablet", first["medication_name"])
        self.assertIn(str(request.external_id), calendar["armed_medication_ids"])

    def test_take_with_signed_token(self):
        request = self._make_request()
        sync_medication_request(request)
        self._arm(request)
        occurrence = ReminderOccurrence.objects.filter(status="pending").earliest("scheduled_at")
        token = alarm_token.generate(occurrence, "take")
        response = self.client.post(f"/api/care_reminders/alarms/{occurrence.external_id}/take/?token={token}")
        self.assertEqual(200, response.status_code)
        occurrence.refresh_from_db()
        self.assertEqual("taken", occurrence.status)
        self.assertIsNotNone(occurrence.taken_at)

    def test_skip_with_otp_bearer(self):
        request = self._make_request()
        sync_medication_request(request)
        self._arm(request)
        occurrence = ReminderOccurrence.objects.filter(status="pending").earliest("scheduled_at")
        self._auth()
        response = self.client.post(f"/api/care_reminders/alarms/{occurrence.external_id}/skip/")
        self.assertEqual(200, response.status_code)
        occurrence.refresh_from_db()
        self.assertEqual("skipped", occurrence.status)

    def test_snooze_postpones_pending_dose(self):
        request = self._make_request()
        sync_medication_request(request)
        self._arm(request)
        occurrence = ReminderOccurrence.objects.filter(status="pending").earliest("scheduled_at")
        token = alarm_token.generate(occurrence, "snooze")
        before = occurrence.scheduled_at
        response = self.client.post(
            f"/api/care_reminders/alarms/{occurrence.external_id}/snooze/?token={token}",
            {"minutes": 15},
            format="json",
        )
        self.assertEqual(200, response.status_code)
        occurrence.refresh_from_db()
        self.assertEqual("pending", occurrence.status)
        self.assertGreater(occurrence.scheduled_at, before)

    def test_rejects_missing_auth(self):
        response = self.client.get("/api/care_reminders/alarms/")
        self.assertIn(response.status_code, (401, 403))

    def test_sos_creates_no_occurrences(self):
        request = self._make_request(
            dosage_instruction=[
                {
                    "text": "SOS",
                    "as_needed_boolean": True,
                    "timing": {"code": {"code": "BID", "display": "Two times a day"}},
                }
            ]
        )
        sync_medication_request(request)
        self.assertFalse(ReminderSchedule.objects.filter(medication_request=request).exists())


class PatientClockApiTest(AlarmApiTest):
    def _hours(self, day_part: str, patient=None) -> set[int]:
        zone = ZoneInfo(plugin_settings.TIME_ZONE)
        rows = ReminderOccurrence.objects.filter(
            reminder_schedule__day_part=day_part,
            status="pending",
        )
        if patient is not None:
            rows = rows.filter(patient=patient)
        return {row.scheduled_at.astimezone(zone).hour for row in rows}

    def test_new_rx_uses_instance_morning_default(self):
        request = self._make_request()
        self._auth()
        response = self.client.post("/api/care_reminders/sync/")
        self.assertEqual(200, response.status_code)
        self.assertEqual(set(), self._hours("morning"))
        clocks = self.client.get("/api/care_reminders/clocks/")
        self.assertEqual(200, clocks.status_code)
        body = clocks.json()
        self.assertEqual(1, len(body["clocks"]))
        self.assertEqual("09:00", body["clocks"][0]["morning_at"])
        self.assertEqual(str(self.patient.external_id), body["clocks"][0]["patient_id"])
        self.assertEqual([], body["armed_medication_ids"])
        self._arm(request)
        self.assertEqual({9}, self._hours("morning"))

    def test_patch_morning_moves_all_morning_doses(self):
        first = self._make_request()
        second = self._make_request(
            medication={
                "display": "Metformin 500 mg oral tablet",
                "system": "http://snomed.info/sct",
                "code": "109081006",
            }
        )
        self._auth()
        self.client.post("/api/care_reminders/sync/")
        self._arm(first)
        self._arm(second)
        night_hours = self._hours("night")
        response = self.client.patch(
            "/api/care_reminders/clocks/",
            {"patient_id": str(self.patient.external_id), "morning_at": "07:00"},
            format="json",
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual("07:00", response.json()["clock"]["morning_at"])
        self.assertEqual({7}, self._hours("morning"))
        self.assertEqual(night_hours, self._hours("night"))
        morning_json = {
            datetime.fromisoformat(row["scheduled_at"].replace("Z", "+00:00"))
            .astimezone(ZoneInfo(plugin_settings.TIME_ZONE))
            .hour
            for row in response.json()["occurrences"]
            if row["day_part"] == "morning"
        }
        self.assertEqual({7}, morning_json)

    def test_sync_after_patch_keeps_morning_time(self):
        request = self._make_request()
        self._auth()
        self.client.post("/api/care_reminders/sync/")
        self._arm(request)
        self.client.patch(
            "/api/care_reminders/clocks/",
            {"patient_id": str(self.patient.external_id), "morning_at": "07:00"},
            format="json",
        )
        self.client.post("/api/care_reminders/sync/")
        self.assertEqual({7}, self._hours("morning"))

    def test_later_prescription_uses_patient_clock(self):
        first = self._make_request()
        self._auth()
        self.client.post("/api/care_reminders/sync/")
        self._arm(first)
        self.client.patch(
            "/api/care_reminders/clocks/",
            {"patient_id": str(self.patient.external_id), "morning_at": "07:00"},
            format="json",
        )
        second = self._make_request(
            medication={
                "display": "Metformin 500 mg oral tablet",
                "system": "http://snomed.info/sct",
                "code": "109081006",
            }
        )
        self.client.post("/api/care_reminders/sync/")
        morning = ReminderSchedule.objects.get(medication_request=second, day_part="morning")
        self.assertEqual(7, morning.time_of_day.hour)
        self.assertFalse(morning.enabled)
        self._arm(second)
        self.assertEqual({7}, self._hours("morning"))

    def test_patch_does_not_move_another_phone(self):
        other = self.create_patient(phone_number="+918888888888", name="Bea")
        other_encounter = self.create_encounter(
            patient=other,
            facility=self.facility,
            organization=self.organization,
        )
        ours = self._make_request()
        theirs = baker.make(
            "emr.MedicationRequest",
            patient=other,
            encounter=other_encounter,
            status="active",
            intent="order",
            category="outpatient",
            priority="routine",
            do_not_perform=False,
            medication={
                "display": "Ibuprofen 400 mg oral tablet",
                "system": "http://snomed.info/sct",
                "code": "387207008",
            },
            dosage_instruction=[self._instruction()],
            authored_on=datetime.now(UTC),
        )
        sync_phone_number(self.patient.phone_number)
        sync_phone_number(other.phone_number)
        self._arm(ours)
        self._arm(theirs)
        self._auth()
        self.client.patch(
            "/api/care_reminders/clocks/",
            {"patient_id": str(self.patient.external_id), "morning_at": "07:00"},
            format="json",
        )
        self.assertEqual({7}, self._hours("morning", self.patient))
        self.assertEqual({9}, self._hours("morning", other))

    def test_invalid_clock_is_rejected(self):
        self._make_request()
        self._auth()
        response = self.client.patch(
            "/api/care_reminders/clocks/",
            {"patient_id": str(self.patient.external_id), "morning_at": "25:00"},
            format="json",
        )
        self.assertEqual(422, response.status_code)

    def test_arm_with_times_then_disarm_this_and_all(self):
        first = self._make_request()
        second = self._make_request(
            medication={
                "display": "Metformin 500 mg oral tablet",
                "system": "http://snomed.info/sct",
                "code": "109081006",
            }
        )
        self._auth()
        self.client.post("/api/care_reminders/sync/")
        armed = self._arm_api(first, morning_at="07:00")
        self.assertEqual(200, armed.status_code)
        self.assertEqual("07:00", armed.json()["clock"]["morning_at"])
        self.assertEqual({7}, self._hours("morning"))
        self.assertIn(str(first.external_id), armed.json()["armed_medication_ids"])

        self._arm(second)
        self.assertEqual(2, len(self.client.get("/api/care_reminders/clocks/").json()["armed_medication_ids"]))

        cancelled = self.client.post(
            "/api/care_reminders/disarm/",
            {"medication_request_id": str(first.external_id)},
            format="json",
        )
        self.assertEqual(200, cancelled.status_code)
        self.assertNotIn(str(first.external_id), cancelled.json()["armed_medication_ids"])
        self.assertIn(str(second.external_id), cancelled.json()["armed_medication_ids"])
        self.assertFalse(ReminderOccurrence.objects.filter(medication_request=first, status="pending").exists())

        all_off = self.client.post("/api/care_reminders/disarm/", {}, format="json")
        self.assertEqual(200, all_off.status_code)
        self.assertEqual([], all_off.json()["armed_medication_ids"])
        self.assertEqual([], all_off.json()["occurrences"])
