"""
core/orchestrator/project_memory.py
Workspace-level persistent memory for the Code / Agent workspace.

Every workspace gets a single  project_memory.json  file that lives in:
    data/code/{workspace_id}/project_memory.json

Items survive across threads and model switches.  They are injected at the
top of every agent system prompt so the agent never needs to re-discover
project facts or re-read user constraints.

Categories
----------
rule        Hard constraints the agent MUST respect (e.g. "no compilers").
context     Factual project info (tech stack, entry points, key files).
design      Visual / UX decisions (theme, layout, component patterns).
note        Soft observations (gotchas, patterns, performance notes).
checklist   Persistent project-level task list spanning multiple sessions.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.utils.logger import get_logger
from core.utils import atomic_json_write, load_json

logger = get_logger(__name__)

CATEGORIES = ("rule", "context", "design", "note", "checklist")

# Category display order in the injected prompt block
_CATEGORY_ORDER = ("rule", "context", "design", "note", "checklist")

# Emoji / label shown in the Thoughts panel when the agent saves an item
CATEGORY_META = {
    "rule":      {"icon": "🔴", "label": "Rule"},
    "context":   {"icon": "🔵", "label": "Context"},
    "design":    {"icon": "🟣", "label": "Design"},
    "note":      {"icon": "🟡", "label": "Note"},
    "checklist": {"icon": "📋", "label": "Checklist"},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectMemory:
    """Read/write interface for one workspace's project_memory.json."""

    def __init__(self, workspace_id: str, storage_root: Path) -> None:
        self.workspace_id = workspace_id
        self._path = storage_root / workspace_id / "project_memory.json"

    # I/O

    def load(self) -> list[dict]:
        return load_json(self._path, default=[])

    def _save(self, items: list[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json_write(self._path, items)

    # CRUD

    def add_item(
        self,
        category: str,
        text: Optional[str] = None,
        title: Optional[str] = None,
        items: Optional[list[dict]] = None,
        source: str = "agent",
    ) -> dict:
        """Add a new memory item. Returns the created item."""
        if category not in CATEGORIES:
            category = "note"
        now = _now()
        item: dict[str, Any] = {
            "id":         str(uuid.uuid4())[:8],
            "category":   category,
            "text":       text,
            "title":      title,
            "items":      items,   # checklist items: [{id, text, done}]
            "source":     source,
            "created_at": now,
            "updated_at": now,
        }
        all_items = self.load()
        all_items.append(item)
        self._save(all_items)
        logger.info("[ProjectMemory] Added %s item: %s", category, (text or title or "")[:60])
        return item

    def update_item(self, item_id: str, **updates) -> Optional[dict]:
        """Update fields of an existing item. Returns updated item or None."""
        all_items = self.load()
        for item in all_items:
            if item["id"] == item_id:
                for k, v in updates.items():
                    item[k] = v
                item["updated_at"] = _now()
                self._save(all_items)
                return item
        return None

    def delete_item(self, item_id: str) -> bool:
        """Remove an item by ID. Returns True if found and deleted."""
        all_items = self.load()
        before = len(all_items)
        all_items = [i for i in all_items if i["id"] != item_id]
        if len(all_items) < before:
            self._save(all_items)
            return True
        return False

    # Checklist helpers

    def add_checklist_items(self, checklist_id: str, texts: list[str]) -> Optional[dict]:
        """Append new items to an existing checklist."""
        all_items = self.load()
        for item in all_items:
            if item["id"] == checklist_id and item["category"] == "checklist":
                checklist_items = item.get("items") or []
                for text in texts:
                    checklist_items.append({
                        "id":   str(uuid.uuid4())[:8],
                        "text": text,
                        "done": False,
                    })
                item["items"] = checklist_items
                item["updated_at"] = _now()
                self._save(all_items)
                return item
        return None

    def update_checklist_item(
        self, checklist_id: str, checklist_item_id: str, done: bool
    ) -> bool:
        """Set the done state of a single checklist row. Returns True on success."""
        all_items = self.load()
        for item in all_items:
            if item["id"] == checklist_id and item["category"] == "checklist":
                for ci in (item.get("items") or []):
                    if ci["id"] == checklist_item_id:
                        ci["done"] = done
                        item["updated_at"] = _now()
                        self._save(all_items)
                        return True
        return False

    # System-prompt injection

    def get_injection_block(self) -> str:
        """Return a formatted block for injection at the top of the system prompt.

        Returns an empty string when there are no items.
        """
        all_items = self.load()
        if not all_items:
            return ""

        sections: dict[str, list[str]] = {c: [] for c in _CATEGORY_ORDER}

        for item in all_items:
            cat = item.get("category", "note")
            if cat not in sections:
                cat = "note"

            if cat == "checklist":
                title = item.get("title") or "Checklist"
                lines = [f"  {title}:"]
                for ci in (item.get("items") or []):
                    mark = "✓" if ci.get("done") else "☐"
                    lines.append(f"    {mark} {ci['text']}")
                sections["checklist"].append("\n".join(lines))
            else:
                text = item.get("text") or ""
                if text:
                    sections[cat].append(f"  • {text}")

        block_lines = [
            "═" * 60,
            f"PROJECT MEMORY — applies to every task in this workspace",
            "Rules are hard constraints. Violating them is an error.",
            "═" * 60,
        ]

        LABELS = {
            "rule":      "Rules (hard constraints — never violate):",
            "context":   "Context (project facts):",
            "design":    "Design:",
            "note":      "Notes:",
            "checklist": "Checklists:",
        }

        for cat in _CATEGORY_ORDER:
            lines = sections[cat]
            if lines:
                block_lines.append(LABELS[cat])
                block_lines.extend(lines)

        block_lines.append("═" * 60)
        return "\n".join(block_lines)
