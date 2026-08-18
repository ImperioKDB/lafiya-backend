from typing import Optional

# Rule-based urgency scorer -- blueprint SS4 / PRD SS6.7: this is the
# single source of truth used by BOTH the smartphone voice-transcript
# path and the USSD numeric-category fallback. Never fork this logic
# per entry point -- if the two paths ever need different behavior,
# that's a parameter to this function, not a second implementation.
#
# This is explicitly NOT a diagnosis. It never names a condition or
# recommends treatment -- it only sorts the doctor's queue by how
# quickly a case likely needs attention.

# Matches the USSD menu tree in Master Build Spec SS9 exactly -- these
# five values are the only valid symptom_category inputs from either
# entry point. Base score is a starting point on the live DB's 0-10
# scale (see consultations.urgency_score check constraint); transcript
# keywords (when available) can raise it, never lower it.
SYMPTOM_CATEGORIES = {
    "other": 2,
    "fever_body_pain": 4,
    "stomach_digestive": 4,
    "injury": 6,
    "pregnancy_related": 8,
}

MAX_SCORE = 10

# Presence of any of these in a free-text transcript forces the case to
# the top of the queue regardless of category -- these are patterns a
# CHW should already be trained to relay verbally, not an AI diagnosis.
CRITICAL_KEYWORDS = [
    "unconscious", "not breathing", "can't breathe", "cannot breathe",
    "severe bleeding", "heavy bleeding", "convulsion", "convulsing",
    "seizure", "chest pain", "unresponsive",
]

# Presence of any of these nudges the score up, capped at MAX_SCORE.
ELEVATED_KEYWORDS = [
    "severe", "worsening", "high fever", "blood", "vomiting blood",
    "can't stand", "can't walk", "fainted",
]


def _label(score: int) -> str:
    if score >= 9:
        return "critical"
    if score >= 7:
        return "high"
    if score >= 5:
        return "elevated"
    if score >= 3:
        return "moderate"
    return "low"


def score_urgency(symptom_category: str, transcript: Optional[str] = None) -> dict:
    category = (symptom_category or "").strip().lower()
    if category not in SYMPTOM_CATEGORIES:
        category = "other"

    score = SYMPTOM_CATEGORIES[category]
    signals = []

    if transcript:
        text = transcript.lower()

        if any(kw in text for kw in CRITICAL_KEYWORDS):
            score = MAX_SCORE
            signals.append("critical_keyword_match")
        elif any(kw in text for kw in ELEVATED_KEYWORDS):
            score = min(score + 2, MAX_SCORE)
            signals.append("elevated_keyword_match")

    return {
        "score": score,
        "level": _label(score),
        "signals": signals,
    }
