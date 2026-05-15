"""
core/worldsim/expansion_engine.py
═══════════════════════════════════
Autonomous stub-to-entity expansion engine for WorldSim.

Works in two modes:

1. STUB EXPANSION
   Finds stub entities (status="stub") and generates full content for them
   using AI, given only the entity name and context from related entities.

2. SECTION DEEPENING
   For active entities, turns sub-topics in sections.stubs into their own
   full entities.

Design principles
-----------------
- Never overwrite Layer-1 data with AI-hallucinated corrections.
  The engine ONLY fills missing/empty fields, never replaces existing data.
- Every AI call produces JSON. If the JSON is malformed or missing required
  fields the entity is left as a stub and the error is logged.
- The engine is re-entrant safe: run it multiple times without duplication
  because EntityWriter.create() and the NameIndex deduplicate.

Usage
-----
    from core.worldsim.expansion_engine import ExpansionEngine
    engine = ExpansionEngine()

    # Expand one stub
    result = await engine.expand_stub("ws_abc123")

    # Expand up to N stubs autonomously
    report = await engine.run(max_entities=10, model="gemini-1.5-flash")
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from core.utils.logger import get_logger
from core.ai.call_contexts import CallSource
from .entity_schema import VALID_TYPES, _now_iso
from .entity_writer import EntityWriter
from .name_index import NameIndex, get_index
from .distiller import _extract_json, _map_to_sections as _map_to_entity_sections

logger = get_logger(__name__)


_EXPANSION_SYSTEM_PROMPT = """You are a JSON-only knowledge generator for a structured database.

CRITICAL: Your entire response must be a single valid JSON object. No prose, no markdown, no code fences, no explanation before or after. Start your response with { and end with }.

You will receive an entity name. Generate a comprehensive knowledge entry for it.

Rules:
- "type" must be one of: person, place, event, concept, organization, artifact, creature, substance, process, phenomenon, work, species, universe, other
- "summary" is 2-4 sentences describing what this entity is
- "stubs" lists only important proper nouns that appear in context and deserve their own entries (other people, places, organizations, concepts). Keep this list short — 3-8 items max.
- "timeline" events only when well-known dates are certain
- "properties" captures key structured facts (e.g. birth_year, nationality, field, founded)
- Use empty arrays [] for sections you have nothing to say about
- Do not invent facts. Use known/public knowledge only.

Respond with exactly this JSON shape (no other text):
{"type":"...","aliases":[],"categories":[],"tags":[],"summary":"...","timeline":[{"date":"YYYY","event":"...","ref_names":[]}],"relations":[{"kind":"related_to","target_name":"...","note":""}],"properties":{"key":"value"},"stubs":[]}"""

_EXPANSION_RETRY_SUFFIX = (
    "\n\nIMPORTANT: You must respond with ONLY a JSON object. "
    "No explanation. No markdown. Start immediately with { and end with }."
)


def _build_expansion_prompt(
    entity_name: str,
    context_snippets: list[str],
    max_context_chars: int = 2000,
    retry: bool = False,
) -> str:
    ctx = "\n".join(context_snippets)[:max_context_chars]
    prompt = f'Generate a knowledge database entry for: "{entity_name}"'
    if ctx:
        prompt += f"\n\nContext from related entities:\n{ctx}"
    prompt += "\n\nRespond with a JSON object only."
    if retry:
        prompt += _EXPANSION_RETRY_SUFFIX
    return prompt


@dataclass
class ExpansionReport:
    """Result of a run() call."""
    expanded:    list[str] = field(default_factory=list)   # entity IDs successfully expanded
    skipped:     list[str] = field(default_factory=list)   # already active
    failed:      list[str] = field(default_factory=list)   # expansion failed
    new_stubs:   list[str] = field(default_factory=list)   # new stub IDs discovered
    total_calls: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "expanded":    self.expanded,
            "skipped":     self.skipped,
            "failed":      self.failed,
            "new_stubs":   self.new_stubs,
            "total_calls": self.total_calls,
            "summary": (
                f"Expanded {len(self.expanded)}, "
                f"skipped {len(self.skipped)}, "
                f"failed {len(self.failed)}, "
                f"created {len(self.new_stubs)} new stubs"
            ),
        }


class ExpansionEngine:
    """
    Autonomous entity expansion engine.

    Parameters
    ----------
    writer : EntityWriter, optional
    model  : str            — default AI model
    concurrency : int       — max parallel AI calls (default 2)
    """

    def __init__(
        self,
        writer: Optional[EntityWriter] = None,
        index: Optional[NameIndex] = None,
        model: str = "auto",
        concurrency: int = 2,
    ) -> None:
        self._writer        = writer or EntityWriter()
        self._index         = index if index is not None else get_index()
        self._default_model = model
        self._semaphore     = asyncio.Semaphore(concurrency)

    # ── Context gathering ─────────────────────────────────────────────────────

    def _gather_context(self, entity_id: str) -> list[str]:
        """
        Collect summary snippets from related entities to provide
        context for stub expansion.
        """
        entity = self._writer.get(entity_id)
        if not entity:
            return []

        snippets: list[str] = []
        for rel in entity["sections"].get("relations", []):
            if not isinstance(rel, dict):
                continue
            related = self._writer.get(rel.get("target_id", ""))
            if not related:
                continue
            summary = related["sections"]["core"].get("summary", "")
            if summary:
                snippets.append(f"[{rel['kind']}] {related['name']}: {summary}")

        return snippets

    # ── Core expansion ────────────────────────────────────────────────────────

    async def expand_stub(
        self,
        entity_id: str,
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Expand a single stub entity.

        Returns a result dict:
        {
          "entity_id":  "ws_...",
          "success":    bool,
          "new_stubs":  ["name", ...],
          "error":      "..." or None,
        }
        """
        entity = self._writer.get(entity_id)
        result: dict[str, Any] = {
            "entity_id": entity_id,
            "success":   False,
            "new_stubs": [],
            "error":     None,
        }

        if not entity:
            result["error"] = f"Entity {entity_id!r} not found"
            return result

        if entity.get("status") == "active" and entity["sections"]["core"].get("summary"):
            result["success"] = True
            result["error"]   = "already_active"
            return result

        used_model = model or self._default_model
        context    = self._gather_context(entity_id)

        async with self._semaphore:
            from core.providers import ProviderManager
            pm = ProviderManager()

            raw = None
            for attempt in range(2):   # up to 2 attempts
                prompt   = _build_expansion_prompt(entity["name"], context, retry=(attempt > 0))
                trace_id = uuid.uuid4().hex
                try:
                    response = await asyncio.to_thread(
                        pm.call_with_failover,
                        prompt=prompt,
                        system_prompt=_EXPANSION_SYSTEM_PROMPT,
                        model=used_model,
                        trace_id=trace_id,
                        source=CallSource.WORLDSIM,
                    )
                    raw = response.content if hasattr(response, "content") else str(response)
                except Exception as e:
                    result["error"] = f"AI call failed: {e}"
                    logger.error(f"[ExpansionEngine] {entity_id}: {result['error']}")
                    return result

                try:
                    extracted = _extract_json(raw)
                    break   # success — exit retry loop
                except Exception as parse_err:
                    if attempt == 0:
                        logger.warning(
                            f"[ExpansionEngine] {entity_id}: JSON parse failed on attempt 1, retrying. "
                            f"Raw response ({len(raw)} chars): {raw[:500]!r}"
                        )
                    else:
                        result["error"] = f"JSON parse failed: {parse_err}"
                        logger.error(
                            f"[ExpansionEngine] {entity_id}: {result['error']}. "
                            f"Raw response ({len(raw)} chars): {raw[:500]!r}"
                        )
                        return result
            else:
                # Should not reach here, but guard anyway
                result["error"] = "JSON parse failed after retries"
                return result

        # Map to sections
        try:
            sections, new_stubs = _map_to_entity_sections(extracted, self._index, self._writer)
        except Exception as e:
            result["error"] = f"Section mapping failed: {e}"
            return result

        # Determine entity type
        entity_type = extracted.get("type", entity.get("type", "other"))
        if entity_type not in VALID_TYPES:
            entity_type = entity.get("type", "other")

        # Update: merge new sections into existing entity, set active
        mutations: dict[str, Any] = {
            "type":    entity_type,
            "status":  "active",
            "source":  entity.get("source", "expansion"),
            "sections": sections,
        }
        try:
            self._writer.update(entity_id, mutations, merge_sections=True)
        except Exception as e:
            result["error"] = f"Write failed: {e}"
            return result

        # Create stub entities for newly discovered sub-topics
        new_stub_ids = []
        for stub_name in new_stubs:
            if not self._index.get(stub_name):
                stub_entity, created = self._writer.create(
                    stub_name,
                    entity_type="other",
                    source="expansion",
                )
                if created:
                    self._writer.update(stub_entity["id"], {"status": "stub"})
                    new_stub_ids.append(stub_entity["id"])

        result["success"]   = True
        result["new_stubs"] = new_stub_ids

        logger.info(
            f"[ExpansionEngine] Expanded {entity['name']!r} ({entity_id}) "
            f"type={entity_type}, new_stubs={len(new_stub_ids)}"
        )
        return result

    # ── Batch run ─────────────────────────────────────────────────────────────

    async def run(
        self,
        max_entities: int = 20,
        model: Optional[str] = None,
        only_ids: Optional[list[str]] = None,
    ) -> ExpansionReport:
        """
        Expand up to *max_entities* stubs.

        If *only_ids* is given, only those IDs are processed (ignores stub status).
        Otherwise, pulls from the stub queue in the entity store.

        Returns an ExpansionReport.
        """
        report = ExpansionReport()
        used_model = model or self._default_model

        if only_ids:
            targets = only_ids[:max_entities]
        else:
            stubs   = self._writer.list_stubs()
            targets = [s["id"] for s in stubs[:max_entities]]

        if not targets:
            logger.info("[ExpansionEngine] No stubs to expand.")
            return report

        logger.info(f"[ExpansionEngine] Starting expansion of {len(targets)} stubs…")

        tasks = [self.expand_stub(eid, model=used_model) for eid in targets]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            report.total_calls += 1
            if isinstance(res, Exception):
                report.failed.append(str(res))
                continue
            if res["error"] == "already_active":
                report.skipped.append(res["entity_id"])
            elif res["success"]:
                report.expanded.append(res["entity_id"])
                report.new_stubs.extend(res.get("new_stubs", []))
            else:
                report.failed.append(res["entity_id"])

        logger.info(
            f"[ExpansionEngine] Done. "
            f"expanded={len(report.expanded)}, "
            f"failed={len(report.failed)}, "
            f"new_stubs={len(report.new_stubs)}"
        )
        return report

    # ── Section deepening ─────────────────────────────────────────────────────

    async def deepen_stubs_for(
        self,
        entity_id: str,
        max_stubs: int = 5,
        model: Optional[str] = None,
    ) -> ExpansionReport:
        """
        For an active entity, turn its sections.stubs list into real entities,
        then expand each one.
        """
        report   = ExpansionReport()
        entity   = self._writer.get(entity_id)
        if not entity:
            return report

        stub_names = self._writer.get_stub_names_for(entity_id)[:max_stubs]
        new_ids    = []

        for name in stub_names:
            stub_entity, created = self._writer.create(
                name, entity_type="other", source="expansion"
            )
            if created:
                self._writer.update(stub_entity["id"], {"status": "stub"})
            new_ids.append(stub_entity["id"])

        if new_ids:
            sub = await self.run(max_entities=max_stubs, model=model, only_ids=new_ids)
            report.expanded    = sub.expanded
            report.failed      = sub.failed
            report.new_stubs   = sub.new_stubs
            report.total_calls = sub.total_calls

        return report
