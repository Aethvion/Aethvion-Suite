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
