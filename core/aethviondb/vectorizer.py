"""
core/aethviondb/vectorizer.py
══════════════════════════════
Generate and store embedding vectors for AethvionDB entities.

Supported providers:
  • Google  — GOOGLE_AI_API_KEY  (google-genai SDK)
  • OpenAI  — OPENAI_API_KEY     (openai SDK)

Vectors are stored inside the entity sections:
  entity["sections"]["vectors"] = {
      "text-embedding-3-small": {
          "embedding":    [...floats...],
          "model":        "text-embedding-3-small",
          "dimensions":   1536,
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
    # OpenAI
    "text-embedding-3-small": {
        "provider":    "openai",
        "dimensions":  1536,
        "description": "OpenAI text-embedding-3-small — fast, efficient (recommended)",
    },
    "text-embedding-3-large": {
        "provider":    "openai",
        "dimensions":  3072,
        "description": "OpenAI text-embedding-3-large — highest quality",
    },
    "text-embedding-ada-002": {
        "provider":    "openai",
        "dimensions":  1536,
        "description": "OpenAI text-embedding-ada-002 — legacy",
    },
    # Google
    "text-embedding-004": {
        "provider":    "google",
        "dimensions":  768,
        "description": "Gemini text-embedding-004",
    },
    "embedding-001": {
        "provider":    "google",
        "dimensions":  768,
        "description": "Gemini embedding-001 — legacy",
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


# ── Provider clients ───────────────────────────────────────────────────────────

def _make_google_client():
    """
    Create a google-genai Client (google-genai>=1.0.0).
    Uses GOOGLE_AI_API_KEY env var.
    """
    from google import genai  # google-genai>=1.0.0

    api_key = os.getenv("GOOGLE_AI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_AI_API_KEY is not set. Add it to your .env file."
        )
    return genai.Client(api_key=api_key, http_options={"api_version": "v1"})


def _make_openai_client():
    """
    Create an OpenAI client.
    Uses OPENAI_API_KEY env var.
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError(
            "openai package is not installed. Run: pip install openai"
        )
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to your .env file."
        )
    return OpenAI(api_key=api_key)


# ── Embedding ──────────────────────────────────────────────────────────────────

async def _embed_google(text: str, model: str) -> list[float]:
    def _sync_embed() -> list[float]:
        client = _make_google_client()
        result = client.models.embed_content(model=model, contents=text)
        if not result or not result.embeddings:
            raise RuntimeError(f"Empty embedding response from model {model!r}")
        return list(result.embeddings[0].values)
    return await asyncio.to_thread(_sync_embed)


async def _embed_openai(text: str, model: str) -> list[float]:
    def _sync_embed() -> list[float]:
        client = _make_openai_client()
        response = client.embeddings.create(model=model, input=text)
        return response.data[0].embedding
    return await asyncio.to_thread(_sync_embed)


async def _embed(text: str, model: str) -> list[float]:
    """Route to the correct provider based on EMBEDDING_MODELS registry."""
    provider = EMBEDDING_MODELS.get(model, {}).get("provider", "google")
    if provider == "openai":
        return await _embed_openai(text, model)
    return await _embed_google(text, model)


def _preflight_check(model: str) -> None:
    """Verify the provider client can be constructed. Raises on failure."""
    provider = EMBEDDING_MODELS.get(model, {}).get("provider", "google")
    if provider == "openai":
        _make_openai_client()
    else:
        _make_google_client()


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

    vectorized  = 0
    skipped     = 0
    failed:     list[str] = []
    first_error: str | None = None

    try:
        # ── Preflight: verify the embedding client works before touching any entity ──
        try:
            _preflight_check(model)
        except Exception as preflight_exc:
            err_msg = str(preflight_exc)
            logger.error(f"[Vectorizer] Preflight failed: {err_msg}")
            write_vec_info(db_root, {
                "status":     "error",
                "error":      err_msg,
                "model":      model,
                "started_at": now_iso(),
            })
            return

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
                    embedding  = await _embed(text, model)
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
                err_str = str(exc)
                logger.warning(f"[Vectorizer] Failed to embed entity {entity_id!r}: {err_str}")
                failed.append(entity_id)
                if first_error is None:
                    first_error = err_str

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
                    "last_error":    first_error,
                    "started_at":    now_iso(),
                })

        # Final status
        final_status = "done" if vectorized > 0 or skipped > 0 else (
            "error" if failed else "done"
        )
        write_vec_info(db_root, {
            "status":        final_status,
            "model":         model,
            "include_stubs": include_stubs,
            "total":         total,
            "vectorized":    vectorized,
            "skipped":       skipped,
            "failed":        len(failed),
            "failed_ids":    failed,
            "last_error":    first_error,
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
