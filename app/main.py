from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from app.api import health, patients, consultations, loans, guarantors, wema, claims, admin, ussd, me, earnings

app = FastAPI(title="LAFIYA API", version="0.1.0")

# Locked down now that a real frontend exists (was wide open with a
# "tighten before demo" note -- this is that moment, not deferred
# again). Covers the production Vercel URL, Vercel's preview-deployment
# subdomains for this project via regex (format:
# lafiya-frontend-<hash>-<team>.vercel.app), and local Vite dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://lafiya-frontend.vercel.app",
        "http://localhost:5173",
    ],
    allow_origin_regex=r"https://lafiya-frontend-.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# NEW -- fixes a real crash, not a style preference. FastAPI's default
# RequestValidationError handler calls jsonable_encoder on exc.errors(),
# which includes the raw request body under "input". If a client posts
# a body FastAPI can't bind to the declared parameter type (e.g. the
# Triage screen's voice-capture path sending multipart/form-data with
# raw audio bytes to an endpoint that expects a JSON body), that "input"
# value can contain bytes that aren't valid UTF-8 -- jsonable_encoder's
# default bytes handling (o.decode()) then raises UnicodeDecodeError
# with no handler for it, which crashes the whole ASGI response and
# surfaces to the client as a bare connection failure ("Failed to
# fetch"), not a clean error. This handler prevents that crash outright,
# and additionally gives a specific, honest message for the multipart
# case instead of a generic validation error -- live Whisper/audio
# wiring isn't built yet (see backend README), so this tells the truth
# about that rather than pretending the upload was accepted.
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        return JSONResponse(
            status_code=415,
            content={
                "detail": (
                    "This endpoint doesn't accept audio uploads yet -- "
                    "live voice transcription isn't wired up on this build. "
                    "Please switch to typing and try again."
                )
            },
        )

    def _sanitize(obj):
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="replace")
        if isinstance(obj, dict):
            return {k: _sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_sanitize(v) for v in obj]
        return obj

    safe_errors = _sanitize(exc.errors())
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(safe_errors)})


app.include_router(health.router)
app.include_router(patients.router)
app.include_router(consultations.router)
app.include_router(loans.router)
app.include_router(guarantors.router)
app.include_router(wema.router)
app.include_router(claims.router)
app.include_router(admin.router)
app.include_router(ussd.router)
app.include_router(me.router)
app.include_router(earnings.router)
