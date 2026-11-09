"""
tests/test_dynamic_connectors_evolution.py
Unit tests for the Dynamic Realtime Connector Incubator and
the Non-Destructive Evolution Protocol:
- AST security validation (blocking dangerous code)
- Dynamic tool creation with self-testing
- Non-destructive evolution updates (backward compatibility verification)
- Automatic fallback on broken updates
- Execution telemetry tracking
- Native Suite promotion
"""

import pytest
from pathlib import Path
from core.bridges import dynamic_manager, dynamic_toolmaker


@pytest.fixture
def mock_dynamic_env(tmp_path, monkeypatch):
    test_dyn_dir = tmp_path / "dynamic_connectors"
    test_dyn_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("core.bridges.dynamic_manager.DYNAMIC_CONNECTORS", test_dyn_dir)
    return test_dyn_dir


def test_code_safety_validation():
    # 1. Clean valid Python code
    safe_code = """
def get_weather(args=None):
    import json
    return json.dumps({"temp": 21, "sky": "clear"})
"""
    ok, msg = dynamic_manager.validate_code_safety(safe_code)
    assert ok is True
    assert msg == "OK"

    # 2. Dangerous eval() call
    bad_eval = """
def run_math(args=None):
    return eval(args.get("expr", "1+1"))
"""
    ok, msg = dynamic_manager.validate_code_safety(bad_eval)
    assert ok is False
    assert "eval()" in msg

    # 3. Dangerous os.system() call
    bad_os = """
def delete_tmp(args=None):
    import os
    os.system("rmdir /s /q C:\\\\tmp")
    return "done"
"""
    ok, msg = dynamic_manager.validate_code_safety(bad_os)
    assert ok is False
    assert "Security Violation" in msg


def test_dynamic_tool_creation(mock_dynamic_env):
    code_v1 = """
def get_jam_info(args=None):
    theme = (args or {}).get("theme", "retro")
    return f"Active Game Jam Theme: {theme}. Countdown: 48h."
"""
    res = dynamic_manager.create_dynamic_tool(
        tool_id="jam_radar_test",
        name="Jam Radar Test",
        description="Tracks game jam countdowns",
        code=code_v1,
        author="misakacipher",
        test_cases=[
            {
                "command": "get_jam_info",
                "args": {"theme": "cyberpunk"},
                "expected_substring": "cyberpunk",
            }
        ]
    )
    assert res["success"] is True
    tool = res["tool"]
    assert tool["version"] == "1.0.0"
    assert tool["author"] == "misakacipher"
    assert len(tool["versions"]) == 1

    # Verify execution
    output = dynamic_manager.execute_dynamic_tool("jam_radar_test", "get_jam_info", {"theme": "horror"})
    assert "Active Game Jam Theme: horror" in output

    # Check telemetry
    meta = dynamic_manager.get_dynamic_tool("jam_radar_test")
    assert meta["telemetry"]["call_count"] == 1
    assert meta["telemetry"]["success_count"] == 1


def test_non_destructive_evolution_backward_compatibility(mock_dynamic_env):
    # Step 1: Misaka creates v1.0.0 with a contract that get_jam_info outputs "Theme:"
    code_v1 = """
def get_jam_info(args=None):
    theme = (args or {}).get("theme", "arcade")
    return f"Theme: {theme} | Status: Live"
"""
    create_res = dynamic_manager.create_dynamic_tool(
        tool_id="collab_tool",
        name="Collab Tool",
        description="Collaborative test tool",
        code=code_v1,
        author="misakacipher",
        test_cases=[
            {
                "command": "get_jam_info",
                "args": {"theme": "arcade"},
                "expected_substring": "Theme: arcade",
            }
        ]
    )
    assert create_res["success"] is True

    # Step 2: Ruiko updates the tool with improvements while preserving backward-compatibility
    code_v2_good = """
def get_jam_info(args=None):
    theme = (args or {}).get("theme", "arcade")
    prizes = (args or {}).get("prizes", "Trophies")
    return f"Theme: {theme} | Status: Live | Prizes: {prizes}"
"""
    up_res = dynamic_manager.propose_update(
        tool_id="collab_tool",
        new_code=code_v2_good,
        change_summary="Added prize pool tracking to jam info",
        author="ruiko_saten"
    )
    assert up_res["success"] is True
    assert up_res["status"] == "upgraded"
    assert up_res["version"] == "1.1.0"

    # Verify collaborators updated
    meta = dynamic_manager.get_dynamic_tool("collab_tool")
    assert "misakacipher" in meta["collaborators"]
    assert "ruiko_saten" in meta["collaborators"]
    assert len(meta["changelog"]) == 2

    # Step 3: Marcel proposes a breaking update that breaks Misaka's original test case!
    code_v3_broken = """
def get_jam_info(args=None):
    # Oops, changed output format completely, missing 'Theme: '
    return "Error: format deprecated"
"""
    break_res = dynamic_manager.propose_update(
        tool_id="collab_tool",
        new_code=code_v3_broken,
        change_summary="Refactored API",
        author="marcel"
    )
    # MUST BE NON-DESTRUCTIVELY PRESERVED AS A PROPOSAL WITHOUT BREAKING ACTIVE VERSION
    assert break_res["success"] is False
    assert break_res["status"] == "proposal_saved"
    assert "Backward compatibility check failed" in break_res["message"]

    # Active tool must STILL be v1.1.0 and functional!
    active_meta = dynamic_manager.get_dynamic_tool("collab_tool")
    assert active_meta["version"] == "1.1.0"
    out = dynamic_manager.execute_dynamic_tool("collab_tool", "get_jam_info", {"theme": "arcade"})
    assert "Theme: arcade" in out
    assert "Prizes:" in out


def test_dynamic_toolmaker_bridge(mock_dynamic_env):
    # Test tool creation through the dynamic_toolmaker bridge interface
    create_output = dynamic_toolmaker.create_tool({
        "id": "bridge_test_tool",
        "name": "Bridge Test Tool",
        "description": "Created via companion tool tag",
        "author": "misakacipher",
        "code": "def ping(args=None):\n    return 'pong'",
        "test_cmd": "ping",
        "expected_substring": "pong"
    })
    assert "Successfully created dynamic connector" in create_output

    # List tools
    listing = dynamic_toolmaker.list_tools()
    assert "bridge_test_tool" in listing
    assert "Bridge Test Tool" in listing

    # Inspect tool
    inspect_text = dynamic_toolmaker.inspect_tool({"tool": "bridge_test_tool"})
    assert "Active Source Code:" in inspect_text
    assert "def ping(args=None):" in inspect_text

    # Test tool run
    run_output = dynamic_toolmaker.test_tool({"tool": "bridge_test_tool", "cmd": "ping"})
    assert "pong" in run_output
