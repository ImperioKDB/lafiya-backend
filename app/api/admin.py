from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import require_role
from app.core.supabase_client import get_service_client
from app.models.common import CurrentUser
from app.models.admin import PharmacyOut, PharmacyStatusUpdate, FraudFlagOut, FraudFlagStatusUpdate
from app.services.guarantor_reputation import apply_reputation_bar

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Admin has no chws/doctors/pharmacies row -- role is resolved from the
# ADMIN_EMAILS allowlist (app/core/auth.py). Per blueprint SS13, "admin
# bypasses via a service-role check on the fraud/pharmacy endpoints
# only" -- every read/write in this file goes through
# get_service_client() for that reason. There is no admin-scoped RLS
# policy anywhere on purpose, and none should be added here.


@router.get("/pharmacies", response_model=list[PharmacyOut])
def list_pharmacies(status: Optional[str] = None, user: CurrentUser = Depends(require_role("admin"))):
    service_client = get_service_client()
    query = service_client.table("pharmacies").select("*")
    if status:
        query = query.eq("status", status)
    result = query.order("created_at", desc=False).execute()
    return result.data or []


@router.patch("/pharmacies/{pharmacy_id}", response_model=PharmacyOut)
# PRD SS6.8 -- only status='verified' pharmacies are selectable anywhere
# in the patient/CHW flow, enforced at claim-submission time in
# app/api/claims.py. No rejection_reason column exists on the live
# table -- confirmed against information_schema before writing this,
# the Master Build Spec's alter-table for it was never actually applied
# to this DB. Rejection reasoning stays out of band (a message to the
# pharmacy directly) until that's added as its own deliberate migration.
def update_pharmacy_status(
    pharmacy_id: str, payload: PharmacyStatusUpdate, user: CurrentUser = Depends(require_role("admin"))
):
    service_client = get_service_client()
    result = (
        service_client.table("pharmacies")
        .update({"status": payload.status})
        .eq("id", pharmacy_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Pharmacy not found")
    return result.data[0]


@router.get("/fraud-flags", response_model=list[FraudFlagOut])
def list_fraud_flags(status: Optional[str] = "open", user: CurrentUser = Depends(require_role("admin"))):
    service_client = get_service_client()
    query = service_client.table("fraud_flags").select("*")
    if status:
        query = query.eq("status", status)
    result = query.order("created_at", desc=True).execute()
    return result.data or []


@router.patch("/fraud-flags/{flag_id}", response_model=FraudFlagOut)
# Blueprint SS4/SS30 -- reviewed/cleared/confirmed_fraud, admin-gated,
# nothing auto-resolves. Confirming fraud on an entity_type='guarantor'
# flag (raised by the overlap check in app/fraud/rules.py) applies the
# same one-strike bar used for a loan default -- now via the shared
# apply_reputation_bar helper (app/services/guarantor_reputation.py) so
# this cascade and the loan-default cascade in app/api/loans.py can
# never drift apart.
def update_fraud_flag_status(
    flag_id: str, payload: FraudFlagStatusUpdate, user: CurrentUser = Depends(require_role("admin"))
):
    service_client = get_service_client()

    existing = service_client.table("fraud_flags").select("*").eq("id", flag_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Fraud flag not found")
    flag = existing.data[0]

    update_result = (
        service_client.table("fraud_flags")
        .update({"status": payload.status})
        .eq("id", flag_id)
        .execute()
    )
    if not update_result.data:
        raise HTTPException(status_code=500, detail="Could not update fraud flag")

    if payload.status == "confirmed_fraud" and flag["entity_type"] == "guarantor":
        guarantor_row = (
            service_client.table("guarantors")
            .select("guarantor_phone")
            .eq("id", flag["entity_id"])
            .execute()
        )
        if guarantor_row.data:
            apply_reputation_bar(service_client, guarantor_row.data[0]["guarantor_phone"])

    return update_result.data[0]
