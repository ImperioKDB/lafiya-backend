-- LAFIYA migration 002 -- consultations RLS + doctor_earnings table
-- Run this directly in the Supabase SQL Editor against project
-- ouujmuiyqndvsrtakxft (eu-west-1). Not applied by this push script --
-- DDL/RLS changes go straight to Supabase, same as the original schema
-- in blueprint SS11. This file lives in the repo as a record only.

create policy chw_insert_own_patient_consultations
on consultations for insert
to authenticated
with check (
  exists (
    select 1 from patients p
    join chws c on c.id = p.registered_by_chw_id
    where p.id = consultations.patient_id
      and c.auth_user_id = auth.uid()
  )
);

create policy chw_read_own_patient_consultations
on consultations for select
to authenticated
using (
  exists (
    select 1 from patients p
    join chws c on c.id = p.registered_by_chw_id
    where p.id = consultations.patient_id
      and c.auth_user_id = auth.uid()
  )
);

create policy doctor_read_queue_and_own
on consultations for select
to authenticated
using (
  doctor_id is null
  or exists (
    select 1 from doctors d
    where d.id = consultations.doctor_id
      and d.auth_user_id = auth.uid()
  )
);

create policy doctor_update_queue_and_own
on consultations for update
to authenticated
using (
  doctor_id is null
  or exists (
    select 1 from doctors d
    where d.id = consultations.doctor_id
      and d.auth_user_id = auth.uid()
  )
)
with check (
  exists (
    select 1 from doctors d
    where d.id = consultations.doctor_id
      and d.auth_user_id = auth.uid()
  )
);

create policy doctor_read_linked_patients
on patients for select
to authenticated
using (
  exists (
    select 1 from consultations c
    join doctors d on d.id = c.doctor_id
    where c.patient_id = patients.id
      and d.auth_user_id = auth.uid()
  )
);

create table doctor_earnings (
  id uuid primary key default gen_random_uuid(),
  doctor_id uuid not null references doctors(id),
  type text not null default 'stipend',
  amount numeric not null,
  related_entity_id uuid,
  status text not null default 'accrued',
  created_at timestamptz not null default now()
);

alter table doctor_earnings enable row level security;

create policy doctor_read_own_earnings
on doctor_earnings for select
to authenticated
using (
  exists (
    select 1 from doctors d
    where d.id = doctor_earnings.doctor_id
      and d.auth_user_id = auth.uid()
  )
);
