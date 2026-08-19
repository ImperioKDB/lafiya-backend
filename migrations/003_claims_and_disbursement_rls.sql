-- LAFIYA migration 003 -- claims RLS + a missing loans UPDATE policy
-- Run this directly in the Supabase SQL Editor against project
-- ouujmuiyqndvsrtakxft (eu-west-1). Not applied by this push script --
-- same pattern as migration 002. Lives in the repo as a record only.

-- Pharmacy submits claims against their own pharmacy_id only.
create policy pharmacy_insert_own_claims
on disbursement_claims for insert
to authenticated
with check (
  exists (
    select 1 from pharmacies ph
    where ph.id = disbursement_claims.pharmacy_id
      and ph.auth_user_id = auth.uid()
  )
);

-- Pharmacy reads only its own submitted claims. Admin-wide read access
-- is part of the fraud-review console (build order item 7), not this
-- migration.
create policy pharmacy_read_own_claims
on disbursement_claims for select
to authenticated
using (
  exists (
    select 1 from pharmacies ph
    where ph.id = disbursement_claims.pharmacy_id
      and ph.auth_user_id = auth.uid()
  )
);

-- Needed for POST /api/loans/{loan_id}/disburse. The original schema
-- (blueprint SS11) never defined an UPDATE policy on loans -- only
-- insert/select existed via the chw_insert_own_patient_loans pattern.
-- Without this, the disburse endpoint's own status-flip update would
-- silently fail RLS with no visible row returned.
create policy chw_update_own_patient_loans
on loans for update
to authenticated
using (
  exists (
    select 1 from patients p
    join chws c on c.id = p.registered_by_chw_id
    where p.id = loans.patient_id
      and c.auth_user_id = auth.uid()
  )
)
with check (
  exists (
    select 1 from patients p
    join chws c on c.id = p.registered_by_chw_id
    where p.id = loans.patient_id
      and c.auth_user_id = auth.uid()
  )
);
