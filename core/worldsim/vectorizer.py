"""
core/worldsim/vectorizer.py
════════════════════════════
Generate and store embedding vectors for AethvionDB entities.

Uses the google-genai SDK (google-genai>=1.0.0), matching the rest of
Aethvion Suite.  API key is read from the GOOGLE_AI_API_KEY env var.

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
import os
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
        "description": "Gemini text-embedding-004 — best quality (recommended)",
    },
    "embedding-001": {
        "provider":   "google",
        "dimensions": 768,
        "description": "Gemini embedding-001 — legacy model",
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


# ── Google client ──────────────────────────────────────────────────────────────

def _make_google_client():
    """
    Create a google-genai Client using the GOOGLE_AI_API_KEY env var.
    Raises RuntimeError if the key is missing so the caller can surface a
    clear message rather than a cryptic SDK exception.
    """
    from google import genai  # google-genai>=1.0.0

    api_key = os.getenv("GOOGLE_AI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_AI_API_KEY environment variable is not set. "
            "Add it to your .env file to use vector embeddings."
        )
    return genai.Client(api_key=api_key)


# ── Embedding ──────────────────────────────────────────────────────────────────

async def _embed_google(text: str, model: str) -> list[float]:
    """
    Async wrapper: calls google-genai embed_content in a thread pool so the
    event loop is not blocked.  Returns the embedding as a list of floats.
    """
    def _sync_embed() -> list[float]:
        client = _make_google_client()
        result = client.models.embed_content(model=model, contents=text)
        # result.embeddings is a list of ContentEmbedding; take the first entry
        return list(result.embeddings[0].values)

    return await asyncio.to_thread(_sync_embed)


# ── Background vectorization task ──────────────────────────────────────────────

async def vectorize_all(
    db_root:       Path,
    writer:        "EntityWriter",
    model:         str,
    force_rewrite: bool = False,
    include_stubs: bool = True,
) -> None:
    """
    Background task: generate embeddings for every non-deleted entity.

    Parameters
    ----------
    force_rewrite : bool
        If True, re-embed entities that already have a vector for this model.
    include_stubs : bool
        If False, stub entities (status == 'stub') are skipped entirely.

    Progress is written to AethvionDB.VECINFO every 5 entities.
    Individual entity failures are logged and counted but do not abort the run.
    """
    key     = str(db_root)
    now_iso = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")

    # Mark as running immediately
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

        # Filter out stubs if requested
        if not include_stubs:
            entities = [e for e in entities if e.get("status") != "stub"]

        total = len(entities)

        write_vec_info(db_root, {
            "status":        "running",
            "model":         model,
            "include_stubs": include_stubs,
            "started_at":    now_iso(),
            "total":         total,
            "vectorized":    0,
            "skipped":       0,
            "failed":        0,
        })

        for idx, entity in enumerate(entities):
            entity_id = entity.get("id", "")
            try:
                # Skip if already vectorized and not forcing rewrite
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
                    "status":        "running",
                    "model":         model,
                    "include_stubs": include_stubs,
                    "total":         total,
                    "vectorized":    vectorized,
                    "skipped":       skipped,
                    "failed":        len(failed),
                    "started_at":    now_iso(),
                })

        # Final status
        write_vec_info(db_root, {
            "status":        "done",
            "model":         model,
            "include_stubs": include_stubs,
            "total":         total,
            "vectorized":    vectorized,
            "skipped":       skipped,
            "failed":        len(failed),
            "failed_ids":    failed,
            "completed_at":  now_iso(),
        })
        logger.info(
            f"[Vectorizer] Done: {vectorized} embedded, {skipped} skipped, "
            f"{len(failed)} failed."
        )

    except Exception as exc:
        logger.error(f"[Vectorizer] Task level error: {exc}")
        write_vec_info(db_root, {
            "status": "error",
            "error":  str(exc)[:500],
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
