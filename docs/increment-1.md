# Increment 1 — CARE patient APK + Android exact alarms

One patient APK that shows CARE (`care_fe` patient portal) and rings Android exact alarms for that patient’s prescriptions.

- CARE Django stays source of truth. The phone owns the clock.
- `care_fe` screens stay React. We do not rebuild them in Stimulus.
- Rails `care_medicine_reminder` stays the independent DPG sidecar.
- iOS, email, and a second portal wait.

## Target loop

```text
Patient OTP login in care_fe (ENG-831 squashed onto fork develop)
  → GET /api/v1/otp/medication_prescription/     (care#3720)
  → Django plugin care_reminders: build ReminderOccurrence rows
  → GET /api/care_reminders/alarms/  (OTP Bearer, next 7 days)
  → Capacitor JS bridge
  → Kotlin AlarmManager (port from care_medicine_reminder)
  → full-screen Taken / Snooze / Skip
  → POST /api/care_reminders/alarms/:id/take|skip|snooze|fired
```

## What we reuse

| From Rails app | Goes to |
| --- | --- |
| `Care::DosageParser` / timing map | this plugin |
| Occurrence calendar + snooze | Django models + OTP views |
| `AlarmScheduler`, `AlarmReceiver`, `AlarmActivity`, `AlarmStore` | Capacitor Android plugin |
| Packaging / Kotlin 2.3 lessons | Same Gradle story |

Leave behind: Hotwire Native, Stimulus `bridge--alarm`, Rails as CARE’s backend.

## Repos / branches

| Repo | Branch | Role |
| --- | --- | --- |
| [yash-learner/care_fe](https://github.com/yash-learner/care_fe) | `cursor/patient-capacitor-alarms-4f0c` | Fork **develop** + **squash** of ENG-831 ([ohcnetwork/care_fe#16612](https://github.com/ohcnetwork/care_fe/pull/16612)). Do **not** work on `ENG-831`. |
| [yash-learner/care](https://github.com/yash-learner/care) | fork `develop` + squash of [ohcnetwork/care#3720](https://github.com/ohcnetwork/care/pull/3720) | OTP Rx/lab APIs. Must run locally. |
| [yash-learner/care_reminders](https://github.com/yash-learner/care_reminders) | `cursor/increment-1-calendar-d302` | Calendar + alarm HTTP. `pip install -e`. |
| Capacitor Android | later, next to `care_fe` or `apps/patient_android` | WebView + alarm plugin |
| [yash-learner/care_medicine_reminder](https://github.com/yash-learner/care_medicine_reminder) | unchanged | Rails DPG sidecar |

### Cloud environments

Four-repo environment (`care`, `care_fe`, `care_medicine_reminder`, `care_reminders`):

- `care_fe` on `cursor/patient-capacitor-alarms-4f0c` (patient portal, Home upcoming-doses card, Capacitor sync hook)
- `care` on a branch that includes #3720
- `care_reminders` installed editable (`pip install -e` + `plug_config.py`)

## Where the patient UI lives

`PatientRouter` is a hardcoded route table (home, visits, records, profile). `PatientAppShell` has a fixed four-tab bar. Plugin slots (`PatientHomeActions`, encounter tabs) are staff EMR hooks and use staff `AuthUserContext`, not OTP `PatientUserContext`.

A patient frontend federation plug would need CARE-core contracts that do not exist yet (plugin routes in `PatientRouter`, patient nav in the shell, OTP auth on `window` for remotes, Module Federation inside a Capacitor WebView). That is a separate OHC PR, not a prerequisite for ringing alarms.

| Layer | Where | Why |
| --- | --- | --- |
| Dose calendar + take/skip/snooze APIs | Django plug `care_reminders` | Optional per deployment; CARE core should not own occurrences |
| Patient screens | `care_fe` `PatientRouter` | Records already show prescriptions; the APK is this React app |
| Clock | Capacitor Kotlin, not React | Web cannot call `AlarmManager` |
| Staff adherence UI (later) | Frontend plug on `AppRouter` | Staff already has plugin routes |

Increment 1 UI in `care_fe` stays small:

- Patient Home lists upcoming doses from `POST /api/care_reminders/sync/` (web and Capacitor). That is how you confirm the plugin is working in a browser — the list is the same calendar the phone will ring.
- `PatientAppShell` still calls `Alarm.sync` **only** when `window.Capacitor` is present. The browser cannot set `AlarmManager`.
- Optional `REACT_PATIENT_APK_URL` turns the Home note into an “Install the Android app to set alarms” button once an APK is published.

Do **not** add a fifth “Reminders” tab unless patients need a screen the native alarm and existing Records pages do not cover. Extract a `care_reminders_fe` plug only if a deployment needs the patient UI without shipping that code in core.

## Phase 0 — run the portal

1. Run care#3720 + care_fe `cursor/patient-capacitor-alarms-4f0c`.
2. Patient OTP login → Home → Records → a prescription with `1-0-1`.
3. Confirm `GET /api/v1/otp/medication_prescription/` with the Bearer token.

No Capacitor until this works. No Rx in the session means nothing to ring.

## Phase 1 — Django plugin (this repo)

URLs under `/api/care_reminders/`. Auth: same `JWTTokenPatientAuthentication` as OTP viewsets. Parser prefers CARE FHIR `text` (M-A-N like `1-0-1`) over a bare `BID` code, matching `care_fe`.

**Models** (slim port of Rails):

- `ReminderSchedule` — per medication request / prescription line
- `ReminderOccurrence` — one clock time, `pending` / `taken` / `skipped`
- Optional `NotificationDelivery` for `alarm` / `fired`

**Logic to port first:** M-A-N + CARE FHIR `text` over `BID`; `getMedicationActiveWindow`; generate occurrences.

**OTP APIs:**

| Endpoint | Purpose |
| --- | --- |
| `POST /api/care_reminders/sync/` | From live prescriptions, (re)build upcoming occurrences |
| `GET /api/care_reminders/alarms/` | JSON calendar (2h ago → 7 days), signed action URLs |
| `POST /api/care_reminders/alarms/:id/take\|skip\|snooze\|fired/` | Same as Rails |

Scope to `request.user` patient (same as 3720). Tests for `1-0-1` vs BID display variants.

**Out of this phase:** web push, email, Celery clone. Sync on-demand when the app opens.

## Phase 2 — Capacitor shell (no alarm yet)

New Android Capacitor app whose WebView loads **patient** `care_fe`:

- Dev: `http://10.0.2.2:4000/patient/login` (or `/patient/home`)
- Not the staff EMR as the start URL

Ship as APK. Success = OTP login, Home, Records, prescription detail — same ENG-831 UI.

Do not extract routes from the React bundle. Point at the patient door.

## Phase 3 — Android alarm as the first native feature

Port the working Kotlin into a Capacitor plugin (`Alarm.sync`, `Alarm.cancel`):

- `setExactAndAllowWhileIdle` + full-screen `AlarmActivity`
- `BootReceiver` re-arm from local store
- Permissions: notifications + exact alarm

**Bridge (keep tiny):** after patient token exists (`patientToken` / Bearer in `care_fe` auth):

1. `POST /api/care_reminders/sync/` (rebuilds occurrences and returns the calendar)
2. `Alarm.sync(calendar)` — no-op until the Capacitor plugin exists

`GET /api/care_reminders/alarms/` remains for native refresh (boot / worker).

The `care_fe` calendar query runs on web and Capacitor (`POST /sync/`) so Home can list doses. `Alarm.sync` still runs **only when `window.Capacitor` is present**. Taken / Snooze / Skip = native UI; POST to this plugin with the signed action token on the calendar paths (lock-screen safe) or the OTP Bearer.

JSON `id` is the integer PK (AlarmManager request code). Action URLs use `external_id` (UUID). `scheduled_at` is UTC ISO-8601.

**Risk:** OTP token → native → plugin API. Signed action tokens on take/skip/snooze/fired solve lock-screen POSTs without storing the JWT in the alarm extra.

## Phase 4 — definition of done

- Sideload APK
- Patient OTP → see Rx from CARE
- Next dose full-screens over lock screen
- Taken writes CARE-side occurrence
- Rails app still runs as DPG, unused by this APK

## Explicitly later

- iOS AlarmKit (iOS 26)
- care_fe federation plugin / extra “Reminders” tab
- Wrapping staff `AppRouter`
- Killing Rails
- Email / WhatsApp / other EMRs

## How to test

### Web (now — no APK)

Alarms will not ring in Chrome/Firefox. The Home card is the check that Django sync works.

1. Backend: `care` with OTP Rx APIs (`cursor/otp-prescriptions-3720-4f0c`) + this plugin installed and migrated (`migrate care_reminders`).
2. Frontend: `care_fe` branch `cursor/patient-capacitor-alarms-4f0c`, `npm run dev` (port 4000).
3. Confirm `GET /api/care_reminders/health` is `OK`.
4. Patient OTP login → **Home**.
5. Under the greeting you should see **Upcoming doses**.
6. DevTools → Network: `POST /api/care_reminders/sync/` returns **200** with `occurrences`.
7. Staff must have prescribed something the parser understands (CARE `text` like `1-0-1`, or a BID-style timing). Then dose times appear.
8. Empty list + the Android note still means the API is up. Missing card usually means the plugin is not registered (`404` on `/sync/`).
9. Leave `REACT_PATIENT_APK_URL` unset until an APK exists. When you publish one, set it to the download URL and the Home note becomes an install button.

### Android (after Phase 2 + 3 — no APK yet)

There is no sideloadable APK in this increment yet. When the Capacitor app and Kotlin `Alarm` plugin exist:

1. Point the WebView at patient `care_fe` (dev emulator: `http://10.0.2.2:4000/patient/login`, or the hosted patient URL).
2. Build a debug APK (`./gradlew assembleDebug` in the Android project). Sideload it. Enable Install unknown apps if needed.
3. On first launch, allow notifications and exact alarms (Android 12+: Alarms & reminders).
4. OTP login → Home. Same upcoming-doses list as web. Copy should say alarms are set on this device (not the APK download note).
5. Optional: set `REACT_PATIENT_APK_URL` on the **web** deploy so browser users can install from Home.
6. Lock the phone. Wait for the next pending `scheduled_at` (or temporarily schedule a dose a minute ahead). Full-screen Taken / Snooze / Skip should appear over the lock screen.
7. Taken / Skip / Snooze should `POST /api/care_reminders/alarms/{external_id}/…` (signed `?token=` is lock-screen safe). Confirm the occurrence status in Django.
8. Reboot the phone; `BootReceiver` should re-arm from the local store.

Kotlin to port lives in `care_medicine_reminder` (`AlarmScheduler`, `AlarmActivity`, `DoseAlarm`, etc.). Suggested app location: `care_fe/android` or `apps/patient_android` — not chosen yet.

## Order of work

1. Phase 0 (portal + 3720) in CARE / care_fe — in progress on the forks
2. Models + `1-0-1` parser + OTP APIs in this plugin — done on `cursor/increment-1-calendar-d302`
3. Web Home “Upcoming doses” card — done on `care_fe` `cursor/patient-capacitor-alarms-4f0c`
4. Capacitor WebView shell (Phase 2) — **next**
5. Port Kotlin alarm plugin and wire `Alarm.sync` (Phase 3)
6. Sideload APK and run the Android checklist above
