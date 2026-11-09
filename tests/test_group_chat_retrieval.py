"""
tests/test_group_chat_retrieval.py
Unit tests for Group Chat Retrieval and Bridge Connector:
- Listing group chats
- Searching group messages and scratchpads
- Reading conversation history (by ID, title, and fuzzy name)
- Reading and appending to group scratchpads
- Companion ambient group chat awareness prompt generation
- Automatic context detection and pre-retrieval when user mentions group chat or members
"""

import pytest
from pathlib import Path
from core.bridges import group_chat_bridge
from core.companions.group_chat_engine import GroupChatEngine
from core.companions.engine.tools import _execute_one, execute_tools_stream


@pytest.fixture
def mock_groups_env(tmp_path, monkeypatch):
    test_groups_dir = tmp_path / "groups"
    test_groups_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("core.companions.group_chat_engine.GROUPS_DIR", test_groups_dir)
    monkeypatch.setattr("core.bridges.group_chat_bridge.COMPANION_GROUPS", test_groups_dir)

    # Create Group A: "Game Architecture"
    g1 = GroupChatEngine.create_group(
        title="Game Architecture & AI",
        description="Brainstorming adaptive boss combat and procedural dungeons",
        companion_ids=["misakacipher", "ruiko_saten"],
        avatar_symbol="🎮",
        accent_color="#8b5cf6"
    )
    gid1 = g1["id"]

    # Post messages in Group A
    GroupChatEngine.post_user_message(
        gid1,
        content="Hey @Ruiko and @Misaka, lets design an adaptive boss combat system with state machines."
    )
    # Add companion replies in history directly
    hist1 = GroupChatEngine.get_group(gid1)["history"]
    hist1.append({
        "id": "msg_test_1",
        "author_id": "ruiko_saten",
        "author_name": "Ruiko Saten",
        "author_role": "companion",
        "content": "I love the adaptive combat idea! What if the boss learns the player's attack timing?",
        "timestamp": "2026-11-09T01:00:00Z",
        "mentions": ["marcel"]
    })
    hist1.append({
        "id": "msg_test_2",
        "author_id": "misakacipher",
        "author_name": "Misaka Cipher",
        "author_role": "companion",
        "content": "Technically we could use a lightweight behavioral ledger to store pattern frequencies.",
        "timestamp": "2026-11-09T01:01:00Z",
        "mentions": ["ruiko_saten"]
    })
    from core.companions.group_chat_engine import _save_history
    _save_history(gid1, hist1)

    # Append note to group scratchpad
    from core.companions.engine.scratchpad import CompanionScratchpad
    sp1 = CompanionScratchpad(test_groups_dir / gid1, "Group")
    sp1.append_note("Adaptive Boss Behavior: Learn player dodge patterns", section="Mechanics", author="misakacipher")

    # Create Group B: "Creative Writing"
    g2 = GroupChatEngine.create_group(
        title="Creative Writing & Lore",
        description="Worldbuilding and urban legends",
        companion_ids=["ruiko_saten"],
        avatar_symbol="📚",
        accent_color="#f43f5e"
    )
    gid2 = g2["id"]
    GroupChatEngine.post_user_message(
        gid2,
        content="Let's write a story about a mysterious digital radio frequency."
    )

    return test_groups_dir, gid1, gid2


def test_list_groups(mock_groups_env):
    _, gid1, gid2 = mock_groups_env
    res = group_chat_bridge.list_groups({"companion_id": "misakacipher"})
    assert "Found 2 Companion Group Chat(s)" in res
    assert "Game Architecture & AI" in res
    assert "Creative Writing & Lore" in res
    assert "[You are a member]" in res


def test_search_messages_by_keyword(mock_groups_env):
    _, gid1, gid2 = mock_groups_env
    
    # Search for "adaptive"
    res1 = group_chat_bridge.search_messages({"query": "adaptive"})
    assert "Found" in res1
    assert "Ruiko Saten" in res1
    assert "adaptive boss combat" in res1

    # Search for "behavioral ledger"
    res2 = group_chat_bridge.search_messages({"query": "behavioral ledger"})
    assert "Misaka Cipher" in res2
    assert "behavioral ledger to store pattern frequencies" in res2

    # Search matches scratchpad entry
    res3 = group_chat_bridge.search_messages({"query": "dodge patterns"})
    assert "Shared Scratchpad Entry" in res3
    assert "dodge patterns" in res3


def test_read_history_fuzzy_matching(mock_groups_env):
    _, gid1, _ = mock_groups_env

    # 1. By exact ID
    res_id = group_chat_bridge.read_history({"group": gid1, "limit": 10})
    assert "Game Architecture & AI" in res_id
    assert "Ruiko Saten" in res_id

    # 2. By title substring
    res_title = group_chat_bridge.read_history({"group": "architecture", "limit": 10})
    assert "Game Architecture & AI" in res_title
    assert "lightweight behavioral ledger" in res_title

    # 3. By member name
    res_member = group_chat_bridge.read_history({"group": "with Misaka", "limit": 10})
    assert "Game Architecture & AI" in res_member


def test_read_and_append_scratchpad(mock_groups_env):
    _, gid1, _ = mock_groups_env

    # Read scratchpad
    sp_res = group_chat_bridge.read_scratchpad({"group": gid1})
    assert "Shared Brainstorming Scratchpad" in sp_res or "Adaptive Boss Behavior" in sp_res
    assert "dodge patterns" in sp_res

    # Append to scratchpad via bridge
    app_res = group_chat_bridge.append_scratchpad({
        "group": "architecture",
        "text": "Add telegraph audio cues before heavy boss strikes",
        "section": "Mechanics",
        "author": "marcel"
    })
    assert "Added note" in app_res

    # Read again
    re_read = group_chat_bridge.read_scratchpad({"group": "architecture", "section": "Mechanics"})
    assert "telegraph audio cues" in re_read


def test_awareness_block_and_detection(mock_groups_env):
    _, gid1, gid2 = mock_groups_env

    # Awareness block
    block = group_chat_bridge.get_group_chat_awareness_block(companion_id="misakacipher")
    assert "Companion Group Chats & Shared Multi-Agent Recall" in block
    assert "Game Architecture & AI" in block
    assert "[tool:bridge module=\"group_chat\" cmd=\"search_messages\"" in block

    # Auto context detection when user mentions "in the groupchat with Ruiko"
    user_prompt = "lets implement the feature we discussed in the groupchat with Ruiko"
    detected = group_chat_bridge.detect_and_retrieve_group_context(user_prompt, companion_id="misakacipher")
    assert detected is not None
    assert "Game Architecture & AI" in detected or "Creative Writing" in detected
    assert "Adaptive Boss Behavior" in detected or "Ruiko Saten" in detected

    # Auto context detection when user mentions the group title
    user_prompt2 = "can we continue what we did in Game Architecture?"
    detected2 = group_chat_bridge.detect_and_retrieve_group_context(user_prompt2, companion_id="misakacipher")
    assert detected2 is not None
    assert "Game Architecture & AI" in detected2


@pytest.mark.asyncio
async def test_tool_execution_stream_group_chat(mock_groups_env):
    _, gid1, _ = mock_groups_env

    # Simulated model response outputting group_chat tool call
    model_output = f'Let me check what we discussed. [tool:bridge module="group_chat" cmd="search_messages" query="adaptive"]'
    
    events = []
    async for ev in execute_tools_stream(model_output, [], profile_id="full_local", companion_id="misakacipher"):
        events.append(ev)

    final_ev = next(e for e in events if e["type"] == "final_cleaned")
    assert "Let me check what we discussed." in final_ev["content"]
    assert len(final_ev["results"]) == 1
    result_text = final_ev["results"][0]
    assert "Ruiko Saten" in result_text
    assert "adaptive" in result_text
