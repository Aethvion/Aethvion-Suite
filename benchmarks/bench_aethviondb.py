#!/usr/bin/env python
"""
benchmarks/bench_aethviondb.py
Reproducible Layer-1 benchmark for the AethvionDB engine.

Measures the deterministic core only — no LLM, no embeddings:
  • write throughput + point reads (the real per-entity ingestion path)
  • cold load (from snapshot) and warm load (from the in-memory cache)
  • full list, lite projection, and type / kind / tag retrieval
  • the O(1) generation-based freshness check

across entity-count scales. All data is synthetic and lives in a temp
directory — it never touches real AethvionDB data.

Run:
    .venv/Scripts/python.exe benchmarks/bench_aethviondb.py
    .venv/Scripts/python.exe benchmarks/bench_aethviondb.py --scales 10000,30000,100000 --writes 2000
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.aethviondb import snapshot                       # noqa: E402
from core.aethviondb.entity_writer import EntityWriter     # noqa: E402
from core.aethviondb.name_index import NameIndex           # noqa: E402

_TYPES = ["module", "class", "function", "concept", "person", "service", "decision"]
_KINDS = ["software.module", "software.class", "domain.concept", "people.person"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ms(fn, *a, **k):
    t = time.perf_counter()
    r = fn(*a, **k)
    return (time.perf_counter() - t) * 1000, r


def _make_entity(i: int, n: int) -> dict:
    """A realistically-sized synthetic entity (~1 KB serialised)."""
    return {
        "id":      "ws_" + uuid.uuid4().hex[:16],
        "type":    _TYPES[i % len(_TYPES)],
        "kind":    _KINDS[i % len(_KINDS)],
        "name":    f"Entity {i:08d}",
        "status":  "active",
        "version": 1,
        "created": _now(),
        "updated": _now(),
        "source":  "benchmark",
        "sections": {
            "core": {
                "summary":    f"Synthetic benchmark entity number {i}. " * 4,
                "aliases":    [],
                "categories": ["Benchmark"],
                "tags":       [f"tag{i % 50}", "benchmark"],
            },
            "timeline":   [],
            "relations":  [{"kind": "related_to", "target_id": f"ws_seed{(i + k) % n:08d}", "note": ""}
                           for k in (1, 2, 3)],
            "properties": {},
            "stubs":      [],
        },
    }


def bench_writes(k: int) -> dict:
    """Measure the real per-entity write path (file + index + gen + cache patch)."""
    tmp = Path(tempfile.mkdtemp(prefix="adb_bench_w_"))
    try:
        root = tmp / "db"
        ent  = root / "entities"
        w    = EntityWriter(entities_dir=ent, index=NameIndex(index_path=root / "name_index.json"))

        t = time.perf_counter()
        last_id = None
        for i in range(k):
            e, _ = w.create(
                f"Write {i:08d}", entity_type=_TYPES[i % len(_TYPES)],
                sections_override={"core": {"summary": f"entity {i}", "tags": ["benchmark"]}},
            )
            last_id = e["id"]
        total_s = time.perf_counter() - t

        get_id_ms,   _ = _ms(w.get, last_id)
        get_name_ms, _ = _ms(w.get_by_name, f"Write {k - 1:08d}")
        return {
            "count":        k,
            "total_s":      total_s,
            "per_write_ms": total_s / k * 1000,
            "writes_sec":   k / total_s,
            "get_id_ms":    get_id_ms,
            "get_name_ms":  get_name_ms,
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def bench_scale(n: int) -> dict:
    """Measure load + query at a fixed entity count, served from a snapshot."""
    tmp = Path(tempfile.mkdtemp(prefix="adb_bench_s_"))
    try:
        root = tmp / "db"
        ent  = root / "entities"
        ent.mkdir(parents=True, exist_ok=True)
        w = EntityWriter(entities_dir=ent, index=NameIndex(index_path=root / "name_index.json"))

        entities = [_make_entity(i, n) for i in range(n)]
        build_ms, _ = _ms(snapshot.build, root, entities)
        snap_mb = snapshot.snapshot_path(root).stat().st_size / 1_000_000

        snapshot._MEM.pop(str(root), None)                 # force cold
        cold_ms,  _ = _ms(w.list_all)                      # cold load from snapshot
        warm_ms,  _ = _ms(w.list_all)                      # served from cache
        lite_cold_ms, _ = _ms(w.list_lite)                 # first lite projection
        lite_warm_ms, _ = _ms(w.list_lite)                 # cached lite
        type_ms,  _ = _ms(w.search_by_type, "module")
        kind_ms,  _ = _ms(w.search_by_kind, "software.module")
        tag_ms,   _ = _ms(w.search_by_tag, "benchmark")    # matches all → worst case

        t = time.perf_counter()
        for _ in range(1000):
            snapshot.is_fresh(root, ent)
        fresh_us = (time.perf_counter() - t) / 1000 * 1_000_000

        return {
            "n": n, "snap_mb": snap_mb, "build_ms": build_ms,
            "cold_ms": cold_ms, "warm_ms": warm_ms,
            "lite_cold_ms": lite_cold_ms, "lite_warm_ms": lite_warm_ms,
            "type_ms": type_ms, "kind_ms": kind_ms, "tag_ms": tag_ms,
            "fresh_us": fresh_us,
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scales", default="10000,30000,100000")
    ap.add_argument("--writes", type=int, default=2000)
    args = ap.parse_args()
    scales = [int(s) for s in args.scales.split(",") if s.strip()]

    try:
        sys.stdout.reconfigure(encoding="utf-8")           # avoid cp1252 issues on Windows
    except Exception:
        pass

    print(f"\nAethvionDB Layer-1 benchmark - {_now()}")
    print(f"Python {sys.version.split()[0]} | platform {sys.platform}\n")

    w = bench_writes(args.writes)
    print("## Write path (real per-entity ingestion)\n")
    print(f"- {w['count']:,} creates in {w['total_s']:.2f}s "
          f"-> {w['writes_sec']:,.0f} writes/s ({w['per_write_ms']:.2f} ms/write)")
    print(f"- get by id: {w['get_id_ms']:.2f} ms | get by name: {w['get_name_ms']:.2f} ms\n")

    print("## Load + query by scale\n")
    hdr = ("entities", "snapshot", "cold load", "warm load", "lite warm",
           "by type", "by kind", "by tag", "freshness")
    print("| " + " | ".join(hdr) + " |")
    print("|" + "|".join(["---"] * len(hdr)) + "|")
    for n in scales:
        r = bench_scale(n)
        print(f"| {r['n']:,} | {r['snap_mb']:.1f} MB | {r['cold_ms']:.0f} ms | "
              f"{r['warm_ms']:.1f} ms | {r['lite_warm_ms']:.1f} ms | {r['type_ms']:.1f} ms | "
              f"{r['kind_ms']:.1f} ms | {r['tag_ms']:.1f} ms | {r['fresh_us']:.1f} us |")
    print()


if __name__ == "__main__":
    main()
