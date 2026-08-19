from datetime import datetime, timedelta, timezone

# Blueprint SS4/SS29 name "velocity" and "guarantor overlap" as
# rule-based fraud signals but never pin down numbers. Both thresholds
# below are decisions made in this pass, not restated from spec --
# change the constants if a different number is wanted.
#
# Both checks FLAG for admin review, they do not block. Only claim
# variance blocks anything (app/api/claims.py) -- match_status is the
# real payout gate there, and there's no equivalent gate on loans or
# guarantors. Velocity/overlap are softer signals a human should weigh,
# consistent with every other check in this build being human-gated
# rather than auto-resolving (blueprint SS30 / 00_START_HERE decisions).

LOAN_VELOCITY_WINDOW_HOURS = 24
LOAN_VELOCITY_THRESHOLD = 5  # more than this many loans by one CHW in the window raises a flag

GUARANTOR_OVERLAP_THRESHOLD = 3  # more than this many simultaneous active guarantees on one phone raises a flag


def check_loan_velocity(service_client, chw_id: str, new_loan_id: str) -> None:
    # Two simple queries rather than an embedded-resource join -- matches
    # the query style already used elsewhere in this codebase (no
    # postgrest embedded joins anywhere else), and keeps this readable
    # over being maximally efficient at hackathon scale.
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=LOAN_VELOCITY_WINDOW_HOURS)).isoformat()

    patients_result = service_client.table("patients").select("id").eq("registered_by_chw_id", chw_id).execute()
    patient_ids = [p["id"] for p in (patients_result.data or [])]
    if not patient_ids:
        return

    recent_result = (
        service_client.table("loans")
        .select("id")
        .in_("patient_id", patient_ids)
        .gte("created_at", cutoff)
        .execute()
    )
    count = len(recent_result.data or [])

    if count > LOAN_VELOCITY_THRESHOLD:
        service_client.table("fraud_flags").insert(
            {
                "entity_type": "loan",
                "entity_id": new_loan_id,
                "reason": (
                    "Velocity: this CHW has originated "
                    + str(count)
                    + " loans in the past "
                    + str(LOAN_VELOCITY_WINDOW_HOURS)
                    + "h (threshold "
                    + str(LOAN_VELOCITY_THRESHOLD)
                    + ")"
                ),
                "status": "open",
            }
        ).execute()


def check_guarantor_overlap(service_client, guarantor_phone: str, guarantor_row_id: str) -> None:
    active_result = (
        service_client.table("guarantors")
        .select("id")
        .eq("guarantor_phone", guarantor_phone)
        .in_("status", ["pending", "confirmed"])
        .execute()
    )
    count = len(active_result.data or [])

    if count > GUARANTOR_OVERLAP_THRESHOLD:
        service_client.table("fraud_flags").insert(
            {
                "entity_type": "guarantor",
                "entity_id": guarantor_row_id,
                "reason": (
                    guarantor_phone
                    + " is an active guarantor on "
                    + str(count)
                    + " loans simultaneously (threshold "
                    + str(GUARANTOR_OVERLAP_THRESHOLD)
                    + ") -- possible professional-guarantor pattern undermining real liability"
                ),
                "status": "open",
            }
        ).execute()
