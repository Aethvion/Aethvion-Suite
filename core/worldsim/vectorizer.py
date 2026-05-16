"""
core/worldsim/vectorizer.py
════════════════════════════
Generate and store embedding vectors for AethvionDB entities.

Vectors are stored inside the entity sections:
  entity["sections"]["vectors"] = {
      "text-embedding-004": {
          "embedding":    [...floats...],
          "model":        "text-embedding-004",
          "dimensions":   768,
          "generated_at": "ISO-8601",
          "input":        "first 300 chars of what was embedded"
      }
  }

Persistence: AethvionDB.VECINFO (JSON sidecar in db root)
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .entity_writer import EntityWriter

logger = logging.getLogger(__name__)

_VEC_INFO_FILE = "AethvionDB.VECINFO"

# ── In-process task tracking ───────────────────────────────────────────────────

_vec_tasks: dict[str, asyncio.Task] = {}   # str(db_root) → Task

# ── Embedding model registry ───────────────────────────────────────────────────

EMBEDDING_MODELS: dict[str, dict] = {
    "text-embedding-004": {
        "provider":   "google",
        "dimensions": 768,
    },
    "embedding-001": {
        "provider":   "google",
        "dimensions": 768,
    },
}


# ── State helpers ──────────────────────────────────────────────────────────────

def is_vectorizing(db_root: Path) -> bool:
    return str(db_root) in _vec_tasks


# ── Info sidecar ───────────────────────────────────────────────────────────────

def read_vec_info(db_root: Path) -> dict:
    """Return contents of AethvionDB.VECINFO, or {} if absent / unreadable."""
    p = db_root / _VEC_INFO_FILE
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def write_vec_info(db_root: Path, data: dict) -> None:
    """Persist data to AethvionDB.VECINFO (best-effort — never raises)."""
    try:
        (db_root / _VEC_INFO_FILE).write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning(f"[Vectorizer] Could not write {_VEC_INFO_FILE}: {exc}")


# ── Text builder ───────────────────────────────────────────────────────────────

def _entity_to_text(entity: dict) -> str:
    """
    Build a combined text string from entity data for embedding.
    Format: "{name} ({type}). {summary}. Tags: {tags}. Categories: {cats}."
    Empty parts are skipped.
    """
    name    = entity.get("name", "")
    etype   = entity.get("type", "")
    core    = (entity.get("sections") or {}).get("core", {})
    summary = core.get("summary", "")
    tags    = core.get("tags", [])
    cats    = core.get("categories", [])

    parts: list[str] = []

    # Name + type header
    if name and etype:
        parts.append(f"{name} ({etype}).")
    elif name:
        parts.append(f"{name}.")

    if summary:
        parts.append(f"{summary}.")

    if tags:
        parts.append(f"Tags: {', '.join(tags)}.")

    if cats:
        parts.append(f"Categories: {', '.join(cats)}.")

    return " ".join(parts)


# ── Embedding ──────────────────────────────────────────────────────────────────

async def _embed_google(text: str, model: str) -> list[float]:
    """
    Async wrapper around google.generativeai.embed_content.
    Runs in a thread so as not to block the event loop.
    """
    import google.generativeai as genai

    def _sync_embed() -> list[float]:
        result = genai.embed_content(
            model=f"models/{model}",
            content=text,
            task_type="retrieval_document",
        )
        return result["embedding"]

    return await asyncio.to_thread(_sync_embed)


# ── Background vectorization task ──────────────────────────────────────────────

async def vectorize_all(
    db_root:       Path,
    writer:        "EntityWriter",
    model:         str,
    force_rewrite: bool = False,
) -> None:
    """
    Background task: generate embeddings for every non-deleted entity.

    Progress is written to AethvionDB.VECINFO every 5 entities.
    Individual entity failures are logged and counted but do not abort the run.
    """
    key = str(db_root)

    now_iso = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")

    # Mark as running
    write_vec_info(db_root, {
        "status":     "running",
        "model":      model,
        "started_at": now_iso(),
    })

    vectorized = 0
    skipped    = 0
    failed:    list[str] = []

    try:
        entities = writer.list_all(include_deleted=False)
        total    = len(entities)

        write_vec_info(db_root, {
            "status":     "running",
            "model":      model,
            "started_at": now_iso(),
            "total":      total,
            "vectorized": 0,
            "skipped":    0,
            "failed":     0,
        })

        for idx, entity in enumerate(entities):
            entity_id = entity.get("id", "")
            try:
                # Check if already has a vector for this model
                existing_vec = (
                    (entity.get("sections") or {})
                    .get("vectors", {})
                    .get(model)
                )
                if existing_vec and not force_rewrite:
                    skipped += 1
                else:
                    text       = _entity_to_text(entity)
                    embedding  = await _embed_google(text, model)
                    dimensions = EMBEDDING_MODELS.get(model, {}).get("dimensions", len(embedding))
                    vec_entry  = {
                        "embedding":    embedding,
                        "model":        model,
                        "dimensions":   dimensions,
                        "generated_at": now_iso(),
                        "input":        text[:300],
                    }
                    writer.update(
                        entity_id,
                        {"sections": {"vectors": {model: vec_entry}}},
                        merge_sections=True,
                    )
                    vectorized += 1
            except Exception as exc:
                logger.warning(f"[Vectorizer] Failed to embed entity {entity_id!r}: {exc}")
                failed.append(entity_id)

            # Checkpoint every 5 entities
            if (idx + 1) % 5 == 0:
                write_vec_info(db_root, {
                    "status":     "running",
                    "model":      model,
                    "total":      total,
                    "vectorized": vectorized,
                    "skipped":    skipped,
                    "failed":     len(failed),
                    "started_at": now_iso(),
                })

        # Finished
        write_vec_info(db_root, {
            "status":       "done",
            "model":        model,
            "total":        total,
            "vectorized":   vectorized,
            "skipped":      skipped,
            "failed":       len(failed),
            "failed_ids":   failed,
            "completed_at": now_iso(),
        })
        logger.info(
            f"[Vectorizer] Done: {vectorized} embedded, {skipped} skipped, "
            f"{len(failed)} failed."
        )

    except Exception as exc:
        logger.error(f"[Vectorizer] Task-level error: {exc}")
        write_vec_info(db_root, {
            "status": "error",
            "error":  str(exc)[:300],
        })
    finally:
        _vec_tasks.pop(key, None)


# ── Cancel ─────────────────────────────────────────────────────────────────────

def cancel_vectorize(db_root: Path) -> dict:
    """Cancel a running vectorization task and update VECINFO to status=cancelled."""
    key  = str(db_root)
    task = _vec_tasks.get(key)
    if task:
        task.cancel()
    info = read_vec_info(db_root)
    write_vec_info(db_root, {
        **info,
        "status":       "cancelled",
        "cancelled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    return {"cancelled": True}
