"""
core/worldsim/entity_schema.py
══════════════════════════════
Canonical schema for WorldSim Layer-1 entity files.

Every entity — from a universe to a subatomic particle — shares this
identical envelope. No facts are duplicated: cross-entity relationships
are always expressed as ID references, never copied text.

Schema
------
{
  "id":      "ws_<hex>",          # Stable 16-char hex UUID prefix
  "type":    "person|place|event|concept|organization|artifact|creature|...",
  "name":    "Canonical Name",    # Title-case canonical; aliases live in core.aliases
  "status":  "active|stub|deleted",
  "version": 1,                   # Integer, incremented on every write
  "created": "ISO-8601",
  "updated": "ISO-8601",
  "source":  "wikipedia|manual|expansion|import",
  "sections": {
    "core": {
      "summary":    "1-3 sentence essence",
      "aliases":    ["alt name", ...],
      "categories": ["Science", "History", ...],
      "tags":       ["keyword", ...]
    },
    "timeline": [
      { "date": "YYYY or YYYY-MM-DD", "event": "Short description", "ref_ids": ["ws_..."] }
    ],
    "relations": [
      { "kind": "parent_of|member_of|created_by|located_in|...", "target_id": "ws_...", "note": "" }
    ],
    "properties": {
      # Type-specific structured facts — free key/value, values are strings or simple lists
    },
    "stubs": [
      "Sub-topic name that needs its own entity",
      ...
    ]
  }
}
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any


VALID_STATUSES = {"active", "stub", "deleted"}

VALID_TYPES = {
    "person", "place", "event", "concept", "organization",
    "artifact", "creature", "substance", "process", "phenomenon",
    "work",       # book, film, song, game …
    "species",
    "universe",   # fictional or cosmological containers
    "other",
}

RELATION_KINDS = {
    "parent_of", "child_of",
    "member_of", "contains",
    "created_by", "created",
    "located_in", "location_of",
    "part_of", "has_part",
    "preceded_by", "followed_by",
    "related_to",
    "instance_of", "has_instance",
    "influenced_by", "influenced",
    "participated_in", "has_participant",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id() -> str:
    """Generate a stable 'ws_' prefixed 16-hex ID."""
    return "ws_" + uuid.uuid4().hex[:16]


def make_empty(
    name: str,
    entity_type: str = "other",
    source: str = "manual",
    entity_id: str | None = None,
) -> dict[str, Any]:
    """
    Return a minimal valid entity dict.
    Use EntityWriter.create() for disk-persisted creation.
    """
    now = _now_iso()
    return {
        "id":      entity_id or _new_id(),
        "type":    entity_type if entity_type in VALID_TYPES else "other",
        "name":    name,
        "status":  "active",
        "version": 1,
        "created": now,
        "updated": now,
        "source":  source,
        "sections": {
            "core": {
                "summary":    "",
                "aliases":    [],
                "categories": [],
                "tags":       [],
            },
            "timeline":   [],
            "relations":  [],
            "properties": {},
            "stubs":      [],
        },
    }


def validate(entity: dict[str, Any]) -> list[str]:
    """
    Structural validation only (schema shape, required keys, enum values).
    For semantic/consistency checks use Validator.
    Returns a list of error strings; empty list means valid.
    """
    errors: list[str] = []

    for key in ("id", "type", "name", "status", "version", "created", "updated", "source", "sections"):
        if key not in entity:
            errors.append(f"Missing required key: {key!r}")

    if "status" in entity and entity["status"] not in VALID_STATUSES:
        errors.append(f"Invalid status {entity['status']!r}; must be one of {VALID_STATUSES}")

    if "type" in entity and entity["type"] not in VALID_TYPES:
        errors.append(f"Unknown entity type {entity['type']!r}")

    secs = entity.get("sections", {})
    for sec in ("core", "timeline", "relations", "properties", "stubs"):
        if sec not in secs:
            errors.append(f"Missing section: {sec!r}")

    if isinstance(secs.get("timeline"), list):
        for i, ev in enumerate(secs["timeline"]):
            if not isinstance(ev, dict) or "date" not in ev or "event" not in ev:
                errors.append(f"timeline[{i}] must have 'date' and 'event' keys")

    if isinstance(secs.get("relations"), list):
        for i, rel in enumerate(secs["relations"]):
            if not isinstance(rel, dict) or "kind" not in rel or "target_id" not in rel:
                errors.append(f"relations[{i}] must have 'kind' and 'target_id' keys")

    return errors
