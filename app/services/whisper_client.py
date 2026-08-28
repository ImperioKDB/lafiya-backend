import requests
from app.core.config import settings

# Groq and OpenAI both expose the same multipart transcription contract
# (POST an audio file + model name, get back JSON with a "text" field) --
# Groq's endpoint is literally namespaced /openai/v1/... because it's
# built to be OpenAI-compatible. That means switching providers is a
# config change (WHISPER_PROVIDER + the matching API key), never a code
# change here.
#
# Groq is the default because it's free -- a generous per-day request
# quota, no card required -- and it hosts Whisper large-v3 on their own
# hardware, not a degraded model. Confirm current limits at
# console.groq.com/docs/rate-limits before a real pilot; hackathon/demo
# volume is comfortably inside them.
PROVIDER_CONFIG = {
    "groq": {
        "url": "https://api.groq.com/openai/v1/audio/transcriptions",
        "default_model": "whisper-large-v3-turbo",
        "api_key": lambda: settings.groq_api_key,
    },
    "openai": {
        "url": "https://api.openai.com/v1/audio/transcriptions",
        "default_model": "whisper-1",
        "api_key": lambda: settings.openai_api_key,
    },
}


class WhisperError(Exception):
    # Raised for anything that should surface as blueprint SS17's
    # "Couldn't reach Whisper -- saved to offline queue, will
    # transcribe on reconnect" state, never a silent hang.
    pass


def transcribe_audio(audio_bytes: bytes, filename: str) -> str:
    provider = settings.whisper_provider if settings.whisper_provider in PROVIDER_CONFIG else "groq"
    cfg = PROVIDER_CONFIG[provider]
    api_key = cfg["api_key"]()

    if not api_key:
        raise WhisperError(
            provider.upper() + "_API_KEY not configured (WHISPER_PROVIDER=" + provider + ")"
        )

    model = settings.whisper_model or cfg["default_model"]

    try:
        response = requests.post(
            cfg["url"],
            headers={"Authorization": "Bearer " + api_key},
            files={"file": (filename, audio_bytes)},
            data={"model": model},
            timeout=30,
        )
    except requests.RequestException as e:
        raise WhisperError("Could not reach " + provider + " transcription API: " + str(e))

    if response.status_code != 200:
        raise WhisperError(
            provider + " transcription API returned " + str(response.status_code) + ": " + response.text[:300]
        )

    try:
        payload = response.json()
    except ValueError:
        raise WhisperError(provider + " transcription API returned a non-JSON response")

    text = (payload.get("text") or "").strip()
    if not text:
        raise WhisperError(provider + " transcription API returned an empty transcript")

    return text
