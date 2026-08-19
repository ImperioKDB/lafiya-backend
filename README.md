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
  `doctor_earnings`/`guarantor_reputation`/`fraud_flags`, none of which
  have (or should have) a self-service RLS policy.
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
  numeric-category flow will use later, per PRD SS6.7).
- `GET /api/consultations/queue` (role: doctor) — unclaimed cases plus
  this doctor's own claimed ones, sorted by urgency then age.
- `PATCH /api/consultations/{id}` (role: doctor) — claims the case
  on first write, updates prescription/cost_estimate, accrues the NGN500
  stipend into `doctor_earnings` exactly once on completion.
- `POST /api/loans` (role: chw) — server-side fee math (flat 5%), tier
  validated against the DB check constraint.
- `GET /api/loans/{id}/status` (role: chw) — loan + its guarantors.
- `POST /api/loans/{id}/guarantors` (role: chw) — attaches exactly two,
  50/50 liability, blocked if either phone is barred in
  `guarantor_reputation`.
- `POST /api/loans/{id}/disburse` (role: chw) — **new this pass**.
  Simulated disbursement: flips `loans.status` to `disbursed`. Requires
  both guarantors to already be `confirmed`. No money moves anywhere —
  same "real payload shape, simulated" pattern as everything else
  access-constrained in this build. Required before a pharmacy claim can
  be submitted against the loan; nothing in the prior build had this
  transition, so claims had nothing to gate against until now.
- `POST /api/guarantors/{id}/confirm` / `/decline` — phone-match auth,
  explicitly flagged as a placeholder (see file comments) pending a
  signed one-time SMS token, which depends on the Africa's Talking SMS
  integration (depth-layer item, not built yet).
- `GET /api/wema/account-lookup/{account_number}` (role: chw) — live
  call to the ALAT Playground sandbox, Wallet Services / Get Wallet
  Details. Lookup/balance only, no creation endpoint wired up (would
  need a real BVN/NIN, which conflicts with the locked decision to keep
  NIN simulated).
- `POST /api/claims` (role: pharmacy) — **new this pass**. Pharmacy
  submits `loan_id` + `claim_amount`; backend pulls `cost_estimate` off
  the linked consultation, computes variance, and either matches
  (`match_status='matched'`, simulated payout) or blocks entirely
  (`match_status='variance_flagged'`, a `fraud_flags` row raised for
  admin review, no payout). Threshold is 15%, a decision made this pass
  — see `app/api/claims.py`. Requires the pharmacy to be `verified` and
  the loan to already be `disbursed`.
- `GET /api/claims/{id}` (role: pharmacy) — scoped to the calling
  pharmacy's own claims.

## Next in the build order (per blueprint SS24)

Fraud rule engine (velocity, guarantor overlap — variance-based flagging
now exists) + the admin review console (pharmacy verification + fraud
flag review, tabbed, per blueprint SS9/SS20). `GET /api/claims/{id}` and
`GET /api/fraud-flags` for admin (all entities, not just own) are part
of that same piece of work, not built yet.

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
