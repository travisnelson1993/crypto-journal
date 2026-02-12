from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 🔑 CRITICAL: force SQLAlchemy to register ALL models
# This fixes ForeignKey resolution errors permanently
import app.models  # noqa: F401

# ----------------------------
# API Routers
# ----------------------------
from app.api import imports as imports_router
from app.api import stats as stats_router
from app.api import trades as trades_router
from app.api import positions as positions_router
from app.api import risk as risk_router

from app.api.analytics.summary import router as analytics_summary_router
from app.api.analytics.risk_warnings import router as risk_warnings_router
from app.api.analytics.discipline import router as discipline_router
from app.api.analytics.discipline_history import router as discipline_history_router
from app.api.analytics.discipline_correlation import (
    router as discipline_correlation_router,
)
from app.api.analytics.monthly_performance import (
    router as monthly_performance_router,
)

from app.api.journal import daily_router, trade_notes_router
from app.api.debug import router as debug_router

# -------------------------------------------------
# App
# -------------------------------------------------
app = FastAPI(
    title="Crypto Journal API",
    version="1.0.0",
)

# -------------------------------------------------
# CORS
# -------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------
# Core Domain Routers
# -------------------------------------------------
app.include_router(trades_router.router)
app.include_router(positions_router.router)
app.include_router(stats_router.router)
app.include_router(imports_router.router)

# -------------------------------------------------
# Analytics (Category 4)
# -------------------------------------------------
app.include_router(analytics_summary_router)
app.include_router(risk_warnings_router)
app.include_router(discipline_router)
app.include_router(discipline_history_router)
app.include_router(discipline_correlation_router)

# ADD THIS:
app.include_router(monthly_performance_router)

# -------------------------------------------------
# Risk / Controls
# -------------------------------------------------
app.include_router(risk_router.router)

# -------------------------------------------------
# Journaling (Phase 2A / 2B)
# -------------------------------------------------
app.include_router(daily_router)
app.include_router(trade_notes_router)

# -------------------------------------------------
# Debug (safe to remove later)
# -------------------------------------------------
app.include_router(debug_router)

# -------------------------------------------------
# Health check
# -------------------------------------------------
@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "ok"}

