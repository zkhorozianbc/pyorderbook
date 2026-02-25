"""Generate sample_orders.parquet — a realistic order flow for replay.

Run this once to create the parquet file:
    python examples/replay/generate_sample_data.py
"""

import random
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

random.seed(42)

SYMBOLS = ["AAPL", "GOOG", "TSLA"]
BASE_PRICES = {"AAPL": 150.0, "GOOG": 175.0, "TSLA": 250.0}

sides = []
symbols = []
prices = []
quantities = []

# Generate 200 orders with realistic price clustering around base prices
for i in range(200):
    symbol = random.choice(SYMBOLS)
    base = BASE_PRICES[symbol]
    side = random.choice(["bid", "ask"])

    # Bids cluster below base, asks cluster above
    if side == "bid":
        price = round(base - random.uniform(0.25, 3.0), 2)
    else:
        price = round(base + random.uniform(0.25, 3.0), 2)

    quantity = random.choice([10, 25, 50, 100, 200, 500])

    sides.append(side)
    symbols.append(symbol)
    prices.append(price)
    quantities.append(quantity)

schema = pa.schema([
    ("side", pa.utf8()),
    ("symbol", pa.utf8()),
    ("price", pa.float64()),
    ("quantity", pa.int64()),
])

table = pa.table({
    "side": sides,
    "symbol": symbols,
    "price": prices,
    "quantity": quantities,
}, schema=schema)

output = Path(__file__).parent / "sample_orders.parquet"
pq.write_table(table, output)
print(f"Wrote {len(table)} orders to {output}")
print(f"Schema:\n{table.schema}")
print(f"\nFirst 10 rows:")
preview = table.slice(0, 10)
for i in range(len(preview)):
    s, sym, px, qty = (preview.column(c)[i].as_py() for c in range(4))
    print(f"  {s:<4} {sym:<5} {px:>8.2f}  {qty:>4}")
