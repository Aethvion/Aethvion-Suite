"""
core/companions/engine/memory.py
════════════════════════════════
CompanionMemory — base_info.json + memory.json for any companion.
One instance per companion; handles init, load, XML-tag extraction, and synthesis.
"""
from __future__ import annotations
import datetime
import json
import re
import uuid
from pathlib import Path
from core.utils.logger import get_logger

logger = get_logger(__name__)


class CompanionMemory:
    """
    Manages a companion's persistent memory files.

        data_dir/
            base_info.json  — identity / personality (evolves slowly via XML tags or synthesis)
            memory.json     — dynamic facts about the user + observations
    """

    def __init__(self, data_dir: Path, default_base_info: dict, companion_name: str = "Companion"):
        self._dir = data_dir
        self._default_base_info = default_base_info
        self._name = companion_name
        self._base_path = data_dir / "base_info.json"
        self._mem_path = data_dir / "memory.json"

    # ── Initialisation ────────────────────────────────────────────────────

    def initialize(self) -> None:
        """Write default files if missing or empty. Safe to call multiple times."""
        self._dir.mkdir(parents=True, exist_ok=True)

        if not self._base_path.exists() or self._base_path.stat().st_size == 0:
            # Before writing, unwrap if double-nested:
            default_to_write = self._default_base_info.get("base_info", self._default_base_info)
            self._base_path.write_text(
                json.dumps(default_to_write, indent=4, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info(f"{self._name}: Initialized base_info.json")

        if not self._mem_path.exists() or self._mem_path.stat().st_size == 0:
            self._mem_path.write_text(
                json.dumps(
                    {
                        "user_info": {},
                        "recent_observations": [],
                        "synthesis_notes": [],
                        "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    },
                    indent=4,
                ),
                encoding="utf-8",
            )
            logger.info(f"{self._name}: Initialized memory.json")

    # ── Load ──────────────────────────────────────────────────────────────

    def load(self) -> dict:
        """Return {"base_info": {...}, "memory": {...}}."""
        base_info: dict = {}
        memory: dict = {}
        try:
            if self._base_path.exists():
                base_info = json.loads(self._base_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"{self._name}: Failed to load base_info.json: {e}")
        try:
            if self._mem_path.exists():
                memory = json.loads(self._mem_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"{self._name}: Failed to load memory.json: {e}")
        return {"base_info": base_info, "memory": memory}

    # ── XML tag extraction ────────────────────────────────────────────────

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
            # Fallback: Look for bare JSON containing memory keys
            json_match = re.search(r'(\{\s*"(?:user_info|recent_observations|base_info)"[\s\S]*?\})', content)
            if json_match:
                raw = json_match.group(1).strip()

        if not raw:
            return content

        try:
            raw = match.group(1).strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
            raw = re.sub(r"```\s*$", "", raw, flags=re.MULTILINE).strip()
            data = json.loads(raw)

            # Update base_info.json
            if "base_info" in data and self._base_path.exists():
                existing = json.loads(self._base_path.read_text(encoding="utf-8"))
                existing.update(data["base_info"])
                self._base_path.write_text(
                    json.dumps(existing, indent=4, ensure_ascii=False), encoding="utf-8"
                )

            # Update memory.json
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
            existing_mem["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._mem_path.write_text(
                json.dumps(existing_mem, indent=4, ensure_ascii=False), encoding="utf-8"
            )

            logger.info(f"{self._name}: Memory updated from XML tag.")
        except Exception as e:
            logger.error(f"{self._name}: Memory XML update failed: {e}")

        return re.sub(
            r"<memory_update>.*?</memory_update>",
            "",
            content,
            flags=re.DOTALL | re.IGNORECASE,
        ).strip()

    # ── Hard reset ────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Wipe dynamic memory.json only; keep base_info intact."""
        self._mem_path.write_text("{}", encoding="utf-8")
        logger.info(f"{self._name}: Dynamic memory reset.")

    # ── Synthesis ─────────────────────────────────────────────────────────

    async def run_synthesis(self, base_info: dict, memory: dict, model: str) -> dict:
        """
        Trigger a dedicated LLM call to reflect on and consolidate memory.
        Returns the updated memory dict (also persisted to disk).
        """
        from core.providers.provider_manager import ProviderManager

        prompt = (
            f"You are performing a deep memory synthesis for {self._name}.\n\n"
            f"Current identity:\n{json.dumps(base_info, indent=2)}\n\n"
            f"Current memory:\n{json.dumps(memory, indent=2)}\n\n"
            "Tasks:\n"
            "1. CLEANUP: Remove outdated/redundant observations.\n"
            "2. REFLECTION: Evolve identity/goals based on recent interactions.\n"
            "3. SYNTHESIZE: Extract 2-4 key insights about the user.\n\n"
            "Return ONLY a valid JSON object:\n"
            "{\n"
            '    "base_info": { ...updated identity... },\n'
            '    "memory": {\n'
            '        "user_info": { ... },\n'
            '        "recent_observations": [ ...10 most meaningful... ],\n'
            '        "synthesis_notes": [ ...2-4 insights... ]\n'
            "    }\n"
            "}"
        )

        try:
            pm = ProviderManager()
            resp = pm.call_with_failover(
                prompt=prompt,
                trace_id=f"{self._name.lower().replace(' ', '_')}-synthesis-{uuid.uuid4().hex[:8]}",
                temperature=0.4,
                model=model,
                request_type="generation",
                source=f"{self._name.lower().replace(' ', '_')}-synthesis",
            )
            if not resp.success:
                logger.error(f"{self._name}: Synthesis LLM call failed: {resp.error}")
                return memory

            raw = resp.content.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
            raw = re.sub(r"```\s*$", "", raw, flags=re.MULTILINE).strip()
            data = json.loads(raw)

            if "base_info" in data:
                self._base_path.write_text(
                    json.dumps(data["base_info"], indent=4, ensure_ascii=False),
                    encoding="utf-8",
                )
                logger.info(f"{self._name}: Identity updated during synthesis.")

            synthesized: dict = data.get("memory", {})
            synthesized["last_synthesis"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._mem_path.write_text(
                json.dumps(synthesized, indent=4, ensure_ascii=False), encoding="utf-8"
            )
            logger.info(f"{self._name}: Memory synthesis complete.")
            return synthesized
        except Exception as e:
            logger.error(f"{self._name}: Synthesis failed: {e}")
            return memory
