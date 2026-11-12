"""Tests for natural group chat pacing (core/companions/group_conductor.py)."""

import asyncio
import datetime
import random

import pytest

from core.companions import group_chat_engine as gce
from core.companions import group_conductor as gc


# ── helpers ──────────────────────────────────────────────────────────────────

MEMBERS = [
    {"id": "marcel", "name": "Marcel", "is_user": True},
    {"id": "aa", "name": "Ada", "is_user": False},
    {"id": "bb", "name": "Bea", "is_user": False},
    {"id": "cc", "name": "Cy", "is_user": False},
]
COMPANIONS = [m for m in MEMBERS if not m["is_user"]]
TRAITS = {
    "aa": gc.Traits(0.8, 80, 1.0, frozenset({"shader", "rendering", "unity"})),
    "bb": gc.Traits(0.5, 60, 1.0, frozenset({"music", "melody"})),
    "cc": gc.Traits(0.3, 60, 1.0, frozenset({"story", "lore"})),
}


def user_msg(text, mentions=()):
    return {"id": "m1", "author_id": "marcel", "author_role": "user", "content": text, "mentions": list(mentions)}


def comp_msg(author, text, mentions=()):
    return {"id": "m2", "author_id": author, "author_role": "companion", "content": text, "mentions": list(mentions)}


@pytest.fixture
def group(tmp_path, monkeypatch):
    monkeypatch.setattr(gce, "GROUPS_DIR", tmp_path)
    gid = "gc_test"
    gce._save_meta(gid, {"id": gid, "title": "Test", "members": MEMBERS, "settings": {"pace": "natural"}})
    gce._save_history(gid, [])
    monkeypatch.setattr(gc, "traits_for", lambda cid: TRAITS[cid])
    return gid


async def no_sleep(_seconds):
    await asyncio.sleep(0)


def make_conductor(script, seed=1):
    """Conductor whose model is a scripted function: script(companion_id, reason) -> result dict."""
    calls = []

    async def fake_generate(*, group_id, companion_id, trigger_reason, natural, commit):
        calls.append((companion_id, trigger_reason))
        return script(companion_id, trigger_reason)

    return gc.GroupConductor(generate=fake_generate, sleep=no_sleep, rng=random.Random(seed)), calls


def reply(cid, text, mentions=()):
    msg = {"id": f"r_{cid}_{random.random()}", "author_id": cid, "author_name": cid, "author_role": "companion",
           "content": text, "mentions": list(mentions)}
    return {"action": "message", "message": msg, "messages": [msg]}


async def drain(conductor, gid, rounds=200):
    for _ in range(rounds):
        room = conductor.room(gid)
        if not room.pending:
            break
        await asyncio.sleep(0)


# ── pure decisions ───────────────────────────────────────────────────────────

def test_user_mention_always_answers():
    p = gc.reply_probability(mentioned=True, someone_else_mentioned=False, author_is_user=True, question=False,
                             acknowledgement=False, overlap=0, talkativeness=0.1, energy=0.0,
                             own_recent_messages=3, n_companions=5)
    assert p == 1.0


def test_message_aimed_at_someone_else_is_mostly_ignored():
    base = dict(mentioned=False, author_is_user=True, question=True, acknowledgement=False, overlap=0.5,
                talkativeness=0.7, energy=1.0, own_recent_messages=0, n_companions=3)
    assert gc.reply_probability(someone_else_mentioned=True, **base) < 0.2
    assert gc.reply_probability(someone_else_mentioned=False, **base) > 0.5


def test_companion_chatter_fades_with_energy():
    base = dict(mentioned=False, someone_else_mentioned=False, author_is_user=False, question=False,
                acknowledgement=False, overlap=0.0, talkativeness=0.6, own_recent_messages=0, n_companions=3)
    hot, cold = gc.reply_probability(energy=1.0, **base), gc.reply_probability(energy=0.1, **base)
    assert hot > 0.4 and cold < 0.1


def test_recent_speaker_holds_back_and_topic_pulls_in():
    base = dict(mentioned=False, someone_else_mentioned=False, author_is_user=True, question=False,
                acknowledgement=False, talkativeness=0.5, energy=1.0, n_companions=3)
    assert gc.reply_probability(overlap=0, own_recent_messages=2, **base) < \
           gc.reply_probability(overlap=0, own_recent_messages=0, **base)
    assert gc.reply_probability(overlap=1.0, own_recent_messages=0, **base) > \
           gc.reply_probability(overlap=0.0, own_recent_messages=0, **base)


def test_expected_responders_stays_near_one_for_any_group_size():
    for n in (2, 4, 8):
        p = gc.reply_probability(mentioned=False, someone_else_mentioned=False, author_is_user=True,
                                 question=False, acknowledgement=False, overlap=0, talkativeness=0.6,
                                 energy=1.0, own_recent_messages=0, n_companions=n)
        assert 0.6 <= p * n <= 1.6


def test_user_is_never_met_with_silence_but_ack_can_be():
    rng = random.Random(0)
    quiet = {k: gc.Traits(0.0, 60, 1.0) for k in TRAITS}
    for _ in range(50):
        picks = gc.choose_responders(user_msg("what do you all think about the new boss fight"), COMPANIONS,
                                     traits=quiet, energy=1.0, recent_authors=[], pace=gc.PACES["natural"], rng=rng)
        assert 1 <= len(picks) <= 3
    silent = sum(1 for _ in range(200) if not gc.choose_responders(
        user_msg("ok thanks"), COMPANIONS, traits=quiet, energy=1.0, recent_authors=[],
        pace=gc.PACES["natural"], rng=rng))
    assert silent > 100


def test_mentioned_companion_speaks_first_and_topic_expert_is_favoured():
    rng = random.Random(3)
    picks = gc.choose_responders(user_msg("@Cy can you check this?", mentions=["cc"]), COMPANIONS, traits=TRAITS,
                                 energy=1.0, recent_authors=[], pace=gc.PACES["natural"], rng=rng)
    assert picks[0]["id"] == "cc" and picks[0]["reason"] == "mention"

    counts = {"aa": 0, "bb": 0, "cc": 0}
    even = {k: gc.Traits(0.5, 60, 1.0, TRAITS[k].keywords) for k in TRAITS}
    for _ in range(400):
        for pick in gc.choose_responders(user_msg("the unity shader rendering looks off"), COMPANIONS, traits=even,
                                         energy=1.0, recent_authors=[], pace=gc.PACES["natural"], rng=rng):
            counts[pick["id"]] += 1
    assert counts["aa"] > counts["bb"] * 1.5 and counts["aa"] > counts["cc"] * 1.5


def test_delays_are_human_scaled():
    rng = random.Random(1)
    t = gc.Traits(0.5, 60, 1.0)
    first = [gc.reply_delay(text="hi", traits=t, pace=gc.PACES["natural"], rank=0, mentioned=False, rng=rng)
             for _ in range(100)]
    second = [gc.reply_delay(text="hi", traits=t, pace=gc.PACES["natural"], rank=1, mentioned=False, rng=rng)
              for _ in range(100)]
    assert 1.5 < sum(first) / 100 < 8
    assert sum(second) / 100 > sum(first) / 100 + 2
    assert gc.typing_seconds("x" * 20, 60) < gc.typing_seconds("x" * 300, 60) <= 14
    assert gc.reply_delay(text="hi", traits=t, pace=gc.PACES["quiet"], rank=0, mentioned=False,
                          rng=random.Random(5)) > \
           gc.reply_delay(text="hi", traits=t, pace=gc.PACES["lively"], rank=0, mentioned=False,
                          rng=random.Random(5))


def test_transcript_marks_silences():
    msgs = [
        {"author_name": "Marcel", "content": "hi", "timestamp": "2026-11-11T10:00:00Z"},
        {"author_name": "Ada", "content": "hey", "timestamp": "2026-11-11T10:00:20Z",
         "reactions": [{"emoji": "x", "by_name": "Bea"}]},
        {"author_name": "Marcel", "content": "back", "timestamp": "2026-11-11T13:00:20Z"},
    ]
    text = gce.format_transcript(msgs, now=datetime.datetime(2026, 11, 11, 14, 0, 20, tzinfo=datetime.timezone.utc))
    assert "3 hours later" in text and "reactions: x Bea" in text and "quiet for 1 hour ---" in text


def test_effective_pace_maps_old_groups():
    assert gce.effective_pace({"chat_speed_seconds": 0}) == "manual"
    assert gce.effective_pace({"chat_speed_seconds": 3.0}) == "natural"
    assert gce.effective_pace({"chat_speed_seconds": 3.0, "pace": "quiet"}) == "quiet"


# ── runtime ──────────────────────────────────────────────────────────────────

def test_mention_reply_is_saved_and_broadcast(group):
    async def run():
        conductor, calls = make_conductor(lambda cid, reason: reply(cid, "on it"))
        q = conductor.subscribe(group)
        conductor.on_message(group, user_msg("@Cy status?", mentions=["cc"]))
        await drain(conductor, group)
        events = []
        while not q.empty():
            events.append(q.get_nowait())
        return calls, events

    calls, events = asyncio.run(run())
    assert ("cc", "mention") in calls
    hist = gce._load_history(group)
    assert any(m["author_id"] == "cc" and m["content"] == "on it" for m in hist)
    kinds = [e["type"] for e in events]
    assert "typing" in kinds and kinds.count("message") >= 2
    typing = [e for e in events if e["type"] == "typing" and e["companion_id"] == "cc"]
    assert typing[0]["active"] is True and typing[-1]["active"] is False


def test_pass_and_react_post_no_message(group):
    async def run():
        def script(cid, reason):
            if cid == "aa":
                return {"action": "pass", "message": None}
            return {"action": "react", "message": None,
                    "reaction": {"message_id": "m1", "emoji": "+1", "by": cid, "by_name": cid}}
        conductor, calls = make_conductor(script)
        gce.append_history_message(group, user_msg("@Ada @Bea look", mentions=["aa", "bb"]))
        conductor.on_message(group, user_msg("@Ada @Bea look", mentions=["aa", "bb"]))
        await drain(conductor, group)
        return calls

    calls = asyncio.run(run())
    assert {c[0] for c in calls} == {"aa", "bb"}
    hist = gce._load_history(group)
    assert len(hist) == 1
    assert hist[0]["reactions"] == [{"emoji": "+1", "by": "bb", "by_name": "bb"}]


def test_companion_ping_pong_dies_out(group):
    """Two companions that always answer and always ping each other must still stop."""
    async def run():
        def script(cid, reason):
            other = "bb" if cid == "aa" else "aa"
            return reply(cid, f"@{other} and another thing", mentions=[other])
        conductor, calls = make_conductor(script, seed=7)
        conductor.on_message(group, user_msg("@Ada go", mentions=["aa"]))
        await drain(conductor, group, rounds=5000)
        return calls, conductor.room(group)

    calls, room = asyncio.run(run())
    posted = [m for m in gce._load_history(group) if m["author_role"] == "companion"]
    assert 1 <= len(posted) <= gc.PACES["natural"].max_streak
    assert not room.pending


def test_reconsiders_once_when_someone_else_posts_first(group):
    async def run():
        state = {"n": 0}
        holder = {}

        def script(cid, reason):
            state["n"] += 1
            if state["n"] == 1:      # someone else posts while this companion is "writing"
                holder["c"].room(group).seq += 1
            return reply(cid, f"draft {state['n']}")
        conductor, calls = make_conductor(script)
        holder["c"] = conductor
        room = conductor.room(group)
        conductor._schedule(room, "aa", "conversation", 0, TRAITS["aa"], gc.PACES["natural"])
        await drain(conductor, group)
        return calls

    calls = asyncio.run(run())
    assert len([c for c in calls if c[0] == "aa"]) == 2
    posted = [m["content"] for m in gce._load_history(group) if m["author_id"] == "aa"]
    assert posted == ["draft 2"]


def test_manual_and_paused_groups_get_no_automatic_replies(group):
    async def run(settings):
        gce.GroupChatEngine.update_settings(group, settings)
        conductor, calls = make_conductor(lambda cid, reason: reply(cid, "hi"))
        picks = conductor.on_message(group, user_msg("@Ada hello", mentions=["aa"]))
        await drain(conductor, group)
        return picks, calls

    assert asyncio.run(run({"pace": "manual"})) == ([], [])
    assert asyncio.run(run({"pace": "natural", "paused": True})) == ([], [])


def test_hourly_budget_stops_replies(group):
    async def run():
        gce.GroupChatEngine.update_settings(group, {"max_messages_per_hour": 2})
        conductor, calls = make_conductor(lambda cid, reason: reply(cid, "hi"))
        for _ in range(6):
            conductor.on_message(group, user_msg("@Ada again", mentions=["aa"]))
            await drain(conductor, group)
        return calls

    asyncio.run(run())
    posted = [m for m in gce._load_history(group) if m["author_role"] == "companion"]
    assert len(posted) == 2


def test_ambient_only_after_silence_within_hours_and_daily_limit(group):
    async def run():
        now = {"t": 1_000_000.0}
        calls = []

        async def fake_generate(*, group_id, companion_id, trigger_reason, natural, commit):
            calls.append(trigger_reason)
            return {"action": "pass", "message": None}

        conductor = gc.GroupConductor(generate=fake_generate, sleep=no_sleep, rng=random.Random(2),
                                      clock=lambda: now["t"])
        gce.GroupChatEngine.update_settings(group, {"max_ambient_per_day": 2})
        noon = datetime.datetime(2026, 11, 11, 12, 0)
        night = datetime.datetime(2026, 11, 11, 3, 0)

        assert conductor.ambient_tick(group, now=noon) is None            # not silent long enough yet
        now["t"] += 4 * 3600
        assert conductor.ambient_tick(group, now=night) is None           # outside active hours
        started = []
        for _ in range(5):
            now["t"] += 4 * 3600
            started.append(conductor.ambient_tick(group, now=noon))
            await drain(conductor, group)
        return started, calls

    started, calls = asyncio.run(run())
    assert [bool(s) for s in started] == [True, True, False, False, False]
    assert calls == ["ambient", "ambient"]
