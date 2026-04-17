"""
core/companions/registry.py
═══════════════════════════
Dynamic, data-driven registry for all Aethvion companions.
Scans for JSON configurations in core blueprints and runtime data directories.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from core.utils.paths import COMPANIONS as _DATA_ROOT
_CONFIG_DIR = Path(__file__).parent / "configs"

@dataclass
class CompanionConfig:
    id: str
    name: str
    description: str
    route_prefix: str
    call_source: str
    prefs_key: str
    default_model: str
    default_expression: str = "default"
    moods: List[str] = field(default_factory=lambda: ["calm"])
    expressions: List[str] = field(default_factory=lambda: ["default"])
    static_dir: str = ""
    data_dir: Path = field(default_factory=Path)
    history_dir: Path = field(default_factory=Path)
    _raw_config: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, json_path: Path) -> "CompanionConfig":
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        cid = data["id"]
        c_data_dir = _DATA_ROOT / cid
        
        return cls(
            id=cid,
            name=data["name"],
            description=data["description"],
            route_prefix=data.get("route_prefix", f"/api/{cid}"),
            call_source=data.get("call_source", cid),
            prefs_key=data.get("prefs_key", cid),
            default_model=data["default_model"],
            default_expression=data.get("default_expression", "default"),
            moods=data.get("moods", ["calm"]),
            expressions=data.get("expressions", ["default"]),
            static_dir=f"companions/{cid}",
            data_dir=c_data_dir,
            history_dir=c_data_dir / "history",
            _raw_config=data
        )

class CompanionRegistry:
    _companions: Dict[str, CompanionConfig] = {}
    _loaded: bool = False

    @classmethod
    def load_all(cls):
        """Scan core and data dirs. Data overrides Core templates."""
        cls._companions = {}
        
        # 1. Load core templates as baseline
        if _CONFIG_DIR.exists():
            for file in _CONFIG_DIR.glob("*.json"):
                try:
                    cfg = CompanionConfig.from_json(file)
                    cls._companions[cfg.id] = cfg
                except Exception as e:
                    print(f"Error loading companion template {file.name}: {e}")
        
        # 2. Overwrite/Add with active state or custom companions from data/
        if _DATA_ROOT.exists():
            for c_dir in _DATA_ROOT.iterdir():
                if not c_dir.is_dir():
                    continue
                config_file = c_dir / "config.json"
                if config_file.exists():
                    try:
                        cfg = CompanionConfig.from_json(config_file)
                        cls._companions[cfg.id] = cfg
                    except Exception as e:
                        print(f"Error loading companion state {c_dir.name}: {e}")
        
        cls._loaded = True

    @classmethod
    def get_companion(cls, companion_id: str) -> Optional[CompanionConfig]:
        if not cls._loaded:
            cls.load_all()
        return cls._companions.get(companion_id)

    @classmethod
    def list_companions(cls) -> List[CompanionConfig]:
        if not cls._loaded:
            cls.load_all()
        return list(cls._companions.values())

def get_companion(companion_id: str) -> Optional[CompanionConfig]:
    """Helper for backward compatibility where needed."""
    return CompanionRegistry.get_companion(companion_id)
