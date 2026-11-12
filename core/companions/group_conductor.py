"""
core/companions/group_conductor.py

Server-side pacing for companion group chats.

The old group chat was driven by the browser: one companion at a time, on a fixed
delay, in a chain. The conductor replaces that with behaviour closer to a real
group chat, and it runs in the server so a group keeps living when no tab is open.

How a message is handled
------------------------
1. Every companion decides on its own whether the message is worth answering
   (`reply_probability`). Being mentioned, being asked a question, the topic
   matching its interests and how talkative it is all raise the chance. Having
   just spoken, or the message being aimed at someone else, lower it.
2. Whoever decides to answer waits a human amount of time first: reading time,
   a reaction pause, and a stagger so two people do not post in the same second.
3. The companion then writes its message. It may still decide to stay silent
   ([pass]) or only react with an emoji. While it writes, others see "typing".
4. If somebody else posted while it was writing, it reconsiders once.
5. Each companion message lowers the room's energy, so companion-to-companion
   talk fades out on its own instead of stopping at a hard turn count.

On top of that an ambient loop lets a companion start a conversation after a long
silence, within active hours and a daily limit.

Everything that costs model calls is bounded: a streak limit on consecutive
companion messages, an hourly message limit, and a daily ambient limit.
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import random
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional, Set

from core.utils import get_logger, utcnow_iso
from core.companions import group_chat_engine as gce
from core.companions.registry import CompanionRegistry

logger = get_logger(__name__)


# ── Pace profiles ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Pace:
    delay_scale: float      # multiplies every waiting time
    chatter: float          # multiplies the chance of unprompted replies
    energy_decay: float     # room energy kept after each companion message
    max_streak: int         # companion messages in a row before everyone goes quiet
    ambient_gap_min: tuple  # (min, max) minutes of silence before someone may start a topic


PACES: Dict[str, Pace] = {
    "natural": Pace(1.0, 1.0, 0.55, 5, (45, 180)),
    "lively":  Pace(0.6, 1.5, 0.72, 8, (20, 90)),
    "quiet":   Pace(1.6, 0.6, 0.40, 3, (120, 360)),
}

DEFAULT_MAX_MESSAGES_PER_HOUR = 60
DEFAULT_MAX_AMBIENT_PER_DAY = 4
DEFAULT_ACTIVE_HOURS = (8, 23)

_STOPWORDS = {
    "that", "this", "with", "from", "have", "what", "your", "about", "would", "there", "their", "they",
    "them", "then", "than", "when", "will", "just", "like", "some", "into", "also", "very", "much",
    "more", "most", "been", "being", "does", "doing", "user", "users", "companion", "helping", "people",
    "things", "thing", "really", "always", "often", "sometimes", "which", "while", "where", "could",
    "should", "focusing", "approach", "approaches",
}
_ACK_RE = re.compile(r"^((ok(ay)?|k|thanks?|thx|ty|lol|lmao|haha+|nice|cool|yes|yeah|yep|no|nope|sure|great|good|wow|hm+|"
                     r"alright|got it|np)[.,!\s]*){1,3}$", re.IGNORECASE)


# ── Per-companion chat traits ────────────────────────────────────────────────

@dataclass(frozen=True)
class Traits:
    talkativeness: float    # 0..1, how readily it joins in unprompted
    typing_wpm: float       # words per minute while "typing"
    latency: float          # multiplier on reaction time (1.0 = average)
    keywords: frozenset = field(default_factory=frozenset)


def _unit(seed: str) -> float:
    """Stable pseudo-random number in [0, 1) from a string."""
    return int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF


def _keywords_from(raw: Dict[str, Any], description: str) -> frozenset:
    base = (raw.get("personality_defaults", {}) or {}).get("base_info", {}) or {}
    chunks: List[str] = [description or "", str(raw.get("personality", "")), str(base.get("role", "")),
                         str(base.get("core_identity", "")), str(base.get("personality", ""))]
    for key in ("likes", "interests", "expertise"):
        val = raw.get(key) or base.get(key) or []
        chunks.extend(val if isinstance(val, list) else [str(val)])
    words = re.findall(r"[a-zA-Z][a-zA-Z\-]{3,}", " ".join(map(str, chunks)).lower())
    return frozenset(w for w in words if w not in _STOPWORDS)


def traits_for(companion_id: str) -> Traits:
    """
    Chat rhythm of one companion.

    Values come from the optional "group_chat" block in the companion config
    ({"talkativeness": 0..1, "typing_wpm": number, "latency": number}). Anything
    not set there gets a stable value derived from the companion id, so each
    companion has its own rhythm without any configuration.
    """
    cfg = CompanionRegistry.get_companion(companion_id)
    raw = (cfg._raw_config if cfg else {}) or {}
    custom = raw.get("group_chat", {}) or {}

    def pick(key: str, lo: float, hi: float) -> float:
        try:
            return float(custom[key])
        except (KeyError, TypeError, ValueError):
            return lo + (hi - lo) * _unit(f"{companion_id}:{key}")

    return Traits(
        talkativeness=min(1.0, max(0.0, pick("talkativeness", 0.35, 0.85))),
        typing_wpm=max(15.0, pick("typing_wpm", 55.0, 95.0)),
        latency=max(0.2, pick("latency", 0.7, 1.5)),
        keywords=_keywords_from(raw, cfg.description if cfg else ""),
    )


# ── Pure decision functions (unit tested) ────────────────────────────────────

def is_question(text: str) -> bool:
    t = (text or "").strip().lower()
    return "?" in t or bool(re.match(r"^(who|what|why|how|when|where|which|can|could|should|does|do|is|are|any)\b", t))


def is_acknowledgement(text: str) -> bool:
    """Short messages like 'ok', 'thanks', 'lol' that nobody needs to answer."""
    return bool(_ACK_RE.match((text or "").strip()))


def topic_overlap(text: str, keywords: frozenset) -> float:
    """0..1: how much a message touches a companion's interests."""
    if not keywords or not text:
        return 0.0
    words = set(re.findall(r"[a-zA-Z][a-zA-Z\-]{3,}", text.lower()))
    hits = sum(1 for w in words if w in keywords or any(w.startswith(k[:5]) and len(k) >= 5 for k in keywords))
    return min(1.0, hits / 2.0)


def reply_probability(
    *,
    mentioned: bool,
    someone_else_mentioned: bool,
    author_is_user: bool,
    question: bool,
    acknowledgement: bool,
    overlap: float,
    talkativeness: float,
    energy: float,
    own_recent_messages: int,
    n_companions: int,
    chatter: float = 1.0,
) -> float:
    """Chance (0..1) that one companion answers one message."""
    if mentioned:
        # The user always gets an answer; a companion's ping can be left hanging when the room is winding down.
        return 1.0 if author_is_user else min(1.0, 0.45 + energy)

    n = max(1, n_companions)
    if author_is_user:
        # Aim for a little over one unprompted answer per user message, however large the group.
        p = min(0.9, 1.25 / n) * (0.6 + 0.8 * talkativeness)
        p += 0.25 if question else 0.0
        p += 0.30 * overlap
        if acknowledgement:
            p *= 0.25
    else:
        p = 0.5 * energy * chatter * (0.5 + talkativeness)
        p += 0.20 * overlap * energy
        p += 0.10 * energy if question else 0.0
        if acknowledgement:
            p *= 0.2

    p -= 0.18 * own_recent_messages
    if someone_else_mentioned:
        p *= 0.15
    return min(0.95, max(0.0, p))


def reading_seconds(text: str) -> float:
    """Time to read a message before reacting."""
    return min(8.0, 0.8 + len(text or "") / 45.0)


def typing_seconds(text: str, wpm: float) -> float:
    """Time a person would need to type a message."""
    words = max(1.0, len(text or "") / 5.0)
    return min(14.0, max(1.2, words / max(15.0, wpm) * 60.0))


def reply_delay(*, text: str, traits: Traits, pace: Pace, rank: int, mentioned: bool,
                rng: random.Random) -> float:
    """Seconds between a message arriving and a companion starting to type."""
    delay = reading_seconds(text) + rng.uniform(1.0, 4.0) * traits.latency
    delay += rank * rng.uniform(2.5, 6.0)          # later responders hang back
    if mentioned:
        delay *= 0.7
    return max(0.8, delay * pace.delay_scale)


def choose_responders(
    message: Dict[str, Any],
    companions: List[Dict[str, Any]],
    *,
    traits: Dict[str, Traits],
    energy: float,
    recent_authors: List[str],
    pace: Pace,
    rng: random.Random,
) -> List[Dict[str, Any]]:
    """
    Decide who answers `message`. Returns [{"id", "reason", "p", "mentioned"}] ordered
    by who will speak first. Pure apart from the injected random source.
    """
    author = message.get("author_id")
    author_is_user = message.get("author_role") == "user"
    text = message.get("content", "")
    mentions = [m for m in (message.get("mentions") or []) if m != author]
    others = [c for c in companions if c["id"] != author]
    if not others:
        return []

    question, ack = is_question(text), is_acknowledgement(text)
    scored = []
    for c in others:
        t = traits[c["id"]]
        mentioned = c["id"] in mentions
        p = reply_probability(
            mentioned=mentioned,
            someone_else_mentioned=bool(mentions) and not mentioned,
            author_is_user=author_is_user,
            question=question,
            acknowledgement=ack,
            overlap=topic_overlap(text, t.keywords),
            talkativeness=t.talkativeness,
            energy=energy,
            own_recent_messages=recent_authors[-3:].count(c["id"]),
            n_companions=len(others),
            chatter=pace.chatter,
        )
        scored.append({"id": c["id"], "p": p, "mentioned": mentioned,
                       "reason": "mention" if mentioned else "conversation"})

    chosen = [s for s in scored if rng.random() < s["p"]]

    # A message from the user to the room should not be met with silence.
    if author_is_user and not chosen and not ack:
        chosen = [max(scored, key=lambda s: s["p"])]

    # Mentioned companions first, then the most interested.
    chosen.sort(key=lambda s: (not s["mentioned"], -s["p"]))
    return chosen[:3]


# ── Runtime ──────────────────────────────────────────────────────────────────

@dataclass
class Room:
    group_id: str
    energy: float = 0.0
    streak: int = 0                               # companion messages since the user last spoke
    seq: int = 0                                  # bumps on every posted message
    recent_authors: List[str] = field(default_factory=list)
    pending: Dict[str, asyncio.Task] = field(default_factory=dict)
    typing: Set[str] = field(default_factory=set)
    subscribers: Set[asyncio.Queue] = field(default_factory=set)
    sent_times: Deque[float] = field(default_factory=deque)
    last_activity: float = field(default_factory=time.time)
    ambient_due_after: float = 0.0                # seconds of silence before the next ambient attempt
    ambient_day: str = ""
    ambient_count: int = 0


GenerateFn = Callable[..., Awaitable[Dict[str, Any]]]


class GroupConductor:
    def __init__(
        self,
        *,
        generate: Optional[GenerateFn] = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: Optional[random.Random] = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._generate = generate or gce.GroupChatEngine.generate_companion_turn
        self._sleep = sleep
        self._rng = rng or random.Random()
        self._clock = clock
        self._rooms: Dict[str, Room] = {}
        self._ambient_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # -- rooms and subscriptions

    def room(self, group_id: str) -> Room:
        room = self._rooms.get(group_id)
        if room is None:
            room = Room(group_id=group_id, last_activity=self._clock())
            try:
                hist = gce._load_history(group_id)
                room.recent_authors = [m.get("author_id", "") for m in hist[-6:] if m.get("author_role") != "system"]
                # last_activity deliberately starts at "now", not at the last stored message: after a
                # restart a full silence window must pass before anyone starts a topic on their own.
            except Exception:
                pass
            self._rooms[group_id] = room
        return room

    def subscribe(self, group_id: str) -> asyncio.Queue:
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        room = self.room(group_id)
        room.subscribers.add(q)
        for cid in room.typing:
            q.put_nowait({"type": "typing", "companion_id": cid, "active": True, "name": self._name(cid)})
        return q

    def unsubscribe(self, group_id: str, q: asyncio.Queue) -> None:
        self.room(group_id).subscribers.discard(q)

    def _emit(self, room: Room, event: Dict[str, Any]) -> None:
        for q in list(room.subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                room.subscribers.discard(q)

    @staticmethod
    def _name(companion_id: str) -> str:
        cfg = CompanionRegistry.get_companion(companion_id)
        return cfg.name if cfg else companion_id.capitalize()

    def _set_typing(self, room: Room, cid: str, active: bool) -> None:
        if active == (cid in room.typing):
            return
        (room.typing.add if active else room.typing.discard)(cid)
        self._emit(room, {"type": "typing", "companion_id": cid, "active": active, "name": self._name(cid)})

    def status(self, group_id: str) -> Dict[str, Any]:
        room = self.room(group_id)
        return {"energy": round(room.energy, 3), "streak": room.streak, "typing": sorted(room.typing),
                "pending": sorted(room.pending), "messages_last_hour": len(room.sent_times),
                "ambient_today": room.ambient_count}

    # -- settings helpers

    @staticmethod
    def _settings(group_id: str) -> Dict[str, Any]:
        meta = gce._load_meta(group_id) or {}
        return meta.get("settings", {}) or {}

    def _pace(self, settings: Dict[str, Any]) -> Optional[Pace]:
        """Pace profile, or None when the conductor must stay out (manual mode or paused)."""
        if settings.get("paused"):
            return None
        return PACES.get(gce.effective_pace(settings))

    def _within_budget(self, room: Room, settings: Dict[str, Any]) -> bool:
        now = self._clock()
        while room.sent_times and now - room.sent_times[0] > 3600:
            room.sent_times.popleft()
        return len(room.sent_times) < int(settings.get("max_messages_per_hour", DEFAULT_MAX_MESSAGES_PER_HOUR))

    # -- entry points

    def on_message(self, group_id: str, message: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Tell the conductor a message was posted (by the user or a companion).
        Broadcasts it and schedules whoever decides to answer. Returns the chosen responders.
        """
        room = self.room(group_id)
        room.seq += 1
        room.last_activity = self._clock()
        room.ambient_due_after = 0.0
        author = message.get("author_id", "")
        if message.get("author_role") != "system":
            room.recent_authors = (room.recent_authors + [author])[-6:]
        self._emit(room, {"type": "message", "message": message})

        settings = self._settings(group_id)
        pace = self._pace(settings)
        if message.get("author_role") == "user":
            room.energy, room.streak = 1.0, 0
        elif message.get("author_role") == "companion":
            room.streak += 1
            room.sent_times.append(self._clock())
            if pace:
                room.energy *= pace.energy_decay
        if pace is None or message.get("author_role") == "system":
            return []
        if room.streak >= pace.max_streak:
            return []
        if not self._within_budget(room, settings):
            if message.get("author_role") == "user":
                self._emit(room, {"type": "notice", "text": "Hourly message limit reached; companions are resting."})
            return []

        meta = gce._load_meta(group_id) or {}
        companions = [m for m in meta.get("members", []) if not m.get("is_user")]
        if not companions:
            return []
        traits = {c["id"]: traits_for(c["id"]) for c in companions}
        chosen = choose_responders(message, companions, traits=traits, energy=room.energy,
                                   recent_authors=room.recent_authors, pace=pace, rng=self._rng)
        for rank, pick in enumerate(chosen):
            cid = pick["id"]
            existing = room.pending.get(cid)
            if existing and not existing.done():
                continue      # already about to speak; it will read this message before writing
            delay = reply_delay(text=message.get("content", ""), traits=traits[cid], pace=pace, rank=rank,
                                mentioned=pick["mentioned"], rng=self._rng)
            self._schedule(room, cid, pick["reason"], delay, traits[cid], pace)
        return chosen

    def nudge(self, group_id: str, companion_id: Optional[str] = None) -> Optional[str]:
        """Ask one companion to say something now (the "Converse" button). Returns its id."""
        meta = gce._load_meta(group_id) or {}
        companions = [m for m in meta.get("members", []) if not m.get("is_user")]
        if not companions:
            return None
        room = self.room(group_id)
        room.energy, room.streak = max(room.energy, 0.8), 0
        if companion_id is None:
            last = room.recent_authors[-1] if room.recent_authors else None
            pool = [c for c in companions if c["id"] != last and c["id"] not in room.pending] or companions
            companion_id = self._rng.choice(pool)["id"]
        pace = PACES.get(gce.effective_pace(self._settings(group_id))) or PACES["natural"]
        self._schedule(room, companion_id, "nudge", 0.5, traits_for(companion_id), pace)
        return companion_id

    def cancel_pending(self, group_id: str) -> None:
        room = self.room(group_id)
        for task in list(room.pending.values()):
            task.cancel()
        room.pending.clear()
        for cid in list(room.typing):
            self._set_typing(room, cid, False)

    # -- one companion turn

    def _schedule(self, room: Room, cid: str, reason: str, delay: float, traits: Traits, pace: Pace) -> None:
        task = asyncio.ensure_future(self._turn(room, cid, reason, delay, traits, pace))
        room.pending[cid] = task
        task.add_done_callback(lambda t, r=room, c=cid: r.pending.pop(c, None) if r.pending.get(c) is t else None)

    async def _turn(self, room: Room, cid: str, reason: str, delay: float, traits: Traits, pace: Pace) -> None:
        gid = room.group_id
        try:
            await self._sleep(delay)
            if self._settings(gid).get("paused"):
                return

            result: Dict[str, Any] = {}
            for attempt in range(2):
                seq_at_start = room.seq
                started = self._clock()
                self._set_typing(room, cid, True)
                result = await self._generate(group_id=gid, companion_id=cid, trigger_reason=reason,
                                              natural=True, commit=False)
                # Someone else posted while this companion was writing: reconsider once.
                if (attempt == 0 and room.seq != seq_at_start and reason != "mention"
                        and result.get("action") == "message"):
                    reason = "conversation"
                    continue
                break

            action = result.get("action", "message")
            if action == "pass":
                return
            if action == "react":
                r = result.get("reaction") or {}
                if r.get("message_id"):
                    gce.add_reaction(gid, r["message_id"], r["emoji"], r["by"], r["by_name"])
                    self._emit(room, {"type": "reaction", **r})
                return

            messages = result.get("messages") or ([result["message"]] if result.get("message") else [])
            for i, msg in enumerate(messages):
                wait = typing_seconds(msg.get("content", ""), traits.typing_wpm) * pace.delay_scale
                if i == 0:
                    wait -= (self._clock() - started)      # the model's own thinking time already passed
                self._set_typing(room, cid, True)
                await self._sleep(max(0.6, wait))
                settings = self._settings(gid)
                if settings.get("paused") or not self._within_budget(room, settings):
                    return
                msg["timestamp"] = utcnow_iso()
                gce.append_history_message(gid, msg)
                self._set_typing(room, cid, False)
                self.on_message(gid, msg)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"[group-conductor] turn failed ({gid}/{cid}): {e}")
            self._emit(room, {"type": "notice", "text": f"{self._name(cid)} could not reply: {str(e)[:160]}"})
        finally:
            self._set_typing(room, cid, False)

    # -- ambient: someone starts a conversation after a long silence

    def ensure_started(self) -> None:
        """Start the ambient loop once. Safe to call from any request handler."""
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
        if self._ambient_task is None or self._ambient_task.done():
            try:
                self._ambient_task = asyncio.ensure_future(self._ambient_loop())
            except RuntimeError:
                pass

    def _handle_external_message(self, group_id: str, message: Dict[str, Any]) -> None:
        room = self.room(group_id)
        # Boost energy slightly so companions in a quiet room can react to an incoming 1-on-1 message
        room.energy = max(room.energy, 0.75)
        room.streak = 0
        self.on_message(group_id, message)

    def notify_external_message(self, group_id: str, message: Dict[str, Any]) -> None:
        """Thread-safe hook for posting a companion message from outside the group chat UI/loop."""
        loop = self._loop
        if loop and loop.is_running():
            loop.call_soon_threadsafe(self._handle_external_message, group_id, message)

    async def _ambient_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(30)
                for group_id in await asyncio.to_thread(_list_group_ids):
                    self.ambient_tick(group_id)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.debug(f"[group-conductor] ambient loop error: {e}")

    def ambient_tick(self, group_id: str, now: Optional[datetime.datetime] = None) -> Optional[str]:
        """Start an ambient turn in one group if it is due. Returns the companion id, or None."""
        settings = self._settings(group_id)
        pace = self._pace(settings)
        if pace is None or not settings.get("ambient_enabled", True):
            return None
        now = now or datetime.datetime.now()
        start = int(settings.get("active_hours_start", DEFAULT_ACTIVE_HOURS[0]))
        end = int(settings.get("active_hours_end", DEFAULT_ACTIVE_HOURS[1]))
        if not (start <= now.hour < end):
            return None

        room = self.room(group_id)
        if room.pending:
            return None
        today = now.strftime("%Y-%m-%d")
        if room.ambient_day != today:
            room.ambient_day, room.ambient_count = today, 0
        if room.ambient_count >= int(settings.get("max_ambient_per_day", DEFAULT_MAX_AMBIENT_PER_DAY)):
            return None
        if not self._within_budget(room, settings):
            return None
        if room.ambient_due_after <= 0:
            lo, hi = pace.ambient_gap_min
            room.ambient_due_after = self._rng.uniform(lo, hi) * 60
        if self._clock() - room.last_activity < room.ambient_due_after:
            return None

        meta = gce._load_meta(group_id) or {}
        companions = [m for m in meta.get("members", []) if not m.get("is_user")]
        if not companions:
            return None
        last = room.recent_authors[-1] if room.recent_authors else None
        pool = [c for c in companions if c["id"] != last] or companions
        weights = [0.2 + traits_for(c["id"]).talkativeness for c in pool]
        cid = self._rng.choices(pool, weights=weights, k=1)[0]["id"]

        room.ambient_count += 1
        room.ambient_due_after = 0.0
        room.last_activity = self._clock()      # one attempt per silence window, even if the companion passes
        room.energy, room.streak = max(room.energy, 0.6), 0
        self._schedule(room, cid, "ambient", self._rng.uniform(1, 20), traits_for(cid), pace)
        return cid


def _list_group_ids() -> List[str]:
    try:
        return [p.name for p in gce.GROUPS_DIR.iterdir() if p.is_dir() and (p / "meta.json").exists()]
    except FileNotFoundError:
        return []


_conductor: Optional[GroupConductor] = None


def get_conductor() -> GroupConductor:
    global _conductor
    if _conductor is None:
        _conductor = GroupConductor()
    return _conductor
