"""
core/companions/engine/visual_memory.py
CompanionVisualMemory — persistent long-term visual context memory.
Allows companions to snapshot, index, describe, remember, and compare
visual states across days (Unity project layouts, Blender 3D models,
IDE code architectures, UI wireframes, and reference artwork).
"""
from __future__ import annotations
import datetime
import json
import re
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from core.utils import atomic_json_write, get_logger, utcnow_iso
from .base import CompanionComponent

logger = get_logger(__name__)

# Directory-level locks to ensure thread-safe concurrent writes
_VISUAL_MEMORY_LOCKS: Dict[str, threading.RLock] = {}
_LOCKS_MUTEX = threading.Lock()

DEFAULT_CATEGORIES = {
    "unity": {"name": "Unity Layouts", "icon": "fa-cube", "color": "#6366f1"},
    "blender": {"name": "Blender 3D Models", "icon": "fa-shapes", "color": "#f97316"},
    "code": {"name": "Code & IDE Layouts", "icon": "fa-code", "color": "#3b82f6"},
    "ui": {"name": "UI & Design", "icon": "fa-pen-ruler", "color": "#10b981"},
    "reference": {"name": "Art & References", "icon": "fa-image", "color": "#ec4899"},
    "general": {"name": "General Desktop", "icon": "fa-desktop", "color": "#8b5cf6"},
}


def _get_dir_lock(dir_path: Path) -> threading.RLock:
    key = str(dir_path.resolve())
    with _LOCKS_MUTEX:
        if key not in _VISUAL_MEMORY_LOCKS:
            _VISUAL_MEMORY_LOCKS[key] = threading.RLock()
        return _VISUAL_MEMORY_LOCKS[key]


class CompanionVisualMemory(CompanionComponent):
    """
    Persistent long-term visual memory manager for a companion.
    Stores visual memory ledger in `visual_memories.json` and snapshots in `visual_snapshots/`.
    """

    def __init__(self, data_dir: Path, companion_name: str = "Companion") -> None:
        super().__init__(data_dir, companion_name)
        self._mem_file = self._dir / "visual_memories.json"
        self._snapshots_dir = self._dir / "visual_snapshots"
        self._snapshots_dir.mkdir(parents=True, exist_ok=True)
        self._lock = _get_dir_lock(self._dir)
        self._initialize_if_missing()

    def _initialize_if_missing(self) -> None:
        with self._lock:
            if not self._mem_file.exists() or self._mem_file.stat().st_size == 0:
                init_data = {
                    "version": 1,
                    "companion_name": self._name,
                    "companion_id": self._dir.name,
                    "created_at": utcnow_iso(),
                    "last_updated": utcnow_iso(),
                    "memories": []
                }
                atomic_json_write(self._mem_file, init_data, indent=2)
                self._info(f"Initialized visual_memories.json for {self._name}")

    def load(self) -> Dict[str, Any]:
        """Load all visual memories with categorized statistics."""
        with self._lock:
            self._initialize_if_missing()
            try:
                data = json.loads(self._mem_file.read_text(encoding="utf-8"))
            except Exception as e:
                self._error(f"Failed to read visual_memories.json: {e}")
                data = {"version": 1, "companion_name": self._name, "memories": []}

            memories: List[Dict[str, Any]] = data.get("memories", [])
            # Sort memories by timestamp descending (newest first)
            memories.sort(key=lambda m: m.get("timestamp", ""), reverse=True)

            # Calculate category statistics
            cat_counts: Dict[str, int] = {}
            for m in memories:
                cat = m.get("category", "general").lower()
                cat_counts[cat] = cat_counts.get(cat, 0) + 1

            cid = self._dir.name
            # Ensure each memory has valid URL for frontend rendering
            for m in memories:
                fname = m.get("filename")
                if fname and not m.get("url"):
                    m["url"] = f"/api/companions/{cid}/visual-memory/snapshots/{fname}"

            return {
                "companion_name": self._name,
                "companion_id": cid,
                "total": len(memories),
                "categories": DEFAULT_CATEGORIES,
                "category_counts": cat_counts,
                "memories": memories,
                "last_updated": data.get("last_updated", utcnow_iso())
            }

    def _save_data(self, data: Dict[str, Any]) -> None:
        data["last_updated"] = utcnow_iso()
        atomic_json_write(self._mem_file, data, indent=2)

    def remember(
        self,
        title: str,
        category: str = "general",
        description: str = "",
        key_elements: Optional[List[str]] = None,
        image_path: Optional[str] = None,
        monitor: int = 0,
        tags: Optional[List[str]] = None,
        source: str = "screen_capture",
    ) -> Dict[str, Any]:
        """
        Record and index a visual memory. If `image_path` is not provided,
        captures the live screen on the specified monitor via mss.
        """
        clean_title = (title or "").strip() or f"Visual Memory ({category.capitalize()})"
        clean_cat = (category or "general").strip().lower()
        if clean_cat not in DEFAULT_CATEGORIES:
            # Map common synonyms
            if any(k in clean_cat for k in ("unity", "game", "scene", "level")):
                clean_cat = "unity"
            elif any(k in clean_cat for k in ("blender", "model", "3d", "mesh")):
                clean_cat = "blender"
            elif any(k in clean_cat for k in ("code", "ide", "vscode", "visual studio")):
                clean_cat = "code"
            elif any(k in clean_cat for k in ("ui", "ux", "wireframe", "design", "layout")):
                clean_cat = "ui"
            elif any(k in clean_cat for k in ("ref", "art", "inspire", "photo")):
                clean_cat = "reference"
            else:
                clean_cat = "general"

        mem_id = f"vmem_{uuid.uuid4().hex[:8]}"
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        target_filename = f"snap_{timestamp_str}_{mem_id}.png"
        saved_file = self._snapshots_dir / target_filename

        width, height = 0, 0

        # Step 1: Capture or copy image
        if image_path and Path(image_path).exists() and Path(image_path).is_file():
            src_p = Path(image_path)
            try:
                import shutil
                shutil.copy2(src_p, saved_file)
            except Exception as copy_err:
                self._error(f"Failed to copy image from {image_path}: {copy_err}")
                return {"error": f"Failed to save image: {copy_err}"}
        else:
            # Live screen capture using mss
            try:
                import mss
                import mss.tools
                with mss.mss() as sct:
                    monitors = sct.monitors
                    target_idx = monitor
                    if target_idx < 0 or target_idx >= len(monitors):
                        target_idx = 1 if len(monitors) > 1 else 0
                    target_mon = monitors[target_idx]
                    sct_img = sct.grab(target_mon)
                    mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(saved_file))
                    width, height = sct_img.width, sct_img.height
            except Exception as sct_err:
                self._error(f"Screen capture failed for visual memory: {sct_err}")
                return {"error": f"Could not capture screen: {sct_err}"}

        # Step 2: Read dimensions if not already known
        if width == 0 or height == 0:
            try:
                from PIL import Image
                with Image.open(saved_file) as im:
                    width, height = im.size
            except Exception:
                pass

        cid = self._dir.name
        created_iso = utcnow_iso()
        dt_obj = datetime.datetime.now()
        human_time = dt_obj.strftime("%b %d, %Y at %H:%M")

        clean_elements = [str(e).strip() for e in (key_elements or []) if str(e).strip()]
        clean_tags = [str(t).strip().lower() for t in (tags or []) if str(t).strip()]
        if clean_cat not in clean_tags:
            clean_tags.insert(0, clean_cat)

        new_entry = {
            "id": mem_id,
            "title": clean_title,
            "category": clean_cat,
            "description": description.strip(),
            "key_elements": clean_elements,
            "image_path": str(saved_file.resolve()),
            "filename": target_filename,
            "url": f"/api/companions/{cid}/visual-memory/snapshots/{target_filename}",
            "width": width,
            "height": height,
            "monitor": monitor,
            "source": source,
            "tags": clean_tags,
            "timestamp": created_iso,
            "human_time": human_time,
        }

        with self._lock:
            self._initialize_if_missing()
            data = json.loads(self._mem_file.read_text(encoding="utf-8"))
            memories: List[Dict[str, Any]] = data.setdefault("memories", [])
            memories.insert(0, new_entry)
            self._save_data(data)

        self._info(f"Visual memory '{clean_title}' saved ({clean_cat}, {width}x{height}) -> {saved_file.name}")
        return {
            "status": "saved",
            "message": f"Visual memory '{clean_title}' recorded successfully.",
            "memory": new_entry,
            "file_path": str(saved_file.resolve())
        }

    def search(
        self,
        query: str = "",
        category: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Search stored visual memories by query keywords, category, or tags."""
        loaded = self.load()
        memories = loaded.get("memories", [])
        if not memories:
            return []

        q_terms = [t.lower() for t in re.findall(r"\w+", query)] if query else []
        cat_filter = category.strip().lower() if category and category.strip() else None

        results = []
        for m in memories:
            m_cat = m.get("category", "").lower()
            if cat_filter and cat_filter != "all" and m_cat != cat_filter:
                continue

            if not q_terms:
                results.append((1.0, m))
                continue

            searchable = (
                f"{m.get('title', '')} {m.get('description', '')} "
                f"{m.get('category', '')} {' '.join(m.get('key_elements', []))} "
                f"{' '.join(m.get('tags', []))}"
            ).lower()

            matches = sum(1 for term in q_terms if term in searchable)
            if matches > 0:
                score = matches / len(q_terms)
                results.append((score, m))

        results.sort(key=lambda r: (r[0], r[1].get("timestamp", "")), reverse=True)
        return [r[1] for r in results[:limit]]

    def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific visual memory by ID."""
        loaded = self.load()
        for m in loaded.get("memories", []):
            if m.get("id") == memory_id:
                return m
        return None

    def update(self, memory_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update metadata on an existing visual memory."""
        with self._lock:
            self._initialize_if_missing()
            data = json.loads(self._mem_file.read_text(encoding="utf-8"))
            memories: List[Dict[str, Any]] = data.get("memories", [])
            target = None
            for m in memories:
                if m.get("id") == memory_id:
                    target = m
                    break
            if not target:
                return None

            for field in ("title", "category", "description", "key_elements", "tags"):
                if field in updates:
                    target[field] = updates[field]

            self._save_data(data)
            return target

    def delete(self, memory_id: str) -> bool:
        """Delete a visual memory and its snapshot image."""
        with self._lock:
            self._initialize_if_missing()
            data = json.loads(self._mem_file.read_text(encoding="utf-8"))
            memories: List[Dict[str, Any]] = data.get("memories", [])
            initial_count = len(memories)
            deleted_file = None
            filtered = []
            for m in memories:
                if m.get("id") == memory_id:
                    deleted_file = m.get("image_path")
                else:
                    filtered.append(m)

            if len(filtered) == initial_count:
                return False

            data["memories"] = filtered
            self._save_data(data)

            # Cleanup snapshot image file if inside snapshots dir
            if deleted_file:
                try:
                    p = Path(deleted_file).resolve()
                    snap_dir = self._snapshots_dir.resolve()
                    if p.exists() and (snap_dir == p.parent or snap_dir in p.parents):
                        p.unlink(missing_ok=True)
                except Exception as e:
                    self._error(f"Could not remove snapshot file {deleted_file}: {e}")

            return True

    def compare(
        self,
        current_image_path: Optional[str] = None,
        memory_id: Optional[str] = None,
        query: Optional[str] = None,
        monitor: int = 0
    ) -> Dict[str, Any]:
        """
        Compare current screen state with a remembered visual memory.
        Returns the reference visual memory details and current snapshot path.
        """
        target_memory = None
        if memory_id:
            target_memory = self.get(memory_id)
        elif query:
            matches = self.search(query=query, limit=1)
            if matches:
                target_memory = matches[0]

        if not target_memory:
            # Fall back to most recent visual memory
            loaded = self.load()
            mems = loaded.get("memories", [])
            if mems:
                target_memory = mems[0]

        if not target_memory:
            return {
                "error": "No visual memory found to compare with. Take a snapshot first with remember_screen."
            }

        # Step 2: Ensure we have a current screenshot
        curr_path = current_image_path
        if not curr_path or not Path(curr_path).exists():
            timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            curr_file = self._snapshots_dir / f"compare_curr_{timestamp_str}.png"
            try:
                import mss
                import mss.tools
                with mss.mss() as sct:
                    monitors = sct.monitors
                    t_idx = monitor if 0 <= monitor < len(monitors) else (1 if len(monitors) > 1 else 0)
                    sct_img = sct.grab(monitors[t_idx])
                    mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(curr_file))
                    curr_path = str(curr_file.resolve())
            except Exception as e:
                curr_path = None

        return {
            "status": "ready_to_compare",
            "reference_memory": target_memory,
            "current_image_path": curr_path,
            "reference_image_path": target_memory.get("image_path")
        }

    def get_recent_summary_for_context(self, limit: int = 4) -> str:
        """
        Format a concise summary of recent visual memories for prompt context injection.
        """
        loaded = self.load()
        memories = loaded.get("memories", [])
        if not memories:
            return ""

        lines = ["VISUAL CONTEXT MEMORY ON FILE:"]
        for m in memories[:limit]:
            title = m.get("title", "Untitled Layout")
            cat = m.get("category", "general").upper()
            t_human = m.get("human_time") or m.get("timestamp", "")[:10]
            desc = m.get("description", "").strip()
            elems = m.get("key_elements", [])
            elem_str = f" | Key elements: {', '.join(elems[:3])}" if elems else ""
            desc_str = f" — {desc[:120]}..." if len(desc) > 120 else (f" — {desc}" if desc else "")
            lines.append(f"- [{cat}] {title} ({t_human}){desc_str}{elem_str}")

        lines.append("You can recall detailed past layouts or compare current screens anytime using the visual_memory connector.")
        return "\n".join(lines)
