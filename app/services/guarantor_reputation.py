# Single source of truth for applying a reputation hit + one-strike bar
# to a guarantor phone number. Blueprint SS1/00_START_HERE: one confirmed
# default = barred from future guarantees. Two triggers call this and
# must never drift apart:
#   - app/api/loans.py -- a loan's own disbursed -> defaulted transition
#   - app/api/admin.py -- an admin confirming fraud on an
#     entity_type='guarantor' flag
#
# Same "single logic path behind multiple entry points" pattern already
# used for the triage scorer (app/services/triage.py) -- don't fork this
# into two copies if a third trigger shows up later.


def apply_reputation_bar(service_client, guarantor_phone: str) -> None:
    rep = (
        service_client.table("guarantor_reputation")
        .select("id, default_count")
        .eq("guarantor_phone", guarantor_phone)
        .execute()
    )
    if rep.data:
        service_client.table("guarantor_reputation").update(
            {"default_count": rep.data[0]["default_count"] + 1, "barred": True}
        ).eq("guarantor_phone", guarantor_phone).execute()
    else:
        service_client.table("guarantor_reputation").insert(
            {"guarantor_phone": guarantor_phone, "default_count": 1, "barred": True}
        ).execute()
