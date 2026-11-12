# Companions — Coworker Plan

**Started:** 2026-11-11
**Goal:** a companion should feel like working with another person who has their
own personality: a coworker, assistant, working partner or friend. Several of
them should be able to share a group chat that behaves like a real one and can
run all day.

This document covers four areas: the companion itself, its tools, group chat,
and a future animated avatar. Each area lists what the code does today, what is
wrong with it, and what to do. The change log at the end records what has been
built.

| Area | Status |
|------|--------|
| 3. Group chat pacing | **Built** (2026-11-11), see section 3 |
| 1. The companion itself | Planned |
| 2. Tools | Planned |
| 4. Animated avatar | Planned (future) |

---

## 1. The companion itself

### Today

- A companion is a JSON config (`core/companions/configs/*.json` plus user-made
  ones): identity, personality, speech style, quirks, likes, moods, expressions.
- `CompanionEngine.chat_response` builds one system prompt per message:
  personality, memory about the user, workspaces, and a long connector block.
- Mood and expression are tags the model writes into a reply
  (`<mood>`, `<expression>`). The expression swaps a portrait image.
- Proactive check-ins and self-set timers exist, but they are driven by the
  browser (`companion-presence.js`), so they stop when no tab is open.

### Problems

1. **Personality is outweighed by rules.** The personality is a few lines. The
   connector block (`engine/streaming.py`) adds roughly fifteen long always-on
   paragraphs about Spotify, YouTube, Twitch, scratchpads and so on. The model
   reads far more about tools than about who it is, which flattens every
   companion into the same helpful voice.
2. **Group chat uses less of the character.** The group prompt only uses
   identity, personality and speech style. Quirks, likes, dislikes and what the
   companion remembers about the user are left out, and there is nothing about
   how it relates to the other companions.
3. **No inner state.** Mood is decided per message and forgotten. A companion
   has no "what I am doing right now", no energy level, no ongoing interests.
4. **Nothing is learned in group chats.** Memory updates only happen in
   one-on-one chat.
5. **The user's name is hard-coded** as "Marcel" in the engine and prompts.

### Plan

| # | Change | Why |
|---|--------|-----|
| 1.1 | **Layered prompt.** Order: who you are → how you talk (with 3 to 5 example lines in the companion's own voice) → your current state → people you know → a short tool index. Tool rules move to section 2's on-demand list. | Voice examples steer style far better than adjectives. |
| 1.2 | **Persistent inner state** per companion: mood, energy, current activity, a few "things on my mind". Updated after conversations, decays over time, shown in the UI. | Continuity between messages and between chats. |
| 1.3 | **Relationships.** A short evolving note per companion about each other member (user and companions): shared jokes, disagreements, what they are working on together. | Makes group chats feel like people who know each other. |
| 1.4 | **Memory from group chats.** Run the existing memory synthesis on group history too, per companion. | Today a group decision is invisible to one-on-one chat except through search. |
| 1.5 | **Server-side presence.** Move check-ins and timers from the browser to the server loop that group chat now uses. Add simple status (available, busy, away) with a daily rhythm. | Works with no tab open; needed for 24/7. |
| 1.6 | **User profile.** One place for the user's name and details; remove the hard-coded name. | Correctness, and the Suite can be used by others. |
| 1.7 | **Chat rhythm in the creator.** Sliders for talkativeness, typing speed and reaction time. The backend already reads these (see 3). | Personality should include how someone chats, not only what they say. |

---

## 2. Tools

### Today

- Tools are "connectors" in `core/bridges/` (23 modules: screen, OCR, clipboard,
  git, processes, Spotify, YouTube, Twitch, web search, tasks, timers,
  scratchpad, visual memory, group chat search, dynamic toolmaker, and more).
- A companion calls one by writing a text tag:
  `[tool:bridge module="..." cmd="..." arg="..."]`. The engine finds tags with a
  parser, runs them, and asks the model again with the results.
- **Connector Profiles** decide which modules a companion may use
  (`bridge_manager.is_module_allowed`).

### Problems

1. **The prompt describes tools the companion may not have.** The module list is
   filtered by profile, but the long rule paragraphs above it are not.
2. **Every tool is described in every message**, which costs tokens and dilutes
   the personality (see 1).
3. **One permission level.** A profile allows a module or not. There is no
   difference between reading the clipboard and writing a file or creating a
   new tool that runs Python (`dynamic_toolmaker`).
4. **Group chat gets one tool round**; one-on-one gets three.
5. **No access to the new workflow engine.** Companions cannot run an Automate
   workflow, call a Model Hub endpoint, or use the Asset Library.
6. **No way to do long work.** A tool call must finish inside one reply.

### Plan

| # | Change | Why |
|---|--------|-----|
| 2.1 | **Build the tool section only from allowed modules**, including each module's own usage notes (move the hard-coded paragraphs into `registry.json` per module). | Fixes problem 1 and shrinks the prompt. |
| 2.2 | **Two-step tool list.** The prompt carries a one-line index per module; a companion asks for details (`[tool:help module="spotify"]`) only when it wants to use one. | Keeps personality dominant. |
| 2.3 | **Permission tiers** per profile: *read* (runs silently), *act* (runs, shown in chat), *ask first* (the companion asks in chat and waits for a yes). File writes, shell, and tool creation default to *ask first*. | Safe enough to leave running all day. |
| 2.4 | **Workflow connector.** `workflows.list`, `workflows.run`, `workflows.status`: a companion can start an Automate workflow and report the result. Plus `assets.search/save` and `models.invoke` on the Model Hub. | Ties companions to the workflow engine built in the Suite Evolution Plan: "Lyra, make me a low-poly barrel" runs the 3D pipeline. |
| 2.5 | **Background jobs.** A tool may return "started"; when it finishes, the result is posted into the chat it came from and the companion reacts. | Real coworker behaviour: "I'll look into it" followed by an answer ten minutes later. |
| 2.6 | **Delegation.** `team.ask companion="axiom" question="..."`: one companion asks another, in the group chat or privately. | Lets companions with different models and tool profiles combine. |
| 2.7 | **Tool activity in group chat.** A small status line ("Axiom is searching the web") instead of silence. | Makes waiting understandable. |
| 2.8 | **Native function calling** where the provider supports it, with the text tag as fallback. | Fewer malformed calls. Larger change; do after 2.1 to 2.3. |

Coworker tools worth adding after that, in order of value for game development:
project task board shared by the group, read access to a game project folder
with search, Unity console/log reading, screenshot review against visual memory
(exists), and daily stand-up summary.

---

## 3. Group chat — built

### What was wrong

The browser ran the conversation: after a user message it picked the mentioned
companion (or a random one), waited a fixed number of seconds, asked for a
reply, then followed @mentions in a chain up to four deep. Result: fixed rhythm,
one long paragraph each, strict A → B → C order, and nothing happened when the
tab was closed.

### How it works now

The server runs the conversation (`core/companions/group_conductor.py`). The
browser only displays a live event stream.

1. **Everyone decides for themselves.** For each new message every companion
   gets a chance of answering, from: being mentioned, the message being a
   question, the topic matching its interests, how talkative it is, whether it
   just spoke, and whether the message was aimed at someone else. The chances
   are scaled so a message to the room gets a little over one answer on average
   whatever the group size. Several companions can answer; often only one does.
2. **Human timing.** Before answering, a companion waits for reading time (by
   message length) plus a reaction pause, and later responders hang back a few
   seconds. A typing indicator is shown while it writes, and the message is held
   back for the time a person would need to type it.
3. **Silence is allowed.** The model may answer `[pass]` (nothing to add) or
   `[react:👍]` (an emoji reaction on the last message instead of a reply).
   A message from the user to the room always gets at least one companion
   considering it; "ok thanks" does not force a reply.
4. **Chat-style messages.** One to three sentences by default, optionally two
   bubbles.
5. **Re-reading.** If someone else posts while a companion is writing, it
   reconsiders once with the new message in view.
6. **Conversations fade out.** Each companion message lowers the room's energy,
   which lowers everyone's chance of adding to it. A user message restores it.
   There is no fixed turn order or count.
7. **Starting topics.** After a long silence (45 to 180 minutes at Natural pace)
   a companion may start something, within active hours. It is told to pass if
   it has nothing worth saying. The silence window restarts after a server
   restart, so nobody talks the moment the Suite starts.
8. **Time awareness.** The transcript given to the model marks long gaps
   ("3 hours later") and includes the current time.

### Settings (per group)

| Setting | Default | Meaning |
|---------|---------|---------|
| `pace` | `natural` | `natural`, `lively` (faster, more back-and-forth), `quiet` (slower, fewer replies), `manual` (old behaviour: nobody speaks unless mentioned or Converse is pressed) |
| `paused` | `false` | Stops all automatic replies. Stored on the server. |
| `ambient_enabled` | `true` | Companions may start topics after a silence ("Starts topics" checkbox). |
| `active_hours_start` / `_end` | 8 / 23 | Local hours in which topics may be started. |
| `max_ambient_per_day` | 4 | Topic-start attempts per day. |
| `max_messages_per_hour` | 60 | Hard limit on companion messages per hour. |

Existing groups map automatically: old "Step-by-Step" becomes `manual`,
everything else becomes `natural`.

Per companion, an optional `group_chat` block in its config sets
`talkativeness` (0 to 1), `typing_wpm` and `latency`. Without it each companion
gets its own stable values derived from its id.

### Cost limits

Every automatic reply is a model call, so three limits apply: at most 5
companion messages in a row without the user (8 lively, 3 quiet), the hourly
limit, and the daily topic limit. A `[pass]` still costs one call.

### API

- `GET  /api/companions/groups/{id}/events` — server-sent events: `message`,
  `typing`, `reaction`, `notice`
- `POST /api/companions/groups/{id}/nudge` — ask someone to speak now
- `GET  /api/companions/groups/{id}/status` — typing, energy, counters
- `PATCH /api/companions/groups/{id}/settings` — accepts the settings above

### Not done yet

- **Unread indicators and notifications** for messages that arrive while the
  group is not open.
- **Waiting while the user types.** Companions do not yet hold back when the
  user is mid-message.
- **Replies to a specific message** (quote/thread).
- **Rhythm sliders in the companion creator** (1.7).
- **A cheaper "should I speak" check** with a small model for large groups.
- **Presence** (busy/away) feeding into reply delays (1.5).

---

## 4. Animated avatar (future)

Goal: a companion that moves, talks and shows expressions on a rigged model,
in the style of a virtual streamer, instead of swapping portrait images.

### Pieces needed

| Piece | Options | Notes |
|-------|---------|-------|
| Rigged model | **VRM** (3D), **Live2D** (2D), Inochi2D (2D, open) | VRM models can be made without rigging skills in VRoid Studio. Live2D looks best for anime 2D but needs a rigged model and a licensed SDK. |
| Renderer | three.js + three-vrm, or PixiJS + a Live2D plugin | The dashboard already ships a three.js viewer, so VRM is the shorter path. |
| Expressions | Map the existing `<expression>`/`<mood>` tags to blendshapes | The tag system already exists; images become one "driver" among several. |
| Idle life | Blinking, breathing, small head and eye movement, looking at the cursor | This is what makes a model feel alive; it needs no AI. |
| Voice out | The Suite's TTS / voice library | Speak sentence by sentence as text streams, to keep delay low. |
| Lip sync | Mouth opening from audio loudness first; phoneme-based later | Loudness-based sync is simple and already convincing. |
| Voice in | Speech-to-text with voice activity detection | Allows interrupting the companion mid-sentence. |
| Stage | A dashboard panel, plus a transparent always-on-top window and a browser source for streaming | PyQt6 is already used by the launcher. |

### Suggested order

1. **Avatar driver interface.** One small interface (`setExpression`, `speak`,
   `lookAt`, `idle`) with the current portrait as its first implementation, so
   nothing else has to change when a model is added.
2. **VRM stage.** Load a `.vrm`, idle animation, expression mapping, loudness
   lip sync on existing TTS output.
3. **Voice conversation.** Speech in, streamed reply, sentence-chunked speech
   out, interruption.
4. **Autonomy.** The avatar reacts to what is on screen or in the group chat on
   its own, using the same pacing logic as section 3.
5. **Live2D driver** as a second renderer behind the same interface.

Open decision for when this starts: VRM first (recommended, shorter path) or
Live2D first (closer to the reference look).

---

## Suggested next steps

1. Use the new group chat for a few days and tune the numbers (reply chance,
   delays, topic frequency) from real use.
2. 2.1 + 1.1 together: the prompt rebuild. This is the biggest single
   improvement to how a companion sounds.
3. 1.5: move check-ins and timers to the server.
4. 2.3 + 2.4: permission tiers, then the workflow connector.
5. 1.2 to 1.4: inner state, relationships, group memory.

---

## Change log

### 2026-11-11 — Natural group chat pacing

**Added**
- `core/companions/group_conductor.py`: server-side pacing (reply decisions,
  human delays, typing, energy, topic starting, limits).
- `tests/test_group_conductor.py`: 17 tests, model replaced by a script.
- Routes: `/events`, `/nudge`, `/status`; new settings fields.

**Changed**
- `core/companions/group_chat_engine.py`: natural mode for
  `generate_companion_turn` (`natural`, `commit`), `[pass]` and `[react:]`,
  two-bubble replies, reactions stored on messages, time gaps in the
  transcript, history and settings writes protected by a lock (two companions
  posting at once could previously lose a message).
- `companion-creator.js`: the group view listens to the event stream; one
  shared message renderer; Pace selector replaces Speed; "Starts topics"
  toggle; Pause is stored on the server; typing indicator for several people;
  reaction pills.
- `companion-creator.css`: typing dots, reaction pills.

**Verified**
- 17 tests pass (reply chances, delays, ping-pong dies out, pass/react,
  re-reading, manual/paused, hourly limit, topic starting rules).
- In the running dashboard with a temporary group: pace selector and toggle
  render, a sent message appears once, the reply was scheduled after a
  5-second reading delay, settings save, and a failed model call shows a
  notice instead of hanging.

**Not verified**
- Real model replies. No AI provider was active in the test environment
  ("All providers failed"), so the wording, the `[pass]`/`[react]` behaviour of
  real models, and the overall feel have not been seen with a live model.
- Topic starting over real hours.
