"""
core/companions/engine/scratchpad.py
CompanionScratchpad — persistent co-working brainstorming canvas & scratchpad
shared between the user (Marcel) and the active companion.
"""
from __future__ import annotations
import datetime
import re
from pathlib import Path
from typing import Optional, List, Dict, Any
from .base import CompanionComponent

DEFAULT_SCRATCHPAD_TEMPLATE = """# Shared Brainstorming Scratchpad
*A live co-working canvas for Marcel and {companion_name}. Jot down ideas, mechanics, and plans here.*

## 💡 Ideas & Brainstorming
- 

## 🛠️ Game & Feature Mechanics
- 

## 📌 Quick Notes & Next Steps
- 
"""


def _utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class CompanionScratchpad(CompanionComponent):
    """
    Manages a markdown-based shared scratchpad for a companion.
    Thread-safe reads and atomic writes.
    """

    def __init__(self, data_dir: Path, companion_name: str = "Companion") -> None:
        super().__init__(data_dir, companion_name)
        self._file = self._dir / "scratchpad.md"
        self._initialize_if_missing()

    def _initialize_if_missing(self) -> None:
        if not self._file.exists():
            tmpl = DEFAULT_SCRATCHPAD_TEMPLATE.format(companion_name=self._name)
            self._file.write_text(tmpl, encoding="utf-8")
            self._info(f"Initialized scratchpad for {self._name} at {self._file}")

    def load(self) -> Dict[str, Any]:
        """Load the scratchpad content and metadata."""
        self._initialize_if_missing()
        try:
            content = self._file.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            self._error(f"Failed to read scratchpad: {e}")
            content = DEFAULT_SCRATCHPAD_TEMPLATE.format(companion_name=self._name)

        stat = self._file.stat() if self._file.exists() else None
        mtime_iso = (
            datetime.datetime.fromtimestamp(stat.st_mtime, datetime.timezone.utc).isoformat()
            if stat
            else _utcnow_iso()
        )

        return {
            "companion_name": self._name,
            "content": content,
            "last_modified": mtime_iso,
            "sections": self.get_sections(content),
        }

    def save(self, content: str) -> Dict[str, Any]:
        """Atomically overwrite scratchpad markdown content."""
        clean_content = content.replace("\r\n", "\n")
        self._dir.mkdir(parents=True, exist_ok=True)
        temp_file = self._file.with_suffix(".tmp")
        temp_file.write_text(clean_content, encoding="utf-8")
        temp_file.replace(self._file)

        return {
            "status": "saved",
            "companion_name": self._name,
            "content": clean_content,
            "last_modified": _utcnow_iso(),
            "sections": self.get_sections(clean_content),
        }

    def get_sections(self, content: Optional[str] = None) -> List[str]:
        """Extract markdown headings (## or ###) as available scratchpad sections."""
        if content is None:
            content = self.load().get("content", "")
        headings = []
        for line in content.split("\n"):
            line_s = line.strip()
            if line_s.startswith("## ") or line_s.startswith("### "):
                title = re.sub(r"^#+\s*", "", line_s).strip()
                if title:
                    headings.append(title)
        return headings

    def append_note(self, text: str, section: Optional[str] = None) -> Dict[str, Any]:
        """
        Append a bullet point or text block to the scratchpad.
        If section is provided, locates that section and inserts the bullet item there.
        """
        note_text = text.strip()
        if not note_text:
            return self.load()

        formatted_item = note_text if note_text.startswith(("- ", "* ", "1. ", "• ")) else f"- {note_text}"

        current = self.load().get("content", "")
        lines = current.split("\n")

        target_idx = -1
        matched_section_name = None

        if section and section.strip():
            clean_sec = section.strip().lower()
            for idx, line in enumerate(lines):
                line_lower = line.strip().lower()
                if (line_lower.startswith("## ") or line_lower.startswith("### ")) and clean_sec in line_lower:
                    target_idx = idx
                    matched_section_name = re.sub(r"^#+\s*", "", line.strip())
                    break

        # If section matched, find the end of that section (before the next heading or EOF)
        if target_idx != -1:
            insert_pos = len(lines)
            for j in range(target_idx + 1, len(lines)):
                next_line = lines[j].strip()
                if next_line.startswith("## ") or next_line.startswith("### "):
                    insert_pos = j
                    break

            # Strip empty trailing lines right before the next heading
            while insert_pos > target_idx + 1 and not lines[insert_pos - 1].strip():
                insert_pos -= 1

            lines.insert(insert_pos, formatted_item)
            new_content = "\n".join(lines)
            save_res = self.save(new_content)
            save_res["message"] = f"Added note to '{matched_section_name}': {note_text}"
            return save_res

        # Fallback 1: Look for "Quick Notes" or "Ideas"
        for default_name in ("Quick Notes", "Ideas", "Brainstorming"):
            for idx, line in enumerate(lines):
                if line.strip().startswith("## ") and default_name.lower() in line.lower():
                    matched_section_name = line.strip()
                    insert_pos = len(lines)
                    for j in range(idx + 1, len(lines)):
                        if lines[j].strip().startswith("## "):
                            insert_pos = j
                            break
                    while insert_pos > idx + 1 and not lines[insert_pos - 1].strip():
                        insert_pos -= 1
                    lines.insert(insert_pos, formatted_item)
                    new_content = "\n".join(lines)
                    save_res = self.save(new_content)
                    save_res["message"] = f"Added note to '{default_name}': {note_text}"
                    return save_res

        # Fallback 2: Append at end of document
        lines.append(formatted_item)
        new_content = "\n".join(lines)
        save_res = self.save(new_content)
        save_res["message"] = f"Appended note to scratchpad: {note_text}"
        return save_res

    def clear(self, reset_template: bool = True) -> Dict[str, Any]:
        """Reset the scratchpad to default template or empty."""
        new_content = DEFAULT_SCRATCHPAD_TEMPLATE.format(companion_name=self._name) if reset_template else ""
        return self.save(new_content)
