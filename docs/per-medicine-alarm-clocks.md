# Per-medicine alarm clocks

People often take a dose **earlier** than the instance default (morning at 07:00 instead of 09:00). Rails `care_medicine_reminder` exposed that as Settings + per-schedule clocks. CARE v1 does not: every `POST /sync/` stamps `DAY_PART_TIMES` onto `ReminderSchedule.time_of_day`.

This note is the plan to add **per-medicine (per slot) alarm times** without reversing increment 1.

Related: [`increment-1.md`](increment-1.md), [`increment-1-v1-plan.md`](increment-1-v1-plan.md).

---

## What “take early” means here

| Intent | This plan? |
| --- | --- |
| Paracetamol **mornings from now on** ring at 07:00 | **Yes** — change that schedule’s clock |
| Metformin mornings stay 09:00 | **Yes** — other schedules untouched |
| I already swallowed today’s tablet at 06:40, do not move future 09:00s | **No** — later “I took this dose now” on a pending occurrence |
| Tomorrow only at 06:30, then back to 09:00 | **No** — one-off exception |
| All of my morning meds at 07:00 in one tap | **Follow-on** — patient-level day-part defaults (Rails `Patient.morning_at`) |

Do not edit CARE `MedicationRequest` / FHIR timing. Staff still prescribed `1-0-1`. The reminder plug owns wall clocks.

Do not put HH:MM on the phone. Kotlin keeps ringing UTC `scheduled_at`. Django interprets the clock in `plugin_settings.TIME_ZONE` (same as today). Per-patient timezone stays a later increment.

---

## Do not reverse

- Django plug is source of truth; Capacitor only re-syncs after the calendar changes.
- No fifth Patient tab. Edit clocks on **Records → medicine** and optionally Home upcoming rows.
- No Module Federation patient plug.
- Occurrences stay one row per medicine. Same-minute grouping stays Kotlin-only.
- `prescription_sync` must **not** wipe a patient-set clock on every OTP open.

---

## Data

`ReminderSchedule` already has `time_of_day`. Add one flag:

```text
time_of_day          TimeField     wall clock for this slot
time_of_day_custom   Boolean       false = filled from DAY_PART_TIMES
```

`BaseModel.external_id` is the public id (same pattern as occurrences).

**Sync rules** (`prescription_sync.update_or_create`):

| Schedule | `time_of_day` |
| --- | --- |
| New slot | Instance `DAY_PART_TIMES[day_part]` (09:00 / 13:00 / 18:00 / 21:00) |
| Existing, `time_of_day_custom=false` | Refresh from `DAY_PART_TIMES` if instance defaults change |
| Existing, `time_of_day_custom=true` | **Keep** the patient’s clock. Still update name, dose, enabled, window. |

If the doctor drops a slot (`1-0-1` → `1-0-0`), that schedule is deleted as today; the custom clock goes with it. A new noon slot on `1-1-1` starts at the instance default.

**After PATCH:** delete **pending** occurrences for that schedule, run `OccurrenceGenerator` again. Leave `taken` / `skipped` / `missed` / `sent` rows. Next `Alarm.sync` re-arms the phone.

---

## APIs (`care_reminders`, OTP Bearer)

```text
GET  /api/care_reminders/schedules/
PATCH /api/care_reminders/schedules/{external_id}/
      { "time_of_day": "07:00" }     → custom=true, rebuild pending
POST /api/care_reminders/schedules/{external_id}/reset/
      custom=false, time_of_day=DAY_PART_TIMES[day_part], rebuild pending
```

List is scoped to patients on the OTP phone number. PATCH 404/403 if the schedule is not theirs.

Calendar JSON (already returned by `POST /sync/` and `GET /alarms/`) gains enough for the picker without a second round-trip on Home:

```json
{
  "schedule_id": "<uuid>",
  "day_part": "morning",
  "time_of_day": "07:00:00",
  "time_of_day_custom": true
}
```

`scheduled_at` stays UTC ISO-8601.

Validate `time_of_day` as `HH:MM` (or `HH:MM:SS`). Interval / STAT / weekly slots may still have a start clock; allow the same PATCH.

---

## Patient UI (`care_fe`)

Keep `PatientRouter` / four tabs.

1. **Records → prescription medicine card** (primary). Under the sig, one row per slot: “Morning alarm · 9:00 AM”. Tap → native-ish time field (i18n). Save → PATCH → invalidate `usePatientDoseCalendar` → existing `Alarm.sync` on Capacitor.
2. **Home upcoming list** (optional, same PATCH). The badge time is the next occurrence; editing it changes the **schedule**, not only that row. Copy: “Changes this medicine’s morning alarm from now on.”
3. **Reset** when `time_of_day_custom` is true.

Browser can save clocks (calendar updates). Only the APK rings.

Strings in `public/locale/en.json` only.

---

## Native

No new plugin methods. After a successful PATCH, JS already on `PatientAppShell` must refresh:

`POST /sync/` is **not** required to apply the clock if PATCH rebuilt occurrences; `GET /alarms/` + `Alarm.sync` is enough. Calling `POST /sync/` is still safe because custom clocks are preserved.

If two medicines share the new minute, lock screen grouping is unchanged.

---

## Timezone (this slice)

Wall clock + `CARE_REMINDERS_TIME_ZONE` / Django `TIME_ZONE`. Do not read the phone’s zone. A patient who travels is a later `Patient.time_zone` field (Rails already had it).

---

## Tests

Django:

- New Rx → morning 09:00, `custom=false`.
- PATCH 07:00 → pending `scheduled_at` is 07:00 in the plugin zone; `custom=true`.
- `POST /sync/` after PATCH does **not** revert to 09:00.
- Reset → 09:00 again.
- Other medicine on the same patient unchanged.
- OTP cannot PATCH another phone’s schedule.

Playwright (web): Records picker saves; Home list shows the new time. No AlarmManager in the browser.

Sideload: Paracetamol morning 07:00, Metformin morning 09:00 → two rings. Both at 07:00 → one grouped lock screen.

---

## Sequence

1. Migration + sync preserve + PATCH/reset + calendar fields (`care_reminders`).
2. Records picker + i18n (`care_fe`).
3. Home row uses the same mutation; Capacitor picks it up via existing sync hook.
4. Optional follow-on: patient-level day-part defaults applied only to `time_of_day_custom=false` schedules.

Do not start with Kotlin time pickers or a Settings tab.
