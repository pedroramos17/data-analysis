"""Small enums shared by finance modules."""

from __future__ import annotations

from enum import Enum


class DataLayer(str, Enum):
    """Durable finance dataset layers."""

    RAW = "raw"
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"


class AssetClass(str, Enum):
    """Common asset classes used by canonical records."""

    EQUITY = "equity"
    FUTURE = "future"
    OPTION = "option"
    FX = "fx"
    CRYPTO = "crypto"
    MACRO = "macro"
