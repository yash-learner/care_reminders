# Increment 1 v1 — end-to-end plan

One patient APK that shows CARE (`care_fe` patient portal) and rings Android exact alarms for that patient’s prescriptions.

This is the working plan from here to a sideloadable debug APK. It does not change the original architecture. It only sequences what is left, names the one lock-screen edge case we will handle, and lists real-world issues we will **acknowledge simply** rather than build product around.

Related: [`increment-1.md`](increment-1.md) (architecture, APIs, test checklists).

---

## You are here

Seeing **Upcoming doses** on patient Home after OTP login means:

- OTP Rx APIs are up (`care` #3720)
- `care_reminders` is installed, migrated, and `POST /api/care_reminders/sync/` returns 200
- `care_fe` on `cursor/patient-capacitor-alarms-4f0c` is listing that calendar

The browser still cannot ring. That card is the calendar, not `AlarmManager`.

| Phase | What | Status |
| --- | --- | --- |
| 0 | Patient portal + OTP Rx | **Done** (Home / Records / Rx) |
| 1 | Django calendar + take/skip/snooze/fired | **Done** |
| 1b | Home “Upcoming doses” card | **Done** (what you are looking at) |
| 2 | Capacitor Android shell (WebView only) | **Done** (`care_fe/android`) |
| 3 | Kotlin exact alarms + lock-screen UI | **Done** (same-minute grouping) |
| 4 | Sideload E2E (including two meds at the same time) | **Your machine** — cloud VM has no Android SDK |

Continue existing branches. Do not open a patient federation plug, a fifth tab, or merge `plug_config.py` into CARE core.

| Repo | Branch |
| --- | --- |
| `care_fe` | `cursor/patient-capacitor-alarms-4f0c` ([PR #7](https://github.com/yash-learner/care_fe/pull/7)) |
| `care_reminders` | `cursor/increment-1-calendar-d302` ([PR #1](https://github.com/yash-learner/care_reminders/pull/1)) |
| `care` | `cursor/otp-prescriptions-3720-4f0c` |
| `care_medicine_reminder` | read-only Kotlin source: `cursor/android-alarm-4f0c` |

---

## Do not reverse

- CARE Django is source of truth. The phone owns the clock.
- Patient screens stay React in `care_fe`. Do not rebuild them in Stimulus or Rails.
- Rails `care_medicine_reminder` stays an independent DPG sidecar. This APK does not call it.
- `PatientRouter` / `PatientAppShell` stay core `care_fe`. No Module Federation patient plug.
- Take / skip / snooze stay **per occurrence** in the API. Never merge two medicines into one Django row.

```text
OTP login in care_fe
  → POST /api/care_reminders/sync/     (already running on Home)
  → Alarm.sync(calendar)               (Capacitor only; no-op until Phase 3)
  → Kotlin AlarmManager
  → lock-screen Taken / Skip / Snooze
  → POST /api/care_reminders/alarms/{external_id}/take|skip|snooze|fired
       (signed ?token= — no OTP JWT in the alarm extra)
```

---

## V1 product (keep this small)

**In:**

- Debug APK whose WebView is the **patient** portal (`/patient/login`), not staff EMR
- Exact alarm at each dose time, including app killed and after reboot
- Full-screen lock-screen actions
- Home still lists upcoming doses (same calendar)
- Two (or more) medicines at the same clock: **one ring, one screen, per-medicine actions**

**Out of v1:**

- iOS / AlarmKit
- FCM / web push backup
- Take / skip in the browser
- Fifth “Reminders” tab
- Quiet hours, “take with food”, refill, adherence charts
- Custom snooze picker (fixed 10 minutes, already in the plugin)
- Staff UI
- Play Store listing / OEM-specific battery hacks
- Merging occurrences in Django or a `group_id` column
- Per-medicine / per-patient alarm clocks in the patient portal — planned in [`per-medicine-alarm-clocks.md`](per-medicine-alarm-clocks.md) (v1 always uses instance `DAY_PART_TIMES`)

---

## Same-time medicines (the one edge case we bake in)

Rails does **not** group these. Each medicine is its own `ReminderOccurrence` and the Android port arms one `AlarmManager` alarm per row. Two 09:00 tablets can replace each other on the lock screen (`FLAG_ACTIVITY_CLEAR_TOP`).

**v1 rule:**

| Layer | Behaviour |
| --- | --- |
| Django / JSON | Unchanged. Flat list, one row per medicine. Unique on `(schedule, scheduled_at)`. |
| Home card | Unchanged. Two lines at 09:00 is correct. |
| Kotlin `Alarm.sync` | Collapse by `(patient_id, scheduled_at` truncated to the minute`)`. Arm **one** exact alarm per slot. |
| Lock screen | Title like “Morning · 2 medicines”. Checklist. **Take all** posts `take` on each still-pending row. Per-row take/skip. **Snooze** snoozes whatever is still pending. Show `patient_name` when the calendar has more than one patient (caregiver). |
| AlarmManager `requestCode` | Hash of the slot, not the occurrence PK. Occurrence `id` / `external_id` stay on each row for POSTs. |

Do not stagger by 1–2 minutes. Do not invent a group resource on the server.

**Acceptance:** prescribe Paracetamol `1-0-1` and Metformin `1-0-1` (same morning clock). One alarm at morning time. Both names on the screen. Take all → both occurrences `taken` in Django.

---

## Real world, handled simply

These show up on real phones. v1 handles them with the Rails Kotlin behaviour plus grouping — not new product surfaces.

| Issue | v1 behaviour |
| --- | --- |
| Notifications / exact alarm / full-screen intent | Prompt once after OTP in the native shell. If exact alarm is denied, fall back to inexact (already in `AlarmScheduler`) and leave a one-line in-app note. |
| Reboot | `BootReceiver` re-arms from local `AlarmStore`. No network, no OTP. |
| App closed for days | Last synced calendar in SharedPreferences is the clock. Opening the app runs `POST /sync/` + `Alarm.sync` again. Stale alarms until next open are accepted. |
| Lock screen / no JWT | Action URLs already carry a signed token (14 days). Never put the OTP Bearer in the `PendingIntent` extra. |
| POST fails (offline, 5xx) | Dismiss locally, toast that CARE did not save (Rails already does this). No retry queue in v1. |
| Logout / token gone | Call `Alarm.cancel()` and clear the store so the next patient’s (or no one’s) doses do not ring. |
| Lookback / horizon | Already 2 hours back, 7 days ahead. Do not ring older missed doses. |
| Timezone / DST | `scheduled_at` is UTC ISO. Kotlin parses an instant. Wall clocks were already applied when Django generated the row (`TIME_ZONE` / day-part defaults). Do not re-interpret HH:MM on the phone. |
| Caregiver / several patients on one OTP | Calendar already includes `patient_id` + `patient_name`. Group key includes `patient_id` so Ada 09:00 and her child 09:00 are two slots. |
| OEM battery killers | README one-liner: if alarms are late, exempt the app from battery optimisation. No per-vendor code. |
| Dev API from a phone | Emulator: WebView `http://10.0.2.2:4000`, API `http://10.0.2.2:<care-port>`. Physical USB: `adb reverse` both ports. Do not invent a tunnel product. |

`GET /api/care_reminders/alarms/` stays for a later native refresh. v1 refresh is: **app open → JS sync**. Boot uses the store only.

---

## Phase 2 — Capacitor shell (no ringing yet)

Put the Android project in **`care_fe/android`**. Capacitor’s default, and the APK **is** this React app. Do not start a fifth repo. That folder is committed on `cursor/patient-capacitor-alarms-4f0c` — after a pull, `npm install` and `npx cap sync android` are enough. `cap add` + `apply-android-alarm.sh` only if `android/` is missing.

Kotlin 2.3 from the Rails Android increment still applies when we add the plugin in Phase 3.

---

## Phase 3 — exact alarms (first native feature)

Port from `care_medicine_reminder` `cursor/android-alarm-4f0c`, drop Hotwire / Stimulus:

| Port | Change for CARE |
| --- | --- |
| `AlarmScheduler`, `AlarmReceiver`, `AlarmStore`, `BootReceiver` | Capacitor plugin `Alarm.sync` / `Alarm.cancel` instead of `bridge--alarm` |
| `AlarmActivity` + `activity_alarm.xml` | Checklist for a same-minute slot (the only UI addition) |
| `AlarmNotifier` | One notification per **slot**, not per medicine |
| `DoseActionClient` | Same POST to `take_path` / `skip_path` / `snooze_path` / `fired_path` |
| WorkManager 15‑minute refresh | **Skip in v1.** App-open sync is enough. |

JS is already wired: `PatientAppShell` → `usePatientAlarmSync` → `Alarm.sync(calendar)` when `window.Capacitor` is present. Phase 3 fills in the native side.

Also in this phase:

- Permission prompt after a successful OTP session
- `Alarm.cancel()` on patient logout
- `fired` POST per occurrence in the slot when the alarm actually rings (or once per slot with one POST each — same APIs)

---

## Phase 4 — definition of done

- Sideload debug APK on an emulator **and** one physical phone
- OTP → Home list matches Django occurrences
- Next dose full-screens over a locked screen
- Taken writes `taken` on that occurrence
- Two medicines, same morning time → one ring, both names, Take all writes both
- Reboot → alarm still armed
- Logout → alarms cleared
- Browser Home still lists doses and does not ring
- Rails app unused by this APK

---

## Build order (do not parallelise 2 and 3)

1. Capacitor project + debug APK loading `/patient/login` (Phase 2)
2. Confirm Home card inside the WebView (still no ring)
3. Port Kotlin plugin + slot grouping (Phase 3)
4. Permissions + logout cancel
5. Run the Android checklist in [`increment-1.md`](increment-1.md), plus the two-medicine case above
6. Optional: set `REACT_PATIENT_APK_URL` on the **web** deploy so the Home note becomes an install button

That is the whole v1 path. Everything else stays on the “explicitly later” list in `increment-1.md`.
