"""
tests/test_companion_group_chat.py
Unit tests for Companion Group Chat:
- Group CRUD (create, list, get, delete)
- Member management (invite, kick)
- Message posting and mention extraction (@Lyra, @MisakaCipher, etc.)
- Multi-agent group scratchpad integration
- Pacing / settings updates
"""

import pytest
from core.companions.group_chat_engine import GroupChatEngine, extract_mentions
from core.companions.engine.scratchpad import CompanionScratchpad


def test_extract_mentions():
    members = [
        {"id": "marcel", "name": "Marcel", "is_user": True},
        {"id": "misakacipher", "name": "Misaka Cipher", "is_user": False},
        {"id": "lyra", "name": "Lyra", "is_user": False},
        {"id": "axiom", "name": "Axiom", "is_user": False},
    ]

    # Mention by exact ID
    m1 = extract_mentions("Hey @misakacipher and @lyra, what do you think?", members)
    assert "misakacipher" in m1
    assert "lyra" in m1
    assert "axiom" not in m1

    # Mention by first word of name
    m2 = extract_mentions("Check this out @Misaka!", members)
    assert "misakacipher" in m2

    # Mention user
    m3 = extract_mentions("What's your plan @Marcel?", members)
    assert "marcel" in m3

    # No mentions
    m4 = extract_mentions("No one is tagged here.", members)
    assert len(m4) == 0


def test_group_chat_lifecycle(tmp_path, monkeypatch):
    test_groups_dir = tmp_path / "groups"
    monkeypatch.setattr("core.companions.group_chat_engine.GROUPS_DIR", test_groups_dir)

    # 1. Create a group
    group = GroupChatEngine.create_group(
        title="Game Dev & AI Brainstorm",
        description="Brainstorming game mechanics and neural networks",
        companion_ids=["misakacipher"],
        avatar_symbol="🎮",
        accent_color="#8b5cf6",
        chat_speed_seconds=2.5,
    )
    assert group is not None
    gid = group["id"]
    assert gid.startswith("gc_")
    assert group["title"] == "Game Dev & AI Brainstorm"
    assert len(group["members"]) == 2  # Marcel + MisakaCipher

    # 2. List groups
    groups = GroupChatEngine.list_groups()
    assert len(groups) == 1
    assert groups[0]["id"] == gid

    # 3. Invite another companion
    updated = GroupChatEngine.invite_companion(gid, "lyra")
    assert any(m["id"] == "lyra" for m in updated["members"])
    assert len(updated["members"]) == 3
    # Check that system announcement was recorded
    last_msg = updated["history"][-1]
    assert "invited" in last_msg["content"].lower()
    assert "lyra" in last_msg["content"].lower()

    # 4. Post a user message with @mention
    user_msg, mentions = GroupChatEngine.post_user_message(
        gid,
        content="Hey @Lyra and @Misaka, can we design an adaptive combat AI?"
    )
    assert user_msg["author_id"] == "marcel"
    assert "lyra" in mentions
    assert "misakacipher" in mentions

    # 5. Group scratchpad test
    g_dir = test_groups_dir / gid
    sp = CompanionScratchpad(g_dir, "Group")
    res = sp.append_note("Design an adaptive boss behavior tree", section="Mechanics", author="lyra")
    assert res["status"] == "appended"
    entry = res["entry"]
    assert entry["author"]["id"] == "lyra"
    assert entry["text"] == "Design an adaptive boss behavior tree"

    # Reload group to verify scratchpad summary
    reloaded = GroupChatEngine.get_group(gid)
    assert reloaded["scratchpad_summary"]["entries_count"] >= 1

    # 6. Kick a companion
    after_kick = GroupChatEngine.kick_companion(gid, "lyra")
    assert not any(m["id"] == "lyra" for m in after_kick["members"])
    assert any(m["id"] == "misakacipher" for m in after_kick["members"])
    last_msg2 = after_kick["history"][-1]
    assert "removed" in last_msg2["content"].lower()

    # 7. Update pacing settings
    up_settings = GroupChatEngine.update_settings(gid, {"chat_speed_seconds": 5.0, "auto_reply_enabled": False})
    assert up_settings["settings"]["chat_speed_seconds"] == 5.0
    assert up_settings["settings"]["auto_reply_enabled"] is False

    # 8. Delete group
    deleted = GroupChatEngine.delete_group(gid)
    assert deleted is True
    assert GroupChatEngine.get_group(gid) is None


@pytest.mark.asyncio
async def test_group_scratchpad_tool_execution(tmp_path, monkeypatch):
    test_groups_dir = tmp_path / "groups"
    monkeypatch.setattr("core.companions.group_chat_engine.GROUPS_DIR", test_groups_dir)
    monkeypatch.setattr("core.utils.paths.COMPANION_GROUPS", test_groups_dir)

    group = GroupChatEngine.create_group(
        title="Myth Busters",
        companion_ids=["misakacipher"],
    )
    gid = group["id"]

    from core.companions.engine.tools import execute_tools_stream

    # Companion generates a scratchpad append WITHOUT specifying group_id in tool tag
    llm_output = 'I am adding this note! [tool:scratchpad cmd="append" text="Urban Legend: Ghost messages in the network"]'

    events = []
    async for ev in execute_tools_stream(
        llm_output,
        [],
        profile_id="full_local",
        companion_id="misakacipher",
        group_id=gid,
    ):
        events.append(ev)

    final = next(ev for ev in events if ev["type"] == "final_cleaned")
    assert "Urban Legend" not in final["content"]  # Tool tag stripped
    assert len(final["results"]) == 1

    # Verify note landed in group scratchpad
    sp = CompanionScratchpad(test_groups_dir / gid, "Group")
    data = sp.load()
    assert len(data.get("entries", [])) == 1
    assert "Urban Legend: Ghost messages in the network" in data["entries"][0]["text"]
    assert data["entries"][0]["author"]["id"] == "misakacipher"


@pytest.mark.asyncio
async def test_group_chat_media_tool_followup(tmp_path, monkeypatch):
    test_groups_dir = tmp_path / "groups"
    monkeypatch.setattr("core.companions.group_chat_engine.GROUPS_DIR", test_groups_dir)
    monkeypatch.setattr("core.utils.paths.COMPANION_GROUPS", test_groups_dir)

    group = GroupChatEngine.create_group(
        title="Media Room",
        companion_ids=["misakacipher"],
    )
    gid = group["id"]

    # Mock tool call in bridge manager
    from core.bridges import bridge_manager
    monkeypatch.setattr(
        bridge_manager,
        "call_module",
        lambda module_id, command, args, profile_id=None: (
            "Found video: Ghost in the Machine (https://www.youtube.com/watch?v=abc123xyz78)"
        )
    )

    call_count = 0
    class MockProviderResponse:
        def __init__(self, content):
            self.success = True
            self.content = content
            self.error = None

    class MockProviderManager:
        def call_with_failover(self, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MockProviderResponse(
                    "Searching YouTube now! [tool:bridge module=\"youtube_link\" cmd=\"search_videos\" query=\"ghost lore\"]"
                )
            else:
                return MockProviderResponse(
                    "Check out this creepy lore video: https://www.youtube.com/watch?v=abc123xyz78 It is super eerie!"
                )

    monkeypatch.setattr("core.companions.group_chat_engine.get_provider_manager", lambda: MockProviderManager())

    turn_res = await GroupChatEngine.generate_companion_turn(gid, "misakacipher")
    assert call_count == 2  # Turn 1 tool call + Turn 2 followup completion!
    msg = turn_res["message"]
    assert "https://www.youtube.com/watch?v=abc123xyz78" in msg["content"]
    assert "[tool:" not in msg["content"]


def test_group_chat_send_message_from_bridge(tmp_path, monkeypatch):
    test_groups_dir = tmp_path / "groups"
    monkeypatch.setattr("core.companions.group_chat_engine.GROUPS_DIR", test_groups_dir)
    monkeypatch.setattr("core.utils.paths.COMPANION_GROUPS", test_groups_dir)
    monkeypatch.setattr("core.bridges.group_chat_bridge.COMPANION_GROUPS", test_groups_dir)

    group = GroupChatEngine.create_group(
        title="Random Topics",
        companion_ids=["misakacipher", "ruikosaten"],
    )
    gid = group["id"]

    from core.bridges import group_chat_bridge
    res = group_chat_bridge.send_message({
        "group": "Random Topics",
        "companion_id": "misakacipher",
        "content": "Hey @Misaka, backend is feeling great today!",
    })
    assert "Posted message to group chat 'Random Topics'" in res

    loaded = GroupChatEngine.get_group(gid)
    posted = loaded["history"][-1]
    assert posted["author_id"] == "misakacipher"
    assert posted["author_role"] == "companion"
    assert posted["source"] == "1on1_bridge"
    assert "misakacipher" in posted["mentions"]
