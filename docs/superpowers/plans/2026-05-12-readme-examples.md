# README and Examples Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework PyOrderBook's README into a short landing page and refresh the examples into a curated, runnable learning path.

**Architecture:** The package API remains unchanged. Documentation moves from inline API reference toward fast orientation, while examples become focused scripts that demonstrate matching, snapshots, and Parquet replay.

**Tech Stack:** Markdown, Python 3.11+, PyOrderBook public API, optional `pyarrow` for Parquet examples.

---

## File Structure

- Modify `README.md`: concise landing page with quickstart and examples index.
- Create `examples/basic_matching.py`: basic matching, partial fill, FIFO, cancel.
- Create `examples/l2_snapshot.py`: L2 depth and snapshot metrics.
- Create `examples/parquet_replay.py`: replay committed Parquet sample and print final state.
- Create `examples/generate_sample_parquet.py`: regenerate `examples/sample_orders.parquet`.
- Keep `examples/sample_orders.parquet`: committed sample dataset for replay.
- Remove old nested example scripts after replacing them with flat scripts.

## Task 1: Rewrite README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace reference-style README with landing-page content**

Use sections in this order: title, description, badges, features, install, quickstart, mental model, examples table, development, license.

- [ ] **Step 2: Keep quickstart runnable**

The quickstart imports only `Book`, `ask`, and `bid`, then prints trades and an L2 snapshot.

- [ ] **Step 3: Link examples with exact commands**

Use commands:

```sh
python examples/basic_matching.py
python examples/l2_snapshot.py
python examples/parquet_replay.py
python examples/generate_sample_parquet.py
```

## Task 2: Replace Example Layout

**Files:**
- Create: `examples/basic_matching.py`
- Create: `examples/l2_snapshot.py`
- Create: `examples/parquet_replay.py`
- Create: `examples/generate_sample_parquet.py`
- Delete: `examples/basic/matching.py`
- Delete: `examples/snapshots/snapshot_demo.py`
- Delete: `examples/replay/replay_and_snapshot.py`
- Delete: `examples/replay/generate_sample_data.py`

- [ ] **Step 1: Create flat scripts with small docstrings**

Each script should run from the repository root and print compact output.

- [ ] **Step 2: Move sample data path**

Regenerate or move the sample Parquet dataset to `examples/sample_orders.parquet`. The replay script should read that path.

- [ ] **Step 3: Add optional dependency guidance**

Parquet scripts should catch missing `pyarrow` and raise `SystemExit` with this message:

```text
This example requires pyarrow. Install it with: pip install pyarrow
```

## Task 3: Verify Documentation Examples

**Files:**
- No source edits expected after this task unless verification exposes a problem.

- [ ] **Step 1: Run non-Parquet examples**

```sh
python examples/basic_matching.py
python examples/l2_snapshot.py
```

Expected: both commands exit 0 and print matching/snapshot summaries.

- [ ] **Step 2: Run Parquet examples when pyarrow is available**

```sh
python examples/generate_sample_parquet.py
python examples/parquet_replay.py
```

Expected: both commands exit 0. If `pyarrow` is missing, the command exits with the clear install message.

- [ ] **Step 3: Run targeted tests**

```sh
pytest tests/test_order_book.py -q
```

Expected: tests pass. If the Rust backend is not built locally, use the existing environment behavior and report the exact blocker.
