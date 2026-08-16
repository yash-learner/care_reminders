# Patient alarm clocks (day-part first)

People take morning medicines **together**, often earlier than the instance default (07:00 instead of 09:00). Rails stored that as `Patient.morning_at` (and noon / evening / night). This plug stores the same four clocks on `ReminderPatientClock`. New schedules copy those times; `POST /sync/` does not reset them to instance `DAY_PART_TIMES`.

**Default product:** one clock per day-part for the patient. All morning slots share it. That matches M-A-N, the Home list, and Kotlin same-minute grouping (“Take all”).

**Exception (later):** one medicine on a different clock (empty stomach at 06:00, the rest with breakfast). Do not build that until someone needs it.

Related: [`increment-1.md`](increment-1.md), [`increment-1-v1-plan.md`](increment-1-v1-plan.md).

---

## Why not per-medicine first

| | Shared day-part clock | Per-medicine clock |
| --- | --- | --- |
| Typical sentence | “I take morning medicines at 7” | “Only this antibiotic at 6” |
| `1-0-1` + `1-0-1` | One 07:00 lock screen (already built) | Two rings unless the patient lined them up |
| UI | Four pickers | A picker on every slot of every Rx |
| Sync | Copy patient clocks onto unlocked schedules | Flag per row, easy to get wrong |

Staff still prescribed `1-0-1`. The plug owns wall clocks, not FHIR.

Kotlin still rings UTC `scheduled_at`. HH:MM is interpreted in `plugin_settings.TIME_ZONE`. Per-patient timezone is a later slice.

---

## What this slice is

| Intent | This slice? |
| --- | --- |
| All of **my** morning meds at 07:00 from now on | **Yes** |
| Noon / evening / night independently | **Yes** |
| Paracetamol 07:00, Metformin 09:00 (both morning) | **No** — later per-schedule override |
| I already took today’s tablet | **No** — `take` on that occurrence |
| Tomorrow only | **No** |

---

## Do not reverse

- Django plug is source of truth. Capacitor re-syncs after PATCH.
- No fifth Patient tab. Opt-in from a **Records prescription** (bell on each medicine). Shared day-part clocks live in that sheet. Not a picker per slot.
- No Module Federation patient plug.
- Occurrences stay one row per medicine. Grouping stays Kotlin-only.
- `prescription_sync` must apply the **patient** clocks to new slots and to slots that are not a later per-medicine override.

---

## Data

New table (or CARE `Patient` JSON field on the plug — prefer a small table so we do not fork EMR):

```text
ReminderPatientClock
  patient            FK emr.Patient, unique
  time_zone          CharField  default plugin TIME_ZONE (unused in this slice except stored)
  morning_at         TimeField  default 09:00
  noon_at            TimeField  default 13:00
  evening_at         TimeField  default 18:00
  night_at           TimeField  default 21:00
```

Create the row on first sync if missing, copied from `DAY_PART_TIMES`.

`ReminderSchedule.time_of_day` stays the clock that actually fires (copied from the patient row at create / when the patient saves). Leave `time_of_day_custom` **off this slice**; add it only for the per-medicine exception.

**When the patient saves morning = 07:00:**

1. Write `ReminderPatientClock.morning_at`.
2. Update every enabled schedule for that patient with `day_part=morning` (and not custom, when that flag exists).
3. Rebuild **pending** occurrences for those schedules. Leave taken / skipped / missed.

**On `prescription_sync`:** new morning slots get `patient.morning_at` (or instance default if no clock row). Do not reset from `DAY_PART_TIMES` if a clock row exists.

---

## APIs (`care_reminders`, OTP Bearer)

```text
GET  /api/care_reminders/clocks/
PATCH /api/care_reminders/clocks/
      { "morning_at": "07:00", "noon_at": "13:00", ... }
```

Scoped to patients on the OTP phone. If the number maps to several patients (caregiver), either one clock set per `patient_id` (query param) or one row per patient in GET and PATCH by id. Do not silently apply Ada’s 07:00 to a child’s schedules.

Validate `HH:MM`. Rebuild pending occurrences in the same request; return the updated calendar so the client can `Alarm.sync` without a second round-trip.

`POST /sync/` remains safe: it must not wipe patient clocks.

---

## Patient UI (`care_fe`)

Keep `PatientRouter` / four tabs.

**Records → prescription:** bell on each scheduled medicine. That sheet turns reminders on, edits the four shared clocks, cancels this medicine, or cancels all. Home lists only armed doses.

Strings in `public/locale/en.json` only. Browser can save; only the APK rings.

---

## Native

No new plugin methods. After PATCH, invalidate `usePatientDoseCalendar` / use the calendar in the PATCH response and call existing `Alarm.sync`.

Paracetamol `1-0-1` + Metformin `1-0-1` after morning=07:00 → **one** 07:00 lock screen, Take all.

---

## Later: per-medicine override

Only if a programme needs “this tablet 30 minutes before food.” Then add `time_of_day_custom` on `ReminderSchedule`, a Records picker, and skip those rows when applying patient day-part PATCH. Do not start there.

---

## Tests

- New Rx, no clock row → 09:00 mornings.
- PATCH morning 07:00 → every pending morning occurrence for that patient is 07:00 in the plugin zone; noon unchanged.
- `POST /sync/` after PATCH does not revert to 09:00.
- Second medicine `1-0-1` added later also gets 07:00.
- Other patient on a different OTP unchanged.
- Sideload: two morning meds → one ring at the new time.

---

## Sequence

1. **Done.** `ReminderPatientClock` + GET/PATCH `/clocks/` + `POST /arm/` / `POST /disarm/`. Sync does not auto-arm.
2. **Done.** Records prescription bell + shared clocks in that sheet (`care_fe`).
3. Per-medicine override only if needed.
