from enum import Enum


class TradeDirection(str, Enum):
    SPOT = "SPOT"
    LONG = "LONG"
    SHORT = "SHORT"
