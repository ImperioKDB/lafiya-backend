import requests
from app.core.config import settings

# OpenAI's hosted Whisper endpoint -- blueprint SS27 lists "Whisper
# (OpenAI API or self-hosted)"; this is the OpenAI-API path. Swap this
# client for a self-hosted call later without touching the caller in
# app/api/consultations.py -- transcribe_audio() is the whole contract.
WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"


class WhisperError(Exception):
    # Raised for anything that should surface as blueprint SS17's
    # "Couldn't reach Whisper -- saved to offline queue, will
    # transcribe on reconnect" state, never a silent hang.
    pass


def transcribe_audio(audio_bytes: bytes, filename: str) -> str:
    if not settings.openai_api_key:
        raise WhisperError("OPENAI_API_KEY not configured")

    try:
        response = requests.post(
            WHISPER_URL,
            headers={"Authorization": "Bearer " + settings.openai_api_key},
            files={"file": (filename, audio_bytes)},
            data={"model": "whisper-1"},
            timeout=30,
        )
    except requests.RequestException as e:
        raise WhisperError("Could not reach Whisper: " + str(e))

    if response.status_code != 200:
        raise WhisperError(
            "Whisper API returned " + str(response.status_code) + ": " + response.text[:300]
        )

    try:
        payload = response.json()
    except ValueError:
        raise WhisperError("Whisper API returned a non-JSON response")

    text = (payload.get("text") or "").strip()
    if not text:
        raise WhisperError("Whisper API returned an empty transcript")

    return text
