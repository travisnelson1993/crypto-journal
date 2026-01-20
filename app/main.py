from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 🔑 CRITICAL: force SQLAlchemy to register ALL models
# This fixes ForeignKey resolution errors permanently
import app.models  # noqa: F401

from app.api import imports as imports_router
from app.api import stats as stats_router
from app.api import trades as trades_router
from app.api import positions as positions_router
from app.api.analytics.risk_warnings import router as risk_warnings_router
from app.api.journal import daily_router, trade_notes_router
from app.api.debug import router as debug_router


# -------------------------------------------------
# App
# -------------------------------------------------
app = FastAPI(title="Crypto Journal API")

# -------------------------------------------------
# CORS
# -------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------
# Routers
# -------------------------------------------------
app.include_router(trades_router.router)
app.include_router(stats_router.router)
app.include_router(imports_router.router)
app.include_router(positions_router.router)
app.include_router(risk_warnings_router)

# Journaling (Phase 2A / 2B)
app.include_router(daily_router)
app.include_router(trade_notes_router)

# Debug (temporary but safe)
app.include_router(debug_router)

# -------------------------------------------------
# Health check
# -------------------------------------------------
@app.get("/health")
async def health_check():
    return {"status": "ok"}

