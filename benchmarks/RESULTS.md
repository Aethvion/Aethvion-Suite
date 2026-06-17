# AethvionDB Layer-1 Benchmark Results

Reproduce: `python benchmarks/bench_aethviondb.py`

Environment: Python 3.10.11, Windows (win32), 2026-06-17. Synthetic entities
(~730 B each — typed, with a summary, tags, and 3 relations). Numbers are
machine-dependent; rerun locally for your hardware. Measures the **deterministic
Layer-1 core only** (no LLM, no embeddings).

## Load + query by scale (served from snapshot → in-memory cache)

| entities | snapshot | cold load | warm load | lite (warm) | by type | by kind | by tag\* | freshness |
|---|---|---|---|---|---|---|---|---|
| 10,000  | 7.3 MB  | 61 ms  | 0.6 ms | 0.6 ms | 1.0 ms | 1.4 ms | 4.1 ms  | 0.22 ms |
| 30,000  | 21.9 MB | 240 ms | 2.1 ms | 2.4 ms | 3.7 ms | 4.7 ms | 14.2 ms | 0.23 ms |
| 100,000 | 73.0 MB | 825 ms | 8.1 ms | 8.9 ms | 14.2 ms | 17.6 ms | 48.4 ms | 0.23 ms |

\* "by tag" here matches **every** entity — worst-case full scan.

- **Cold load** — first read after process start / DB switch (parses the snapshot
  once; in the app this runs off the event loop, so the UI never blocks).
- **Warm load** — served from the in-memory cache: single-digit ms even at 100k.
- **Freshness** — the O(1) generation check stays ~0.2 ms **flat** across all
  scales, replacing the old per-file `stat()` scan that grew with entity count.

## Write path (incremental, real per-entity ingestion)

- 2,000 creates → **~193 writes/s (~5.2 ms/write)**; get-by-id ~4 ms, get-by-name ~0.2 ms.
- Each create performs three atomic file writes (entity + name-index + generation
  counter). That's fine for **incremental agent writes** (memory, plans, tasks),
  but **bulk ingestion is write-bound**: importing 100k entities one-by-one would
  take minutes. A future batch path (defer the index save, build the snapshot
  once) is the obvious optimization for large imports — the core is currently
  read-optimized.
