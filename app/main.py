from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import imports as imports_router
from app.api import stats as stats_router
from app.api import trades as trades_router
from app.api import positions as positions_router
from app.api.journal import router as journal_router
from app.api.analytics import router as analytics_router

app = FastAPI(title="Crypto Journal API")

# -------------------------------------------------
# CORS (permissive for local dev; restrict in prod)
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
app.include_router(journal_router)
app.include_router(analytics_router)

# -------------------------------------------------
# Health check (CI / uptime / sanity)
# -------------------------------------------------
@app.get("/health")
async def health_check():
    return {"status": "ok"}

