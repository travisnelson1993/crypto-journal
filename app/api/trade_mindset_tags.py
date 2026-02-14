from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_db
from app.models.trade_mindset_tag import TradeMindsetTag
from app.models.trade_note import TradeNote
from app.schemas.trade_mindset_tag import (
    TradeMindsetTagCreate,
    TradeMindsetTagRead,
    TradeMindsetTagList,
)

router = APIRouter(
    prefix="/api/trade-notes",
    tags=["trade-mindset-tags"],
)
