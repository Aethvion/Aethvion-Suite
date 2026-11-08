"""
tests/test_companion_timer_flow.py
Unit tests for Companion Proactive Timers, Flow State & Vibe Manager,
and Natural 1-on-1 Conversational Restraint.
"""

import time
import pytest
from core.bridges import companion_timer_bridge, flow_state_bridge, bridge_manager
from core.companions.registry import CompanionRegistry
from core.companions.companion_engine import CompanionEngine


def test_companion_timer_lifecycle(tmp_path, monkeypatch):
    test_file = tmp_path / "companion_timers.json"
    monkeypatch.setattr(companion_timer_bridge, "TIMERS_FILE", test_file)

    # 1. Set a timer with 0.001 min (~0.06s) for rapid expiration testing
    res = companion_timer_bridge.set_timer({
        "companion_id": "misakacipher",
        "minutes": 0.001,
        "reason": "Shader compilation check",
        "context": "Ask Marcel if the shader compilation completed without errors."
    })
    assert "Timer scheduled" in res
    assert "misakacipher" in res
    assert "Shader compilation check" in res

    # 2. List timers
    listed = companion_timer_bridge.list_timers({"companion_id": "misakacipher"})
    assert "Shader compilation check" in listed
    assert "tm_" in listed

    # Extract ID
    import re
    m = re.search(r"#(tm_[a-f0-9]+)", res)
    assert m is not None
    timer_id = m.group(1)

    # 3. Test due timer check (sleep a tiny bit to ensure due_ts passes)
    time.sleep(0.1)
    due = companion_timer_bridge.get_due_timers("misakacipher")
    assert len(due) >= 1
    assert any(t["id"] == timer_id for t in due)

    # 4. Pop due timers
    popped = companion_timer_bridge.pop_due_companion_timers("misakacipher")
    assert any(t["id"] == timer_id for t in popped)

    # Verify status transitioned to processing
    timers = companion_timer_bridge._load_timers()
    item = next(t for t in timers if t["id"] == timer_id)
    assert item["status"] == "processing"

    # 5. Mark completed
    companion_timer_bridge.mark_timer_completed(timer_id, "Shader compiled cleanly!")
    timers = companion_timer_bridge._load_timers()
    item = next(t for t in timers if t["id"] == timer_id)
    assert item["status"] == "completed"
    assert item["response"] == "Shader compiled cleanly!"

    # 6. Cancellation test
    res2 = companion_timer_bridge.set_timer({
        "companion_id": "misakacipher",
        "minutes": 10.0,
        "reason": "Test cancel",
        "context": "Context to cancel"
    })
    m2 = re.search(r"#(tm_[a-f0-9]+)", res2)
    t2_id = m2.group(1)
    cancel_res = companion_timer_bridge.cancel_timer({"id": t2_id})
    assert "Cancelled companion follow-up timer" in cancel_res


def test_companion_timer_duration_parsing():
    parse = companion_timer_bridge.parse_duration_minutes
    assert parse(5) == 5.0
    assert parse("10") == 10.0
    assert parse("15m") == 15.0
    assert parse("20 mins") == 20.0
    assert parse("1.5h") == 90.0
    assert parse("in 5 minutes") == 5.0
    assert parse("30s") == 0.5


def test_flow_state_categorization():
    cat_name, cat_id = flow_state_bridge._categorize_process("Code.exe", "main.py - Aethvion - Visual Studio Code")
    assert cat_id == "coding"
    assert "Coding" in cat_name

    cat_name, cat_id = flow_state_bridge._categorize_process("Unity.exe", "Unity - MainScene - PC")
    assert cat_id == "game_dev"
    assert "Unity" in cat_name

    cat_name, cat_id = flow_state_bridge._categorize_process("blender.exe", "character_model.blend - Blender")
    assert cat_id == "3d_art"
    assert "Blender" in cat_name

    cat_name, cat_id = flow_state_bridge._categorize_process("chrome.exe", "Google Search")
    assert cat_id == "browsing"


def test_flow_state_summary_and_guidance(tmp_path, monkeypatch):
    test_file = tmp_path / "flow_state.json"
    monkeypatch.setattr(flow_state_bridge, "FLOW_STATE_FILE", test_file)

    summary = flow_state_bridge.get_flow_state()
    assert "Flow State:" in summary
    assert "Continuous Session:" in summary
    assert "Music Vibe:" in summary
    assert "Vibe Guidance:" in summary


def test_bridge_manager_companion_timer_and_slash():
    # Direct tool call via bridge_manager
    res = bridge_manager.call_module("companion_timer", "set_timer", {
        "companion_id": "misakacipher",
        "minutes": 15,
        "reason": "Break reminder",
        "context": "Remind Marcel to hydrate"
    })
    assert "Timer scheduled" in res

    # Slash command parsing
    parsed = bridge_manager.parse_and_execute_slash_commands("/timer 10m check light sync")
    assert parsed["triggered"] is True
    assert len(parsed["results"]) > 0
    assert "Timer scheduled" in parsed["results"][0]["output"]

    # Flow / vibe slash command
    parsed_vibe = bridge_manager.parse_and_execute_slash_commands("/vibe")
    assert parsed_vibe["triggered"] is True
    assert "Flow State:" in parsed_vibe["results"][0]["output"]


def test_natural_tone_prompt_rules():
    cfg = CompanionRegistry.get_companion("misakacipher")
    assert cfg is not None

    # Verify initiate_response prompt rules include strict name restraint
    # We can inspect the initiate rules string logic
    from core.companions.companion_engine import CompanionEngine
    # Check that companion engine source code enforces NO REPETITIVE NAME-DROPPING
    import inspect
    engine_src = inspect.getsource(CompanionEngine)
    assert "NO REPETITIVE GREETINGS OR NAME-DROPPING" in engine_src
    assert "NATURAL 1-ON-1 CONVERSATION (NO REPETITIVE NAME-DROPPING)" in engine_src
