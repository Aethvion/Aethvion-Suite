"""
tests/conftest.py
═════════════════
Shared pytest fixtures for the Aethvion Suite test suite.

All fixtures that touch the filesystem use isolated tmp_path directories so
they cannot interfere with a developer's live data.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make the project root importable without `pip install -e .`
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# AethvionDB fixtures

@pytest.fixture()
def db_dir(tmp_path: Path) -> Path:
    """Return a fresh, empty AethvionDB root directory."""
    d = tmp_path / "aethviondb" / "test_db"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture()
def name_index(db_dir: Path):
    """Return a NameIndex backed by a temporary directory."""
    from core.aethviondb.name_index import NameIndex
    return NameIndex(index_path=db_dir / "name_index.json")


@pytest.fixture()
def entity_writer(db_dir: Path, name_index):
    """Return an EntityWriter backed by isolated tmp directories."""
    from core.aethviondb.entity_writer import EntityWriter
    entities_dir = db_dir / "entities"
    entities_dir.mkdir(parents=True, exist_ok=True)
    return EntityWriter(entities_dir=entities_dir, index=name_index)


# Companion fixtures

@pytest.fixture()
def companion_config_dir(tmp_path: Path) -> Path:
    """Return a directory containing a minimal companion JSON config."""
    cfg_dir = tmp_path / "companion_configs"
    cfg_dir.mkdir()
    (cfg_dir / "test_companion.json").write_text(
        json.dumps({
            "id": "test_companion",
            "name": "Test Companion",
            "description": "A companion used only in tests",
            "default_model": "gemini-2.0-flash",
            "route_prefix": "/api/test_companion",
            "call_source": "test_companion",
            "prefs_key": "test_companion",
            "moods": ["calm", "happy"],
            "expressions": ["default", "smile"],
        }),
        encoding="utf-8",
    )
    return cfg_dir