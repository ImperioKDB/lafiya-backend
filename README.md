# LAFIYA Backend (FastAPI)

Matches blueprint §10/§12/§13. Deploys to Render from GitHub — pushed via
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
  `guarantor_reputation`, which don't have (and shouldn't have) a
  self-service RLS policy.
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
  to the calling CHW's own `chws.id`, accrues the ₦150 registration fee
  into `chw_earnings` immediately.
- `GET /api/patients/{id}` (role: chw) — scoped to chw-owned patients
  only. Doctor/admin patient access arrives with the consultations
  endpoint next, since that needs its own RLS policy this pass didn't add.

## Next in the build order (per blueprint §24)

Triage/consultations endpoint, then loans + guarantors, then the Wema/
ALAT lookup integration.
