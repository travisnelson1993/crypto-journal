from fastapi import APIRouter
from app.db.database import Base

router = APIRouter(prefix="/debug")


@router.get("/tables")
def list_tables():
    return sorted(Base.metadata.tables.keys())
