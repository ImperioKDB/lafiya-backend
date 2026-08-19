from datetime import datetime, timezone
from fastapi import APIRouter, Form
from fastapi.responses import PlainTextResponse
from app.core.config import settings
from app.core.supabase_client import get_service_client
from app.services.triage import score_urgency

router = APIRouter(prefix="/api/ussd", tags=["ussd"])

# Order matters here -- numeric menu choices 1-5 map onto these category
# keys positionally, matching the menu tree in Master Build Spec SS9.
# The scores themselves live in exactly one place (app/services/triage.py
# SYMPTOM_CATEGORIES) -- this list is only ever used for ORDER, never
# duplicates a score, so the two can't drift apart on values.
SYMPTOM_MENU_ORDER = ["fever_body_pain", "stomach_digestive", "pregnancy_related", "injury", "other"]


def _find_patient_by_phone(service_client, phone: str):
    # Phone isn't unique on patients (a household could plausibly share
    # one) -- most-recently-registered is the same "pick one, most
    # recent" convention already used for guarantor overlap detection
    # (app/fraud/rules.py). Good enough for sandbox/demo; a real
    # deployment would need a firmer patient-identification story over
    # USSD than "whoever registered last on this number."
    result = (
        service_client.table("patients")
        .select("*")
        .eq("phone", phone)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


@router.post("/webhook", response_class=PlainTextResponse)
# Africa's Talking's actual USSD callback has no signing/shared-secret
# mechanism -- confirmed against their developer docs before writing
# this. (The blueprint's SS14 security line about "verifying Africa's
# Talking's shared secret" doesn't map to a real feature of this
# product -- flagging that mismatch rather than fabricating a check that
# doesn't exist.) The only sanity check available is matching the
# incoming serviceCode against the one actually registered for this app
# -- exactly as much of a placeholder as the guarantor phone-match auth
# already flagged in app/api/guarantors.py.
#
# Session state is derived by re-parsing `text` on every request, not a
# server-side session table keyed by sessionId. Master Build Spec SS9
# suggested a session table for a menu "with real branching" -- the
# tree actually built here never goes past 2 levels, and Africa's
# Talking's own docs describe exactly this token-parsing approach as
# sufficient at that depth. Revisit if the tree grows deeper later.
def ussd_webhook(
    sessionId: str = Form(...),
    phoneNumber: str = Form(...),
    serviceCode: str = Form(...),
    text: str = Form(default=""),
):
    if settings.ussd_service_code and serviceCode != settings.ussd_service_code:
        return "END Service temporarily unavailable."

    service_client = get_service_client()
    parts = text.split("*") if text else []

    # ---- Main menu ----
    if len(parts) == 0:
        return (
            "CON Welcome to LAFIYA\n"
            "1. Report Symptom\n"
            "2. Check Loan Status\n"
            "3. Confirm Guarantor\n"
            "4. Request Doctor Callback\n"
            "5. Change Language"
        )

    choice = parts[0]

    # ---- 1. Report Symptom -- numeric category, feeds the identical
    # scorer the smartphone voice path uses (PRD SS6.7: single source of
    # truth, never forked per entry point). Category acts as a proxy
    # signal in place of a transcript -- coarser, but the same logic. ----
    if choice == "1":
        if len(parts) == 1:
            return (
                "CON Select symptom category\n"
                "1. Fever/Body pain\n"
                "2. Stomach/Digestive\n"
                "3. Pregnancy-related\n"
                "4. Injury\n"
                "5. Other"
            )
        if len(parts) == 2:
            patient = _find_patient_by_phone(service_client, phoneNumber)
            if not patient:
                return "END No patient record found for this number. Please register with your CHW first."

            category_choice = parts[1]
            if category_choice not in ("1", "2", "3", "4", "5"):
                return "END Invalid selection."
            category = SYMPTOM_MENU_ORDER[int(category_choice) - 1]

            scored = score_urgency(category, transcript=None)

            # No authenticated user on a USSD request -- service client,
            # bypassing the chw-scoped RLS the app's own consultation
            # insert relies on. This is a deliberate second entry point
            # into the same table, not a workaround for a blocked write.
            service_client.table("consultations").insert(
                {
                    "patient_id": patient["id"],
                    "transcript": None,
                    "urgency_score": scored["score"],
                    "status": "queued",
                }
            ).execute()

            return "END Symptom report received. A doctor will review your case soon."

        return "END Invalid selection."

    # ---- 2. Check Loan Status -- read-only, single-shot END ----
    if choice == "2":
        patient = _find_patient_by_phone(service_client, phoneNumber)
        if not patient:
            return "END No patient record found for this number."

        loans_result = (
            service_client.table("loans")
            .select("*")
            .eq("patient_id", patient["id"])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not loans_result.data:
            return "END No loan record found."

        loan = loans_result.data[0]
        return (
            "END Loan status: "
            + loan["status"]
            + ". Amount: NGN"
            + str(int(loan["amount"]))
            + ". Total repayable: NGN"
            + str(loan["total_repayable"])
        )

    # ---- 3. Confirm Guarantor -- writes to the same guarantors table
    # the app/SMS-link flow uses (app/api/guarantors.py), just a second
    # entry point into it, per PRD SS6.7. ----
    if choice == "3":
        pending_result = (
            service_client.table("guarantors")
            .select("*")
            .eq("guarantor_phone", phoneNumber)
            .eq("status", "pending")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        pending = pending_result.data[0] if pending_result.data else None

        if len(parts) == 1:
            if not pending:
                return "END No pending guarantor requests found for this number."
            return (
                "CON You have been asked to guarantee a LAFIYA loan.\n"
                "1. Confirm\n"
                "2. Decline"
            )

        if len(parts) == 2:
            if not pending:
                return "END This guarantor request is no longer pending."

            if parts[1] == "1":
                service_client.table("guarantors").update(
                    {"status": "confirmed", "confirmed_at": datetime.now(timezone.utc).isoformat()}
                ).eq("id", pending["id"]).execute()
                return "END Thank you, you have confirmed as guarantor."

            if parts[1] == "2":
                # No reputation penalty for declining, same as the
                # app/SMS-link path -- blueprint SS30.
                service_client.table("guarantors").update({"status": "declined"}).eq("id", pending["id"]).execute()
                return "END You have declined this guarantor request."

            return "END Invalid selection."

        return "END Invalid selection."

    # ---- 4. Request Doctor Callback -- flags the most recent
    # not-yet-completed case, single-shot END. Does not place a live
    # call -- that's Africa's Talking's separate Voice API, an explicit
    # non-decision per Master Build Spec SS9. ----
    if choice == "4":
        patient = _find_patient_by_phone(service_client, phoneNumber)
        if not patient:
            return "END No patient record found for this number."

        open_result = (
            service_client.table("consultations")
            .select("id")
            .eq("patient_id", patient["id"])
            .neq("status", "completed")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not open_result.data:
            return "END No open case found to flag for a callback."

        service_client.table("consultations").update({"callback_requested": True}).eq(
            "id", open_result.data[0]["id"]
        ).execute()
        return "END A doctor callback has been requested for your open case."

    # ---- 5. Change Language -- STUB. No language column exists
    # anywhere, no translated menu content exists anywhere in this
    # build. Multi-language is explicitly Secondary/Nice-to-have in
    # blueprint SS3, not MVP. This acknowledges the selection and does
    # nothing further with it -- flagged here plainly rather than
    # quietly persisting a preference nothing ever reads. ----
    if choice == "5":
        if len(parts) == 1:
            return (
                "CON Select language\n"
                "1. English\n"
                "2. Hausa\n"
                "3. Yoruba\n"
                "4. Igbo"
            )
        if len(parts) == 2:
            return "END Language preference noted. (Translated menus are not yet built.)"
        return "END Invalid selection."

    return "END Invalid selection. Please dial in again."
