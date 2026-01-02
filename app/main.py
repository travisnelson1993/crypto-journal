from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# import your routers
from app.api import imports as imports_router
from app.api import stats as stats_router
from app.api import trades as trades_router

# Import your async engine and your Base metadata.
# Adjust these imports if your database module uses different names.
# Expected: app/db/database.py exports `engine` (an AsyncEngine) and app/models/trade.py exports `Base`.
from app.db.database import engine
from app.models.trade import Base

app = FastAPI(title="Crypto Journal API")

# CORS - keep permissive for local dev, lock down in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # change to your frontend origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# include the trades router (prefix defined in the router)
app.include_router(trades_router.router)
app.include_router(stats_router.router)
app.include_router(imports_router.router)


@app.on_event("startup")
async def on_startup():
    """
    Create DB tables on startup (development convenience).
    For production use Alembic migrations instead.
    """
    try:
        async with engine.begin() as conn:
            # run_sync will execute the sync create_all on the sync metadata
            await conn.run_sync(Base.metadata.create_all)
        print("Database tables ensured (create_all).")
    except Exception as exc:
        # print so you can see errors in the logs during dev
        print("Error creating tables on startup:", exc)
