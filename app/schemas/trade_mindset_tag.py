from datetime import datetime
from typing import List
from pydantic import BaseModel
from enum import Enum


class TradeMindsetTagEnum(str, Enum):
    fomo = "fomo"
    revenge = "revenge"
    hesitation = "hesitation"
    overconfidence = "overconfidence"
    fear = "fear"
    discipline = "discipline"
    patience = "patience"
    impulsive = "impulsive"


class TradeMindsetTagCreate(BaseModel):
    tag: TradeMindsetTagEnum


class TradeMindsetTagRead(BaseModel):
    id: int
    tag: TradeMindsetTagEnum
    created_at: datetime

    class Config:
        from_attributes = True


class TradeMindsetTagList(BaseModel):
    items: List[TradeMindsetTagRead]
