# README and Examples Refresh Design

## Goal

Make PyOrderBook easy to understand in a few minutes by turning the README into a short landing page and making the examples directory the primary learning path.

## Audience

The primary reader is a Python developer evaluating the package from GitHub or PyPI. They should quickly understand that PyOrderBook is a Rust-backed limit order book and matching engine, how to install it, how matching works at a glance, and which example to run next.

## README Shape

The README will be concise and scannable:

- A one-sentence description and badges.
- A compact feature list focused on developer decisions.
- Installation commands for `pip` and `uv`.
- A short quickstart that demonstrates standing liquidity, an incoming order, trades, order status, and an L2 snapshot.
- A plain-language mental model of `Book`, `Order`, `TradeBlotter`, and `Snapshot`.
- A curated examples table with exact commands.
- A short development section with local test commands.
- License.

The README will avoid duplicating every property and method. API details stay discoverable through examples and source names.

## Examples Shape

The examples directory will be flattened into runnable scripts from the repository root:

- `examples/basic_matching.py`: price-time priority, partial fills, FIFO at one price level, and cancellation.
- `examples/l2_snapshot.py`: depth snapshots, spread, midpoint, side VWAP, and aggregated quantities.
- `examples/parquet_replay.py`: replay event rows from Parquet and summarize final book state.
- `examples/generate_sample_parquet.py`: regenerate the sample Parquet dataset used by the replay example.
- `examples/sample_orders.parquet`: small committed sample data file used by the replay example.

The examples will print compact, stable output. They will use top-level `bid` and `ask` helpers for readability and avoid internal implementation details unless the example is explicitly about inspection.

## Compatibility

The change is documentation and examples only. It does not change matching behavior, package metadata, public API, or backend selection.

## Verification

Verification will run the examples from the repository root. The Parquet examples require `pyarrow`; if it is unavailable, the replay/generation examples should exit with clear guidance rather than a confusing import traceback.
