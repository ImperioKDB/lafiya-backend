# LAFIYA Backend (FastAPI)

Matches blueprint SS10/SS12/SS13. Deploys to Render from GitHub — pushed via
`push_backend.py` in Colab, never uploaded or edited locally.

## Roles and how accounts get provisioned

There are 4 roles: `chw`, `doctor`, `pharmacy`, `admin`. There's no
separate `patients` login — patients are mediated by a CHW or identified
by phone number over USSD.

Role is resolved **by table membership**, not a JWT claim:

1. Create the person's login the normal Supabase way (Auth -> add user,
   or your own sign-up flow once one exists).
2. To make them a **chw**: insert a row into `chws` with `auth_user_id`
   set to that user's UUID. Same pattern for `doctors` and `pharmacies`.
3. To make them an **admin**: no table row needed — add their email to
   the `ADMIN_EMAILS` environment variable (comma-separated) in Render.

`get_current_user` in `app/core/auth.py` checks chws -> doctors ->
pharmacies -> the admin allowlist, in that order, and rejects the
request with 403 if none match. A real account should only ever match
one.

## Two Supabase clients, on purpose

- `get_service_client()` — service-role key, bypasses RLS. Only used for
  role lookup at login and for writes to `chw_earnings`/
  `doctor_earnings`/`guarantor_reputation`, which don't have (and
  shouldn't have) a self-service RLS policy.
- `get_user_client(access_token)` — scoped to the caller's own JWT, so
  every Postgres RLS policy from the migration still applies. Every
  endpoint that touches user-owned data (patients, consultations, loans,
  guarantors, claims) should use this one. The FastAPI `require_role`
  check is a second line of defense, not a replacement for RLS.

## Running locally

```
pip install -r requirements.txt
cp .env.example .env   # fill in the real values from Supabase dashboard
uvicorn app.main:app --reload
```

Then `GET http://localhost:8000/api/health` should return `{"status": "ok"}`.

## What's live so far

- `POST /api/patients` (role: chw) — registers a patient, RLS-enforced
  to the calling CHW's own `chws.id`, accrues the NGN150 registration fee
  into `chw_earnings` immediately.
- `GET /api/patients/{id}` (role: chw) — scoped to chw-owned patients
  only.
- `POST /api/consultations` (role: chw) — creates a consultation against
  a patient this chw registered, scores urgency via the rule-based
  triage engine (`app/services/triage.py` — same logic path the USSD
  numeric-category flow will use later, per PRD SS6.7). `transcript` is
  optional and hand-entered for now; live Whisper wiring is next.
- `GET /api/consultations/queue` (role: doctor) — unclaimed cases plus
  this doctor's own claimed ones, sorted by urgency then age.
- `PATCH /api/consultations/{id}` (role: doctor) — claims the case
  on first write (`doctor_id` set to the calling doctor), updates
  prescription/cost_estimate, and on `complete: true` accrues the NGN500
  stipend into `doctor_earnings` exactly once.
- **New RLS policy**: doctors can now `SELECT` a `patients` row if it's
  linked through one of their own `consultations` rows — see
  `migrations/002_consultations_rls.sql`. Doctors still cannot see
  patients they have no consultation relationship with.
- **New table**: `doctor_earnings` (mirrors `chw_earnings` — blueprint
  SS11 never defined a doctor-side earnings table, so this is a new
  addition this pass, not something restored from spec). Same
  service-role-only write pattern as `chw_earnings`.

## Next in the build order (per blueprint SS24)

Pharmacy claim submission + variance matching, then the fraud rule
engine.

## Wema/ALAT sandbox setup

`GET /api/wema/account-lookup/{account_number}` (role: chw) calls the
live ALAT Playground sandbox -- Wallet Services, Account Management API,
"Get Wallet Details" operation. To make this work in Render:

1. Sign in at playground.alat.ng, subscribe to **Wallet Services**
   (nothing else -- see below), attach it to an Application, generate keys.
2. Set `WEMA_API_KEY` in Render's environment variables. `WEMA_BASE_URL`
   already defaults to `https://apiplayground.alat.ng`.

Deliberately not wired up: any wallet/account **creation** endpoint
(Wallet Creation API - BVN, Wallet Creation API - NIN, Face Biometric,
E-Commerce Wallet Creation). All of them require a real government ID
check, one way or another -- that conflicts with the locked decision to
keep NIN simulated for the life of this project. Lookup/balance only.
