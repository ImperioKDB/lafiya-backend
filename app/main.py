from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import health, patients

app = FastAPI(title="LAFIYA API", version="0.1.0")

# Wide open for now since the frontend URL isn't deployed yet — tighten
# this to the real Vercel origin before the demo, not after.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(patients.router)
