from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class SnapshotLevel:
    price: Decimal
    quantity: int

    def get_price(self) -> Decimal:
        return self.price

    def get_quantity(self) -> int:
        return self.quantity


@dataclass
class Snapshot:
    bids: list[SnapshotLevel] = field(default_factory=list)
    asks: list[SnapshotLevel] = field(default_factory=list)
    spread: Decimal | None = None
    midpoint: Decimal | None = None
    bid_vwap: Decimal | None = None
    ask_vwap: Decimal | None = None

    def get_bids(self) -> list[SnapshotLevel]:
        return self.bids

    def get_asks(self) -> list[SnapshotLevel]:
        return self.asks

    def get_spread(self) -> Decimal | None:
        return self.spread

    def get_midpoint(self) -> Decimal | None:
        return self.midpoint

    def get_bid_vwap(self) -> Decimal | None:
        return self.bid_vwap

    def get_ask_vwap(self) -> Decimal | None:
        return self.ask_vwap
