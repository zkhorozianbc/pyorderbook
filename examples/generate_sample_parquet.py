"""Generate the small deterministic Parquet dataset used by parquet_replay.py."""

from pathlib import Path

PYARROW_HELP = "This example requires pyarrow. Install it with: pip install pyarrow"

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError as exc:
    raise SystemExit(PYARROW_HELP) from exc


ROWS = [
    {"side": "ask", "symbol": "AAPL", "price": 150.00, "quantity": 100},
    {"side": "ask", "symbol": "AAPL", "price": 151.00, "quantity": 50},
    {"side": "bid", "symbol": "AAPL", "price": 151.00, "quantity": 120},
    {"side": "bid", "symbol": "AAPL", "price": 149.50, "quantity": 80},
    {"side": "ask", "symbol": "AAPL", "price": 149.50, "quantity": 40},
    {"side": "bid", "symbol": "MSFT", "price": 300.00, "quantity": 40},
    {"side": "bid", "symbol": "MSFT", "price": 300.00, "quantity": 60},
    {"side": "ask", "symbol": "MSFT", "price": 299.00, "quantity": 70},
    {"side": "ask", "symbol": "TSLA", "price": 250.00, "quantity": 20},
    {"side": "bid", "symbol": "TSLA", "price": 249.00, "quantity": 30},
]


def main() -> None:
    output = Path(__file__).with_name("sample_orders.parquet")
    schema = pa.schema(
        [
            ("side", pa.utf8()),
            ("symbol", pa.utf8()),
            ("price", pa.float64()),
            ("quantity", pa.int64()),
        ]
    )
    table = pa.table(
        {
            "side": [row["side"] for row in ROWS],
            "symbol": [row["symbol"] for row in ROWS],
            "price": [row["price"] for row in ROWS],
            "quantity": [row["quantity"] for row in ROWS],
        },
        schema=schema,
    )

    pq.write_table(table, output)
    print(f"wrote {len(ROWS)} rows to {output}")


if __name__ == "__main__":
    main()
