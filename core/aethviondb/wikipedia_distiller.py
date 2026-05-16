"""
core/aethviondb/wikipedia_distiller.py
════════════════════════════════════════
Converts raw Wikipedia-style text into AethvionDB Layer-1 entity files.

The distiller sends the article text to an LLM with a structured extraction
prompt and maps the response into the entity schema. It never writes facts
for entities it creates stubs for — stub expansion is handled separately by
the expansion engine.

Supported entity type detection
--------------------------------
The distiller infers entity type from Wikipedia categories and text clues:
  person, place, event, concept, organization, artifact, creature,
  substance, process, phenomenon, work, species, other

Usage
-----
    from core.aethviondb.wikipedia_distiller import WikipediaDistiller
    distiller = WikipediaDistiller()

    # From raw text (sync — wraps the async method)
    result = distiller.distill_sync(
        article_text="...",
        article_title="Albert Einstein",
        model="gemini-1.5-flash",
    )

    # Async (preferred in route handlers)
    result = await distiller.distill(
        article_text="...",
        article_title="Albert Einstein",
    )
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import Any, Optional

from core.utils.logger import get_logger
from core.ai.call_contexts import CallSource
from .entity_schema import VALID_TYPES
from .entity_writer import EntityWriter
from .name_index import get_index

logger = get_logger(__name__)

_SYSTEM_PROMPT = """You are a knowledge extraction engine for a structured world-simulation database.

Your task: read the provided article text and extract all key information into a strict JSON object.

RULES:
- Output ONLY valid JSON. No markdown, no code fences, no explanation.
- Every value must be a string, number, or array of strings — no nested objects except where specified.
- Do not invent facts not present in the text. Leave fields empty ("" or []) if not stated.
- "stubs" lists sub-topics mentioned that deserve their own entity entry — only include meaningful proper nouns (people, places, organizations, concepts). Not every word.
- "relations" are cross-entity references; use descriptive kind strings from this set:
  parent_of, child_of, member_of, contains, created_by, created, located_in, location_of,
  part_of, has_part, preceded_by, followed_by, related_to, instance_of, has_instance,
  influenced_by, influenced, participated_in, has_participant
- "type" must be exactly one of:
  person, place, event, concept, organization, artifact, creature,
  substance, process, phenomenon, work, species, universe, other
- "timeline" events: date must be YYYY or YYYY-MM-DD format (approximate dates like "circa 1900" → "~1900").

Output this exact JSON structure:
{
  "type": "<entity_type>",
  "aliases": ["alternate name 1", "..."],
  "categories": ["Category 1", "..."],
  "tags": ["keyword1", "keyword2"],
  "summary": "<1-3 sentence essence of what this entity is>",
  "timeline": [
    { "date": "YYYY", "event": "Short description of what happened", "ref_names": ["Name of related entity"] }
  ],
  "relations": [
    { "kind": "located_in", "target_name": "Name of related entity", "note": "optional clarification" }
  ],
  "properties": {
    "key": "value"
  },
  "stubs": ["Name of sub-topic 1", "Name of sub-topic 2"]
}"""


def _build_user_prompt(title: str, text: str, max_chars: int = 12000) -> str:
    truncated = text[:max_chars]
    if len(text) > max_chars:
        truncated += "\n\n[...text truncated for length...]"
    return f"Article title: {title}\n\nArticle text:\n{truncated}"


def _extract_json(raw: str) -> dict[str, Any]:
    """Extract the first JSON object from a raw LLM response string."""
    # Strip markdown fences
    clean = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    # Find first { ... }
    start = clean.find("{")
    end   = clean.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in LLM response")
    return json.loads(clean[start:end + 1])


def _map_to_entity_sections(
    extracted: dict[str, Any],
    index,
    writer: EntityWriter,
) -> tuple[dict[str, Any], list[str]]:
    """
    Map the raw extracted dict into the entity sections format.
    Resolves target_name → target_id where possible.
    Returns (sections_dict, unresolved_stub_names).
    """
    # ── Core section ──────────────────────────────────────────────────────────
    core = {
        "summary":    str(extracted.get("summary", "")),
        "aliases":    [str(a) for a in extracted.get("aliases", []) if a],
        "categories": [str(c) for c in extracted.get("categories", []) if c],
        "tags":       [str(t) for t in extracted.get("tags", []) if t],
    }

    # ── Timeline ─────────────────────────────────────────────────────────────
    timeline = []
    for ev in extracted.get("timeline", []):
        if not isinstance(ev, dict):
            continue
        entry: dict[str, Any] = {
            "date":    str(ev.get("date", "")),
            "event":   str(ev.get("event", "")),
        }
        # Resolve ref_names → ref_ids where possible
        ref_ids = []
        for rname in ev.get("ref_names", []):
            rid = index.get(str(rname))
            if rid:
                ref_ids.append(rid)
        if ref_ids:
            entry["ref_ids"] = ref_ids
        if entry["date"] and entry["event"]:
            timeline.append(entry)

    # ── Relations ─────────────────────────────────────────────────────────────
    relations = []
    for rel in extracted.get("relations", []):
        if not isinstance(rel, dict):
            continue
        target_name = str(rel.get("target_name", ""))
        if not target_name:
            continue
        target_id = index.get(target_name)
        if not target_id:
            # Create a stub for it
            stub_entity, _ = writer.create(
                target_name,
                entity_type="other",
                source="expansion",
                sections_override={"core": {"summary": ""}},
            )
            target_id = stub_entity["id"]
            # Mark as stub
            writer.update(target_id, {"status": "stub"})

        entry = {
            "kind":      str(rel.get("kind", "related_to")),
            "target_id": target_id,
        }
        note = str(rel.get("note", ""))
        if note:
            entry["note"] = note
        relations.append(entry)

    # ── Properties ────────────────────────────────────────────────────────────
    raw_props = extracted.get("properties", {})
    properties = {str(k): str(v) for k, v in raw_props.items() if v is not None}

    # ── Stubs ─────────────────────────────────────────────────────────────────
    stubs = [str(s) for s in extracted.get("stubs", []) if s]
    # Remove stubs that are already indexed
    unresolved = [s for s in stubs if not index.get(s)]

    sections = {
        "core":       core,
        "timeline":   timeline,
        "relations":  relations,
        "properties": properties,
        "stubs":      unresolved,
    }
    return sections, unresolved


class WikipediaDistiller:
    """
    Distills Wikipedia-style article text into WorldSim entity files.

    Parameters
    ----------
    writer : EntityWriter, optional
    model  : str, optional  — default model for AI calls
    """

    def __init__(
        self,
        writer: Optional[EntityWriter] = None,
        model: str = "gemini-1.5-flash",
    ) -> None:
        self._writer = writer or EntityWriter()
        self._index  = get_index()
        self._default_model = model

    async def distill(
        self,
        article_text: str,
        article_title: str,
        model: Optional[str] = None,
        source: str = "wikipedia",
    ) -> dict[str, Any]:
        """
        Distill an article into a WorldSim entity.

        Returns a result dict:
        {
          "entity_id":   "ws_...",
          "entity_name": "...",
          "was_created": bool,
          "stub_count":  int,
          "stubs":       ["name", ...],
          "errors":      ["..."],
        }
        """
        from core.providers import ProviderManager
        pm = ProviderManager()
        used_model = model or self._default_model

        result: dict[str, Any] = {
            "entity_id":   None,
            "entity_name": article_title,
            "was_created": False,
            "stub_count":  0,
            "stubs":       [],
            "errors":      [],
        }

        # ── Check if already exists ───────────────────────────────────────────
        existing_id = self._index.get(article_title)
        if existing_id and self._writer.exists(existing_id):
            logger.info(f"[Distiller] '{article_title}' already exists ({existing_id}) — skipping")
            result["entity_id"] = existing_id
            result["was_created"] = False
            return result

        # ── Call AI ───────────────────────────────────────────────────────────
        user_prompt = _build_user_prompt(article_title, article_text)
        trace_id = uuid.uuid4().hex

        try:
            response = await asyncio.to_thread(
                pm.call_with_failover,
                prompt=user_prompt,
                system_prompt=_SYSTEM_PROMPT,
                model=used_model,
                trace_id=trace_id,
                source=CallSource.WORLDSIM,
            )
            raw_text = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            err = f"AI call failed: {e}"
            logger.error(f"[Distiller] {err}")
            result["errors"].append(err)
            return result

        # ── Parse response ────────────────────────────────────────────────────
        try:
            extracted = _extract_json(raw_text)
        except Exception as e:
            err = f"JSON parse failed: {e}"
            logger.error(f"[Distiller] {err} — raw: {raw_text[:300]}")
            result["errors"].append(err)
            return result

        # ── Validate entity type ──────────────────────────────────────────────
        entity_type = extracted.get("type", "other")
        if entity_type not in VALID_TYPES:
            entity_type = "other"

        # ── Map to sections ───────────────────────────────────────────────────
        try:
            sections, stubs = _map_to_entity_sections(extracted, self._index, self._writer)
        except Exception as e:
            err = f"Section mapping failed: {e}"
            logger.error(f"[Distiller] {err}")
            result["errors"].append(err)
            return result

        # ── Create the entity ─────────────────────────────────────────────────
        aliases = sections["core"].get("aliases", [])
        entity, was_created = self._writer.create(
            name=article_title,
            entity_type=entity_type,
            source=source,
            sections_override=sections,
            extra_aliases=aliases,
        )

        if not was_created:
            # Race condition: another caller created it between our check and create
            entity = self._writer.update(entity["id"], {"sections": sections})

        result["entity_id"]   = entity["id"]
        result["entity_name"] = entity["name"]
        result["was_created"] = was_created
        result["stub_count"]  = len(stubs)
        result["stubs"]       = stubs

        logger.info(
            f"[Distiller] Distilled '{article_title}' → {entity['id']} "
            f"(type={entity_type}, stubs={len(stubs)})"
        )
        return result

    def distill_sync(
        self,
        article_text: str,
        article_title: str,
        model: Optional[str] = None,
        source: str = "wikipedia",
    ) -> dict[str, Any]:
        """Blocking wrapper around distill(). Use in non-async contexts."""
        return asyncio.run(self.distill(article_text, article_title, model, source))
