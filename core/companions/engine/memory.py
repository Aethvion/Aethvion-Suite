"""
core/companions/engine/memory.py
CompanionMemory — base_info.json + memory.json for any companion.
One instance per companion; handles init, load, XML-tag extraction, and synthesis.
"""
from __future__ import annotations
import json
import re
import uuid
from pathlib import Path
from core.utils import utcnow_iso, atomic_json_write
from .base import CompanionComponent


class CompanionMemory(CompanionComponent):
    """
    Manages a companion's persistent memory files.

        data_dir/
            base_info.json  — identity / personality (evolves slowly via XML tags or synthesis)
            memory.json     — dynamic facts about the user + observations
    """

    def __init__(self, data_dir: Path, default_base_info: dict, companion_name: str = "Companion"):
        super().__init__(data_dir, companion_name)
        self._default_base_info = default_base_info
        self._base_path = data_dir / "base_info.json"
        self._mem_path  = data_dir / "memory.json"

    # Initialisation

    def initialize(self) -> None:
        """Write default files if missing or empty. Safe to call multiple times."""
        # _dir already created by CompanionComponent.__init__
        if not self._base_path.exists() or self._base_path.stat().st_size == 0:
            # Unwrap if double-nested before writing
            default_to_write = self._default_base_info.get("base_info", self._default_base_info)
            atomic_json_write(self._base_path, default_to_write, indent=4)
            self._info("Initialized base_info.json")

        if not self._mem_path.exists() or self._mem_path.stat().st_size == 0:
            atomic_json_write(self._mem_path, {
                "user_info": {},
                "recent_observations": [],
                "synthesis_notes": [],
                "last_updated": utcnow_iso(),
            }, indent=4)
            self._info("Initialized memory.json")

    # Load

    def load(self) -> dict:
        """Return {"base_info": {...}, "memory": {...}}."""
        base_info: dict = {}
        memory: dict = {}
        try:
            if self._base_path.exists():
                base_info = json.loads(self._base_path.read_text(encoding="utf-8"))
        except Exception as e:
            self._error(f"Failed to load base_info.json: {e}")
        try:
            if self._mem_path.exists():
                memory = json.loads(self._mem_path.read_text(encoding="utf-8"))
        except Exception as e:
            self._error(f"Failed to load memory.json: {e}")
        return {"base_info": base_info, "memory": memory}

    # XML tag extraction

    def update_from_xml(self, content: str) -> str:
        """
        Find <memory_update>...</memory_update> in content.
        Parse the JSON, apply the patch to disk, return content with the block stripped.
        """
        match = re.search(
            r"<memory_update>(.*?)</memory_update>",
            content,
            re.DOTALL | re.IGNORECASE,
        )

        raw = ""
        if match:
            raw = match.group(1).strip()
        else:
            # Fallback: look for bare JSON containing memory keys
            json_match = re.search(
                r'(\{\s*"(?:user_info|recent_observations|base_info)"[\s\S]*?\})', content
            )
            if json_match:
                raw = json_match.group(1).strip()

        if not raw:
            return content

        try:
            raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
            raw = re.sub(r"```\s*$", "", raw, flags=re.MULTILINE).strip()
            data = json.loads(raw)

            # Update base_info.json atomically
            if "base_info" in data and self._base_path.exists():
                existing = json.loads(self._base_path.read_text(encoding="utf-8"))
                existing.update(data["base_info"])
                atomic_json_write(self._base_path, existing, indent=4)

            # Update memory.json atomically
            if self._mem_path.exists():
                existing_mem: dict = json.loads(self._mem_path.read_text(encoding="utf-8"))
            else:
                existing_mem = {"user_info": {}, "recent_observations": [], "synthesis_notes": []}

            if "user_info" in data:
                existing_mem.setdefault("user_info", {}).update(data["user_info"])
            if "recent_observations" in data:
                obs: list = existing_mem.get("recent_observations", [])
                obs.extend(data["recent_observations"])
                existing_mem["recent_observations"] = obs[-20:]
            existing_mem["last_updated"] = utcnow_iso()
            atomic_json_write(self._mem_path, existing_mem, indent=4)

            self._info("Memory updated from XML tag.")
        except Exception as e:
            self._error(f"Memory XML update failed: {e}")

        return re.sub(
            r"<memory_update>.*?</memory_update>",
            "",
            content,
            flags=re.DOTALL | re.IGNORECASE,
        ).strip()

    # Hard reset

    def reset(self) -> None:
        """Wipe dynamic memory.json only; keep base_info intact."""
        self._mem_path.write_text("{}", encoding="utf-8")
        self._info("Dynamic memory reset.")

    # Interactive Memory CRUD

    def _load_mem_only(self) -> dict:
        self.initialize()
        try:
            if self._mem_path.exists():
                return json.loads(self._mem_path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {"user_info": {}, "recent_observations": [], "synthesis_notes": []}

    def _save_mem_only(self, mem: dict) -> dict:
        mem["last_updated"] = utcnow_iso()
        atomic_json_write(self._mem_path, mem, indent=4)
        return self.load()

    def set_fact(self, key: str, value: str) -> dict:
        """Add or update a user_info key-value fact."""
        mem = self._load_mem_only()
        mem.setdefault("user_info", {})[key.strip()] = value.strip()
        self._info(f"Fact set: {key.strip()}")
        return self._save_mem_only(mem)

    def delete_fact(self, key: str) -> dict:
        """Delete a user_info fact by key."""
        mem = self._load_mem_only()
        mem.get("user_info", {}).pop(key, None)
        self._info(f"Fact deleted: {key}")
        return self._save_mem_only(mem)

    def add_observation(self, text: str) -> dict:
        """Append a new observation note."""
        mem = self._load_mem_only()
        obs = mem.setdefault("recent_observations", [])
        if text.strip():
            obs.append(text.strip())
        return self._save_mem_only(mem)

    def update_observation(self, index: int, text: str) -> dict:
        """Update an existing observation at index."""
        mem = self._load_mem_only()
        obs = mem.get("recent_observations", [])
        if 0 <= index < len(obs) and text.strip():
            obs[index] = text.strip()
        return self._save_mem_only(mem)

    def delete_observation(self, index: int) -> dict:
        """Remove an observation at index."""
        mem = self._load_mem_only()
        obs = mem.get("recent_observations", [])
        if 0 <= index < len(obs):
            obs.pop(index)
        return self._save_mem_only(mem)

    def delete_synthesis_note(self, index: int) -> dict:
        """Remove a synthesis note at index."""
        mem = self._load_mem_only()
        notes = mem.get("synthesis_notes", [])
        if 0 <= index < len(notes):
            notes.pop(index)
        return self._save_mem_only(mem)

    # Synthesis

    async def run_synthesis(self, base_info: dict, memory: dict, model: str) -> dict:
        """
        Trigger a dedicated LLM call to reflect on and consolidate memory.
        Returns the full loaded {"base_info": ..., "memory": ...} dict.
        Raises ValueError on failure so callers can report the reason.
        """
        import asyncio
        from core.providers.provider_manager import get_provider_manager

        prompt = (
            f"You are performing a deep memory synthesis for {self._name}.\n\n"
            f"Current identity:\n{json.dumps(base_info, indent=2)}\n\n"
            f"Current memory:\n{json.dumps(memory, indent=2)}\n\n"
            "Tasks:\n"
            "1. CLEANUP: Merge duplicate or outdated observations and organize user facts into user_info.\n"
            "2. REFLECTION: Keep or subtly refine identity traits based on recent interactions.\n"
            "3. SYNTHESIZE: Extract 2-5 meaningful, high-level insights about the user into synthesis_notes.\n\n"
            "Return ONLY a valid JSON object matching this exact schema (no markdown commentary):\n"
            "{\n"
            '    "base_info": { ... },\n'
            '    "memory": {\n'
            '        "user_info": { ... },\n'
            '        "recent_observations": [ ... ],\n'
            '        "synthesis_notes": [ ... ]\n'
            "    }\n"
            "}"
        )

        pm = get_provider_manager()
        resp = await asyncio.to_thread(
            pm.call_with_failover,
            prompt=prompt,
            trace_id=f"{self._name.lower().replace(' ', '_')}-synthesis-{uuid.uuid4().hex[:8]}",
            temperature=0.4,
            model=model or "auto",
            request_type="generation",
            source=f"{self._name.lower().replace(' ', '_')}-synthesis",
        )
        if not resp.success:
            self._error(f"Synthesis LLM call failed: {resp.error}")
            raise ValueError(resp.error or "Model synthesis call failed")

        raw = resp.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"```\s*$", "", raw, flags=re.MULTILINE).strip()
        if not raw.startswith("{"):
            m = re.search(r"(\{[\s\S]*\})", raw)
            if m:
                raw = m.group(1)

        data = json.loads(raw)

        if "base_info" in data and isinstance(data["base_info"], dict):
            merged_bi = {**base_info, **data["base_info"]}
            atomic_json_write(self._base_path, merged_bi, indent=4)
            self._info("Identity updated during synthesis.")

        synthesized: dict = data.get("memory", memory)
        if not isinstance(synthesized, dict):
            synthesized = memory
        synthesized.setdefault("user_info", memory.get("user_info", {}))
        synthesized.setdefault("recent_observations", memory.get("recent_observations", []))
        synthesized.setdefault("synthesis_notes", memory.get("synthesis_notes", []))
        synthesized["last_updated"] = utcnow_iso()
        synthesized["last_synthesis"] = utcnow_iso()
        atomic_json_write(self._mem_path, synthesized, indent=4)
        self._info("Memory synthesis complete.")
        return self.load()
