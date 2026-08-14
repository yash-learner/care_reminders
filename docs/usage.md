# Usage

Increment 1 APIs (OTP Bearer, same `JWTTokenPatientAuthentication` as care#3720):

| Endpoint | Purpose |
| --- | --- |
| `POST /api/care_reminders/sync/` | Rebuild upcoming occurrences from live CARE prescriptions; returns the alarm calendar |
| `GET /api/care_reminders/alarms/` | JSON calendar (2h ago → 7 days) with signed take/skip/snooze/fired paths |
| `POST /api/care_reminders/alarms/{external_id}/take\|skip\|snooze\|fired/` | Dose actions. Auth: OTP Bearer **or** `?token=` from the calendar |

Health check: `GET /api/care_reminders/health`

Patient UI stays in `care_fe` (`PatientAppShell` Capacitor sync). This repo is the Django calendar only — not a frontend federation plug.
