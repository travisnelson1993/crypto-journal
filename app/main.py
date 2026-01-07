from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import imports as imports_router
from app.api import stats as stats_router
from app.api import trades as trades_router

app = FastAPI(title="Crypto Journal API")

# CORS – permissive for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(trades_router.router)
app.include_router(stats_router.router)
app.include_router(imports_router.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}

