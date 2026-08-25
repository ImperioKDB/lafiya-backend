from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
