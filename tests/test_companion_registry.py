"""
tests/test_companion_registry.py
══════════════════════════════════
Unit tests for the CompanionRegistry and CompanionConfig.

Tests use isolated tmp directories so they never read or write live companion
data from data/companions/.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.companions.registry import CompanionConfig


# Helpers

def _write_companion_json(cfg_dir: Path, data: dict) -> Path:
    """Write a companion config JSON and return its path."""
    p = cfg_dir / f"{data['id']}.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


MINIMAL_COMPANION = {
    "id": "aria",
    "name": "Aria",
    "description": "A test companion",
    "default_model": "gemini-2.0-flash",
    "route_prefix": "/api/aria",
    "call_source": "aria",
    "prefs_key": "aria",
    "moods": ["calm", "happy"],
    "expressions": ["default"],
}


# CompanionConfig.from_json

class TestCompanionConfigFromJson:
    def test_minimal_config_loads(self, companion_config_dir):
        path = companion_config_dir / "test_companion.json"
        cfg = CompanionConfig.from_json(path)
        assert cfg.id == "test_companion"
        assert cfg.name == "Test Companion"

    def test_default_model_preserved(self, companion_config_dir):
        path = companion_config_dir / "test_companion.json"
        cfg = CompanionConfig.from_json(path)
        assert cfg.default_model == "gemini-2.0-flash"

    def test_moods_list_preserved(self, companion_config_dir):
        path = companion_config_dir / "test_companion.json"
        cfg = CompanionConfig.from_json(path)
        assert "calm" in cfg.moods
        assert "happy" in cfg.moods

    def test_expressions_list_preserved(self, companion_config_dir):
        path = companion_config_dir / "test_companion.json"
        cfg = CompanionConfig.from_json(path)
        assert "default" in cfg.expressions

    def test_aria_minimal(self, tmp_path):
        cfg_dir = tmp_path / "configs"
        cfg_dir.mkdir()
        p = _write_companion_json(cfg_dir, MINIMAL_COMPANION)
        cfg = CompanionConfig.from_json(p)
        assert cfg.id == "aria"
        assert cfg.name == "Aria"
        assert cfg.route_prefix == "/api/aria"

    def test_data_dir_set(self, tmp_path):
        cfg_dir = tmp_path / "configs"
        cfg_dir.mkdir()
        p = _write_companion_json(cfg_dir, MINIMAL_COMPANION)
        cfg = CompanionConfig.from_json(p)
        # data_dir is derived from the paths module — just verify it's a Path
        assert isinstance(cfg.data_dir, Path)

    def test_missing_required_field_raises(self, tmp_path):
        cfg_dir = tmp_path / "configs"
        cfg_dir.mkdir()
        # Omit required "name" field
        broken = {k: v for k, v in MINIMAL_COMPANION.items() if k != "name"}
        p = _write_companion_json(cfg_dir, broken)
        with pytest.raises((KeyError, Exception)):
            CompanionConfig.from_json(p)


# CompanionConfig defaults

class TestCompanionConfigDefaults:
    def test_default_expression_fallback(self, tmp_path):
        cfg_dir = tmp_path / "configs"
        cfg_dir.mkdir()
        data = dict(MINIMAL_COMPANION)
        data.pop("expressions", None)
        p = _write_companion_json(cfg_dir, data)
        cfg = CompanionConfig.from_json(p)
        # Should fall back to ["default"]
        assert cfg.expressions == ["default"]

    def test_default_moods_fallback(self, tmp_path):
        cfg_dir = tmp_path / "configs"
        cfg_dir.mkdir()
        data = dict(MINIMAL_COMPANION)
        data.pop("moods", None)
        p = _write_companion_json(cfg_dir, data)
        cfg = CompanionConfig.from_json(p)
        # Should fall back to ["calm"]
        assert cfg.moods == ["calm"]
