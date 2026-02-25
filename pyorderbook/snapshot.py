from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class SnapshotLevel:
    price: Decimal
    quantity: int


@dataclass
class Snapshot:
    bids: list[SnapshotLevel] = field(default_factory=list)
    asks: list[SnapshotLevel] = field(default_factory=list)
    spread: Decimal | None = None
    midpoint: Decimal | None = None
    bid_vwap: Decimal | None = None
    ask_vwap: Decimal | None = None
