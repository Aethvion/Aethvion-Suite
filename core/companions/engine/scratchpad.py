"""
core/companions/engine/scratchpad.py
CompanionScratchpad — persistent, multi-agent co-working brainstorming canvas & ledger.
Supports concurrent atomic writes, author provenance tagging, color badges,
and bidirectional sync between structured JSON ledger and human-readable Markdown.
"""
from __future__ import annotations
import datetime
import json
import re
import threading
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any
from core.utils import atomic_json_write
from .base import CompanionComponent

# Global process-level mutex table per directory to guarantee thread-safe writes
_SCRATCHPAD_LOCKS: Dict[str, threading.RLock] = {}
_LOCKS_MUTEX = threading.Lock()

DEFAULT_AUTHORS: Dict[str, Dict[str, str]] = {
    "user": {
        "id": "marcel",
        "name": "Marcel",
        "role": "user",
        "color": "#10b981",
        "symbol": "✦"
    },
    "marcel": {
        "id": "marcel",
        "name": "Marcel",
        "role": "user",
        "color": "#10b981",
        "symbol": "✦"
    },
    "misakacipher": {
        "id": "misakacipher",
        "name": "Misaka Cipher",
        "role": "companion",
        "color": "#6366f1",
        "symbol": "✦"
    },
    "nova": {
        "id": "nova",
        "name": "Nova",
        "role": "companion",
        "color": "#38bdf8",
        "symbol": "✦"
    },
    "asuna": {
        "id": "asuna",
        "name": "Asuna",
        "role": "companion",
        "color": "#f43f5e",
        "symbol": "✦"
    },
    "axiom": {
        "id": "axiom",
        "name": "Axiom",
        "role": "companion",
        "color": "#06b6d4",
        "symbol": "✦"
    },
    "coder": {
        "id": "coder",
        "name": "Coder Agent",
        "role": "agent",
        "color": "#f59e0b",
        "symbol": "⚡"
    },
    "architect": {
        "id": "architect",
        "name": "Architect Agent",
        "role": "agent",
        "color": "#a855f7",
        "symbol": "🏛️"
    },
    "reviewer": {
        "id": "reviewer",
        "name": "Reviewer Agent",
        "role": "agent",
        "color": "#ec4899",
        "symbol": "🛡️"
    }
}

DEFAULT_PALETTE = [
    "#6366f1", "#10b981", "#f59e0b", "#ec4899", "#8b5cf6",
    "#06b6d4", "#f43f5e", "#14b8a6", "#3b82f6", "#eab308"
]


def _utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _get_dir_lock(dir_path: Path) -> threading.RLock:
    key = str(dir_path.resolve())
    with _LOCKS_MUTEX:
        if key not in _SCRATCHPAD_LOCKS:
            _SCRATCHPAD_LOCKS[key] = threading.RLock()
        return _SCRATCHPAD_LOCKS[key]


def _resolve_author_info(author_input: Optional[Any], default_id: str, default_name: str) -> Dict[str, str]:
    if isinstance(author_input, dict):
        aid = str(author_input.get("id") or default_id).strip().lower()
        name = str(author_input.get("name") or default_name).strip()
        role = str(author_input.get("role") or "agent").strip()
        color = str(author_input.get("color") or "").strip()
        symbol = str(author_input.get("symbol") or "✦").strip()
    else:
        aid = str(author_input or default_id).strip().lower()
        name = default_name
        role = "companion" if aid != "marcel" and aid != "user" else "user"
        color = ""
        symbol = "✦"

    preset = DEFAULT_AUTHORS.get(aid, {})
    final_name = name or preset.get("name") or aid.capitalize()
    final_role = role or preset.get("role") or "agent"
    final_color = color or preset.get("color")
    if not final_color:
        # Deterministic color by hashing author id
        idx = abs(hash(aid)) % len(DEFAULT_PALETTE)
        final_color = DEFAULT_PALETTE[idx]

    return {
        "id": aid,
        "name": final_name,
        "role": final_role,
        "color": final_color,
        "symbol": symbol or preset.get("symbol", "✦")
    }


class CompanionScratchpad(CompanionComponent):
    """
    Multi-agent, thread-safe collaborative scratchpad and brainstorming canvas.
    Maintains both `scratchpad_entries.json` (structured ledger) and `scratchpad.md` (markdown representation).
    """

    def __init__(self, data_dir: Path, companion_name: str = "Companion") -> None:
        super().__init__(data_dir, companion_name)
        self._md_file = self._dir / "scratchpad.md"
        self._ledger_file = self._dir / "scratchpad_entries.json"
        self._lock = _get_dir_lock(self._dir)
        self._initialize_if_missing()

    def _initialize_if_missing(self) -> None:
        with self._lock:
            if not self._ledger_file.exists() and not self._md_file.exists():
                is_group = self._name == "Group"
                init_ledger = {
                    "version": 2,
                    "title": "Group Scratchpad" if is_group else "Shared Brainstorming Scratchpad",
                    "subtitle": "" if is_group else f"A live co-working canvas for Marcel and {self._name}. Jot down ideas, mechanics, and plans here.",
                    "sections": [] if is_group else [
                        "💡 Ideas & Brainstorming",
                        "🛠️ Game & Feature Mechanics",
                        "📌 Quick Notes & Next Steps"
                    ],
                    "entries": [],
                    "last_modified": _utcnow_iso()
                }
                atomic_json_write(self._ledger_file, init_ledger)
                self._render_ledger_to_md(init_ledger)
                self._info(f"Initialized multi-agent scratchpad ledger for {self._name} at {self._ledger_file}")
            elif self._md_file.exists() and not self._ledger_file.exists():
                # Backfill ledger from existing markdown
                try:
                    md_text = self._md_file.read_text(encoding="utf-8", errors="replace")
                    reconciled = self._parse_markdown_into_ledger(md_text)
                    atomic_json_write(self._ledger_file, reconciled)
                    self._render_ledger_to_md(reconciled)
                except Exception as e:
                    self._error(f"Failed backfilling ledger from markdown: {e}")

    def _parse_markdown_into_ledger(self, md_text: str) -> Dict[str, Any]:
        """Parse raw markdown text into structured ledger sections and entries, preserving author tags."""
        lines = md_text.replace("\r\n", "\n").split("\n")
        title = "Shared Brainstorming Scratchpad"
        subtitle = f"A live co-working canvas for Marcel and {self._name}."
        sections = []
        entries = []
        current_section = "💡 Ideas & Brainstorming"

        pill_regex = re.compile(
            r'<span\s+class="spad-author-pill"[^>]*data-author-id="([^"]*)"[^>]*data-author="([^"]*)"[^>]*data-color="([^"]*)"[^>]*data-time="([^"]*)"[^>]*data-role="([^"]*)"[^>]*>.*?</span>\s*',
            re.IGNORECASE
        )

        for line in lines:
            line_s = line.strip()
            if not line_s:
                continue

            if line_s.startswith("# "):
                title = line_s[2:].strip()
                continue
            elif line_s.startswith("*") and line_s.endswith("*") and not line_s.startswith(("* ", "*-")):
                subtitle = line_s.strip("* ").strip()
                continue
            elif line_s.startswith("## ") or line_s.startswith("### "):
                sec_name = re.sub(r"^#+\s*", "", line_s).strip()
                if sec_name:
                    current_section = sec_name
                    if sec_name not in sections:
                        sections.append(sec_name)
                continue

            # Check if this line is a bullet item or task
            is_bullet = bool(re.match(r"^[-*+•]\s+", line_s))
            if is_bullet:
                raw_item = re.sub(r"^[-*+•]\s+", "", line_s).strip()
                checked = False
                if raw_item.startswith("[x] ") or raw_item.startswith("[X] "):
                    checked = True
                    raw_item = raw_item[4:].strip()
                elif raw_item.startswith("[ ] "):
                    checked = False
                    raw_item = raw_item[4:].strip()

                # Check if item contains an existing author pill
                pill_match = pill_regex.search(raw_item)
                if pill_match:
                    aid, aname, acolor, atime, arole = pill_match.groups()
                    clean_text = pill_regex.sub("", raw_item).strip()
                    author_meta = {
                        "id": aid or "marcel",
                        "name": aname or "Marcel",
                        "role": arole or "user",
                        "color": acolor or "#10b981",
                        "symbol": "✦"
                    }
                    entry_time = atime or _utcnow_iso()
                else:
                    # New line added by user without a badge
                    clean_text = raw_item.strip()
                    author_meta = DEFAULT_AUTHORS["marcel"]
                    entry_time = _utcnow_iso()

                if clean_text:
                    entries.append({
                        "id": f"e_{uuid.uuid4().hex[:6]}",
                        "section": current_section,
                        "text": clean_text,
                        "checked": checked,
                        "author": author_meta,
                        "timestamp": entry_time
                    })

        if not sections:
            sections = [
                "💡 Ideas & Brainstorming",
                "🛠️ Game & Feature Mechanics",
                "📌 Quick Notes & Next Steps"
            ]

        return {
            "version": 2,
            "title": title,
            "subtitle": subtitle,
            "sections": sections,
            "entries": entries,
            "last_modified": _utcnow_iso()
        }

    def _render_ledger_to_md(self, ledger: Dict[str, Any]) -> str:
        """Render structured ledger entries into a clean markdown document with embedded author pills."""
        entries = ledger.get("entries") or []
        if self._name == "Group" and not entries:
            temp_md = self._md_file.with_suffix(".tmp")
            temp_md.write_text("", encoding="utf-8")
            temp_md.replace(self._md_file)
            return ""
        title = ledger.get("title", "Group Scratchpad" if self._name == "Group" else "Shared Brainstorming Scratchpad")
        subtitle = ledger.get("subtitle", "" if self._name == "Group" else f"A live co-working canvas for Marcel and {self._name}.")
        sections = ledger.get("sections") or [
            "💡 Ideas & Brainstorming",
            "🛠️ Game & Feature Mechanics",
            "📌 Quick Notes & Next Steps"
        ]

        # Group entries by section
        entries_by_section: Dict[str, List[Dict[str, Any]]] = {}
        for sec in sections:
            entries_by_section[sec] = []

        for e in entries:
            sec = e.get("section") or sections[0]
            if sec not in entries_by_section:
                entries_by_section[sec] = []
            entries_by_section[sec].append(e)

        lines = [
            f"# {title}",
            f"*{subtitle}*",
            ""
        ]

        for sec in sections:
            lines.append(f"## {sec}")
            sec_items = entries_by_section.get(sec, [])
            if not sec_items:
                lines.append("- ")
            else:
                for item in sec_items:
                    text = item.get("text", "").strip()
                    checked = item.get("checked", False)
                    chk_prefix = "[x] " if checked else ("[ ] " if checked is not None and "task" in item.get("type", "") else "")
                    author = item.get("author") or DEFAULT_AUTHORS["marcel"]
                    aid = author.get("id", "marcel")
                    aname = author.get("name", "Marcel")
                    acolor = author.get("color", "#10b981")
                    arole = author.get("role", "user")
                    atime = item.get("timestamp", _utcnow_iso())
                    short_name = aname.split()[0] if len(aname.split()) > 1 and len(aname) > 12 else aname

                    pill = (
                        f'<span class="spad-author-pill" data-author-id="{aid}" data-author="{aname}" '
                        f'data-color="{acolor}" data-time="{atime}" data-role="{arole}">✦ {short_name}</span>'
                    )
                    lines.append(f"- {chk_prefix}{pill} {text}")
            lines.append("")

        md_content = "\n".join(lines).strip() + "\n"

        temp_md = self._md_file.with_suffix(".tmp")
        temp_md.write_text(md_content, encoding="utf-8")
        temp_md.replace(self._md_file)
        return md_content

    def load(self) -> Dict[str, Any]:
        """Load both structured ledger and clean markdown representation."""
        with self._lock:
            self._initialize_if_missing()
            try:
                ledger = json.loads(self._ledger_file.read_text(encoding="utf-8"))
            except Exception:
                ledger = {
                    "version": 2,
                    "title": "Shared Brainstorming Scratchpad",
                    "subtitle": f"A live co-working canvas for Marcel and {self._name}.",
                    "sections": [
                        "💡 Ideas & Brainstorming",
                        "🛠️ Game & Feature Mechanics",
                        "📌 Quick Notes & Next Steps"
                    ],
                    "entries": [],
                    "last_modified": _utcnow_iso()
                }

            try:
                md_content = self._md_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                md_content = self._render_ledger_to_md(ledger)

            # Extract distinct contributors
            authors = []
            seen_authors = set()
            for e in ledger.get("entries", []):
                a = e.get("author", {})
                aid = a.get("id")
                if aid and aid not in seen_authors:
                    seen_authors.add(aid)
                    authors.append(a)

            # Generate clean plain text without HTML spans for LLM context
            plain_lines = []
            for line in md_content.split("\n"):
                cleaned = re.sub(r'<span class="spad-author-pill"[^>]*>✦?\s*([^<]+)</span>\s*', r'[\1] ', line)
                plain_lines.append(cleaned)
            plain_text = "\n".join(plain_lines)

            return {
                "companion_name": self._name,
                "content": md_content,
                "plain_text": plain_text,
                "ledger": ledger,
                "entries": ledger.get("entries", []),
                "sections": ledger.get("sections", []),
                "authors": authors,
                "last_modified": ledger.get("last_modified", _utcnow_iso()),
            }

    def save(self, raw_markdown: str) -> Dict[str, Any]:
        """
        Save manual edits from the markdown textarea.
        Reconciles with existing ledger so authors and IDs are retained.
        """
        with self._lock:
            reconciled = self._parse_markdown_into_ledger(raw_markdown)
            atomic_json_write(self._ledger_file, reconciled)
            md_content = self._render_ledger_to_md(reconciled)

            authors = []
            seen_authors = set()
            for e in reconciled.get("entries", []):
                a = e.get("author", {})
                aid = a.get("id")
                if aid and aid not in seen_authors:
                    seen_authors.add(aid)
                    authors.append(a)

            return {
                "status": "saved",
                "companion_name": self._name,
                "content": md_content,
                "entries": reconciled.get("entries", []),
                "sections": reconciled.get("sections", []),
                "authors": authors,
                "last_modified": reconciled.get("last_modified"),
            }

    def append_note(
        self,
        text: str,
        section: Optional[str] = None,
        author: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Thread-safe, atomic append of a new note/entry into the scratchpad ledger.
        """
        note_text = text.strip()
        if not note_text:
            return self.load()

        # Clean any leading bullet dashes from input
        clean_note = re.sub(r"^[-*+•]\s+", "", note_text).strip()
        if not clean_note:
            return self.load()

        with self._lock:
            self._initialize_if_missing()
            try:
                ledger = json.loads(self._ledger_file.read_text(encoding="utf-8"))
            except Exception:
                ledger = self._parse_markdown_into_ledger("")

            sections = ledger.setdefault("sections", [
                "💡 Ideas & Brainstorming",
                "🛠️ Game & Feature Mechanics",
                "📌 Quick Notes & Next Steps"
            ])
            entries = ledger.setdefault("entries", [])

            # Match target section, or create a new topic section if explicitly given
            target_sec = None
            if section and section.strip():
                sec_clean = section.strip()
                sec_needle = sec_clean.lower()
                for s in sections:
                    if sec_needle == s.lower() or sec_needle in s.lower():
                        target_sec = s
                        break
                if not target_sec:
                    target_sec = sec_clean
                    sections.append(target_sec)

            if not target_sec:
                # Default to Ideas or Quick Notes or first section
                for candidate in ("Ideas", "Brainstorming", "Quick Notes"):
                    for s in sections:
                        if candidate.lower() in s.lower():
                            target_sec = s
                            break
                    if target_sec:
                        break
            if not target_sec:
                target_sec = sections[0] if sections else "Ideas"
                if target_sec not in sections:
                    sections.append(target_sec)

            # Resolve author metadata
            author_meta = _resolve_author_info(author, default_id=self._dir.name, default_name=self._name)

            new_entry = {
                "id": f"e_{uuid.uuid4().hex[:6]}",
                "section": target_sec,
                "text": clean_note,
                "checked": False,
                "author": author_meta,
                "timestamp": _utcnow_iso()
            }
            entries.append(new_entry)
            ledger["last_modified"] = _utcnow_iso()

            atomic_json_write(self._ledger_file, ledger)
            md_content = self._render_ledger_to_md(ledger)

            authors = []
            seen_authors = set()
            for e in entries:
                a = e.get("author", {})
                aid = a.get("id")
                if aid and aid not in seen_authors:
                    seen_authors.add(aid)
                    authors.append(a)

            self._info(f"Appended note by {author_meta['name']} under '{target_sec}': {clean_note}")
            return {
                "status": "appended",
                "entry": new_entry,
                "message": f"Added note to '{target_sec}' by {author_meta['name']}: {clean_note}",
                "content": md_content,
                "sections": sections,
                "authors": authors,
                "last_modified": ledger["last_modified"]
            }

    def clear(self, reset_template: bool = True) -> Dict[str, Any]:
        """Reset the scratchpad back to empty (Group) or default template."""
        with self._lock:
            is_group = self._name == "Group"
            init_ledger = {
                "version": 2,
                "title": "Group Scratchpad" if is_group else "Shared Brainstorming Scratchpad",
                "subtitle": "" if is_group else f"A live co-working canvas for Marcel and {self._name}. Jot down ideas, mechanics, and plans here.",
                "sections": [] if is_group else [
                    "💡 Ideas & Brainstorming",
                    "🛠️ Game & Feature Mechanics",
                    "📌 Quick Notes & Next Steps"
                ],
                "entries": [],
                "last_modified": _utcnow_iso()
            }
            atomic_json_write(self._ledger_file, init_ledger)
            md_content = self._render_ledger_to_md(init_ledger)
            return {
                "status": "cleared",
                "content": md_content,
                "sections": init_ledger["sections"],
                "last_modified": init_ledger["last_modified"]
            }
