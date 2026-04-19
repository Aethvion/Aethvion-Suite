# Feature Report — v1
### Aethvion Suite — Date: 2026-04-19

---

## 1. The Core Idea

Aethvion Suite's value proposition is three words: **local, personal, unified.**

- **Local** — your models, your data, your hardware. No subscription, no cloud dependency, no data leaving your machine.
- **Personal** — companions with real memory and personality, a dashboard that adapts to what you actually use, tools that know who you are.
- **Unified** — every AI workflow in one place, and those workflows can *talk to each other*. An agent can hand off to a companion. A research board session can feed into a scheduled task. Memory accumulates across everything.

Most AI apps pick one of these. Aethvion Suite aims to be all three. That is what makes it worth building and what makes it worth choosing over simpler alternatives.

This report is organized around that idea: improvements that deepen these three properties, and new features that no other app in the space currently offers.

---

## 2. What Aethvion Suite Has Right Now

Before adding, it's worth naming what already exists — because several features are already unusual:

| Feature | Why it's unique |
|---|---|
| Companions with persistent memory + mood | AI with evolving identity, not a stateless chatbot |
| Research Board | Multi-expert synthesis from a single prompt |
| Agent Corp | Multi-worker AI organizations with hierarchy |
| "Are You Smarter Than AI?" | Game-show format with a live AI judge |
| Bridges (screen, webcam, Spotify, system) | Companions can perceive and act on the user's environment |
| OpenAI-compatible external API | The suite itself becomes a backend for other apps |
| Overlay sidecar | Ask your companion about anything on screen |
| Full local stack | GGUF/Ollama models, local TTS/STT, local image gen |

The suite already does things no single product does. The goal of this report is to connect these pieces more tightly and add a layer of genuine personality and intelligence on top.

---

## 3. Improvements to Existing Features

These are enhancements to things that already work — higher return on investment than building new.

---

### 3.1 Companion Memory Visualizer

**Current state:** Companion memory is stored in `memory.json` and `base_info.json`. Users cannot see what their companion knows about them without opening files.

**Improvement:** A dedicated Memory panel per companion, accessible from the companion's settings. Shows memory as human-readable cards:

```
┌─────────────────────────────────────────┐
│ 🧠 What Misaka knows about you          │
├─────────────────────────────────────────┤
│ Name: [user's name]                     │
│ Works on: Python, backend systems       │
│ Preference: prefers concise answers     │
│ Noted: dislikes verbose introductions   │
│                                         │
│ Recent observations (last 20):          │
│ • "Asked about FastAPI 4 times this wk" │
│ • "Working on a local AI dashboard"     │
│ • "Prefers examples over explanations"  │
└─────────────────────────────────────────┘
```

Each card is **editable and deletable**. The user can also add facts manually. This makes the memory system visible and trustworthy instead of a black box.

**Why this draws users:** Memory is Aethvion's biggest differentiator from standard chatbots. Making it visible turns it from a background mechanic into a feature people *show to others*.

**Effort:** Medium — 1–2 days. The data already exists; it's a UI problem.

---

### 3.2 Companion Voice Call Mode

**Current state:** TTS and STT infrastructure exists and works. Companions respond in text.

**Improvement:** A "Call" button on any companion. Activates a phone-call-style interface: the user speaks, STT transcribes it, the companion responds with TTS. The UI switches to a minimal call view — companion avatar, waveform animation, hang-up button. No typing needed.

Design details:
- Push-to-talk or voice activity detection (VAD) toggle in settings
- The companion's current mood affects TTS voice speed/pitch slightly (Lyra slower and warmer, Axiom flat and measured)
- Call history is saved like regular chat history
- Bridging: if the companion has screen capture enabled, it can see what you're looking at during the call

**Why this draws users:** Talking to a persistent AI companion with memory, personality, and a voice is materially different from typing at a chatbot. It's the closest thing to having an AI colleague.

**Effort:** Medium-High — 3–5 days. TTS/STT are built; the call UI and VAD integration are the work.

---

### 3.3 Research Board: Live Debate Mode

**Current state:** Research Board generates N expert perspectives in a single pass and synthesizes them. It's one round.

**Improvement:** A "Live Debate" toggle. After the initial perspectives are generated, experts respond to each other — the optimist pushes back on the critic, the ethicist challenges the strategist. 2–3 rounds of back-and-forth before a final synthesis.

The board becomes a genuine deliberation rather than a parallel monologue. The output is richer and often surfaces contradictions the single-pass synthesis misses.

Additional improvement: **Save board sessions as templates**. "Startup strategy review," "technical architecture debate," "ethical risk assessment" — users build a library of boards they can re-run on new topics.

**Effort:** Low-Medium — debate rounds are just additional LLM calls on existing infrastructure. Templates are a JSON save/load.

---

### 3.4 Agent Corp: Pre-built Templates

**Current state:** Corp requires users to define every worker manually. The onboarding friction is high for new users.

**Improvement:** A **Corp Template Library** — a set of pre-designed organizations users can deploy in one click:

| Template | Workers |
|---|---|
| **Software Dev Team** | Architect, Senior Dev, QA Engineer, DevOps |
| **Content Studio** | Researcher, Writer, Editor, SEO Analyst |
| **Research Lab** | Principal Investigator, Analyst, Fact-Checker, Synthesizer |
| **Startup Advisors** | CEO Coach, CTO Coach, CMO Coach, CFO Coach |
| **Personal Productivity** | Task Planner, Accountability Partner, Summarizer |

Each template ships with sane defaults — worker personalities, task routing logic, output formats. Users can then edit or expand from there.

**Why this draws users:** Corp is one of Aethvion's most powerful and most underused features. Templates lower the barrier from "build a team from scratch" to "pick a team and start working."

**Effort:** Low — defining JSON templates and a selection UI.

---

### 3.5 Bridges: Calendar + Browser + Clipboard

**Current state:** Bridges cover the computer's hardware state (CPU, screen, webcam) and media (Spotify, system audio). There's no awareness of what the user is *doing*.

**Three new bridges:**

**Calendar Bridge** — reads the user's calendar (Google Calendar / iCal / `.ics` file). Companions can answer "what do I have today?", proactively mention upcoming deadlines, or factor schedule into suggestions. Entirely local — the calendar is read, not uploaded.

**Browser Bridge** — reads the current tab URL and page title from the user's browser (via a small local browser extension or browser's CDP interface). Companions can say "I see you're reading about X — want to talk about it?" No page content is read unless the user explicitly shares it via paste or the screen bridge.

**Clipboard Bridge** — if the user grants permission, the companion can read the current clipboard contents when asked. "What did I just copy?" becomes a valid question. Opt-in, explicitly triggered, never passive.

**Why this draws users:** These three bridges complete the picture of "AI that knows your context." Combined with the existing screen and system bridges, Misaka can have a realistic sense of what the user is doing right now.

**Effort:** Calendar bridge: Medium (read-only from local files or Google Calendar API). Browser bridge: Medium (requires a small companion browser extension). Clipboard bridge: Low (OS clipboard API is trivial).

---

### 3.6 Arena: Save and Compare Benchmarks

**Current state:** Arena runs blind model comparisons but results are not persisted or shareable.

**Improvement:**
- Save any arena session with a name and notes
- Build a personal leaderboard over time across all saved sessions
- Export results as a shareable JSON or formatted report
- Add a "temperature sweep" mode: run the same model at temp 0.2, 0.5, 0.8, 1.0 to find the optimal setting for a task type

**Effort:** Low — persistent storage and a leaderboard UI on top of the existing arena.

---

### 3.7 Scheduler: Event-Driven Triggers

**Current state:** Scheduler is purely time-based (cron).

**Improvement:** Add event triggers alongside cron:

| Trigger type | Example |
|---|---|
| File change | "Run summarization agent when new file added to `/projects/notes/`" |
| App launch | "Brief me when I open the suite for the first time today" |
| Idle detection | "If I haven't interacted in 2 hours, save a session summary" |
| Threshold | "Alert me if CPU stays above 90% for more than 5 minutes" |

This transforms scheduling from "set a cron job" into a lightweight automation layer. Combined with the workspace and bridge systems, users can build personal automations entirely in plain English.

**Effort:** Medium-High — requires a background event watcher service, but the task execution infrastructure already exists.

---

## 4. New Feature Concepts

These are features that don't exist yet and would draw users to Aethvion specifically.

---

### 4.1 Suite Profiles — Work / Create / Unwind

**The idea:** The same installation behaves completely differently depending on which profile is active. Profiles are not just themes — they change which features are visible, which companion is front and center, and which bridges are active.

**Three default profiles:**

**Work Profile**
- Visible: Agents, Corp, Research Board, Explained, Scheduler, Workspace tools
- Hidden: Games, 3D models, Audio studio
- Default companion: Axiom (focused, no-nonsense)
- Active bridges: System, Calendar, Browser, Clipboard
- Dashboard accent: cool blue

**Create Profile**
- Visible: Image gen, Audio studio, 3D models, Research Board, Companion chat
- Hidden: Agents, Corp, Scheduler, System management
- Default companion: Lyra (warm, imaginative)
- Active bridges: Spotify, Screen capture
- Dashboard accent: warm violet

**Unwind Profile**
- Visible: Games, Companion chat, "Are You Smarter Than AI?", Music (Spotify bridge)
- Hidden: Everything work-related
- Default companion: Misaka (playful mood)
- Active bridges: Spotify, Media sentinel
- Dashboard accent: soft indigo

Users can customize any profile and create new ones. Switching profiles is a single click from the header. The app doesn't delete features — it focuses them.

**Why this is unique:** No other AI app has the concept of a *context-aware mode* that changes the entire product surface. This directly addresses the "super app without bloat" goal. Every user sees exactly the app they need.

**Effort:** Medium — profile configs are JSON, visibility toggles are CSS + JS. The infrastructure for showing/hiding panels already exists.

---

### 4.2 Daily Brief — Morning Companion Session

**The idea:** Once per day (at a configurable time, or on first suite open), a companion delivers a personalized briefing. Not a dashboard of widgets — a *conversation* that starts the day.

What the brief includes (each section is optional, configured per user):

```
Good morning. Here's what I have for you.

📅 Today: Three tasks in your schedule. The 2pm deep work block
   you set last Tuesday.

🧠 From memory: You were working on the auth system yesterday.
   You mentioned being stuck on token refresh. Want to pick that
   back up?

📰 Research: You asked about WebAssembly three times this week.
   I put together a short brief if you want it.

🌤 Weather: 14°C, overcast. Rain expected around 3pm.

What would you like to start with?
```

The companion then stays in the brief panel for a short back-and-forth before the user opens their main workflow. The brief session is saved to memory — what the user chose to focus on, what they skipped.

**Why this is unique:** Every productivity app has a dashboard. None of them *talk to you*. The daily brief is the moment where Aethvion's persistent memory pays off — it's not generic information, it's *your* information delivered by someone who knows you.

**Effort:** Medium — the data sources (schedule, memory, weather bridge) all exist. It's a new companion prompt template + trigger logic + a clean brief UI.

---

### 4.3 Companion Relationship Timeline

**The idea:** A visual timeline showing how a companion's relationship with the user has evolved. Not a log — a *story*.

```
── March 2026 ─────────────────────────────────────
  First conversation. You were testing the suite.
  Misaka noted you were a developer.

── April 2026 ─────────────────────────────────────
  Synthesis: You've been building Aethvion for 3 weeks.
  Misaka has learned your preferences on code style.
  Mood trend: Mostly "focused" during your sessions.

  Key memory: "User prefers examples over explanations.
  Dislikes long preambles. Works best in evening sessions."
```

Shows:
- When the user started using the companion
- Key synthesis notes over time
- Mood/energy patterns across sessions
- "Milestones" (first 10 conversations, first memory update, etc.)

The companion can reflect on the timeline when asked: "Misaka, how long have we been working together?"

**Why this is unique:** It makes the relationship with the companion feel *real*. Other AI products reset every conversation. Aethvion is the opposite — it accumulates and reflects. This feature makes that visible.

**Effort:** Medium — the data already exists in `memory.json` synthesis notes and history. The timeline is a UI layer over existing data.

---

### 4.4 Conversation Recipes

**The idea:** User-defined shortcut workflows that trigger a specific sequence of AI actions from a short command.

Examples:
```
/standup     → Run a Research Board with "team standup" template on 
               [topic I type next]

/explain X   → Open Explained mode with X, set depth to "beginner",
               auto-start

/review      → Start Axiom in code review mode with current workspace
               files as context

/debate X    → Research Board with 4 experts and live debate mode on X
```

Recipes are defined in a simple UI — pick a name, pick the action (open panel, run agent, start companion with persona, etc.), set default parameters. No code required.

A Recipe can chain actions: "Send this to the Research Board, then have Lyra summarize the conclusions for me."

**Why this is unique:** Recipes turn the suite's existing features into a personal command language. Power users build their own workflows. New users get starter packs. It's keyboard-driven productivity on top of AI.

**Effort:** Medium-High — requires a recipe runner / action dispatcher, but most action primitives (open panel, start agent, trigger companion) already exist as JS functions.

---

### 4.5 Personal Knowledge Base

**The idea:** A structured, user-curated knowledge layer that lives alongside companion memory but is separate from it. Where memory is ephemeral and automatic, the Knowledge Base is intentional and permanent.

Think: a personal wiki that every companion can read.

**Structure:**
```
Knowledge Base
├── Projects
│   ├── Aethvion Suite — overview, decisions, status
│   └── Client Project X — context, contacts, constraints
├── People
│   ├── [Name] — relationship, notes, last contact
│   └── ...
├── Topics
│   ├── Machine Learning — notes, resources, open questions
│   └── Home Automation — setup, devices, configs
└── Reference
    ├── Passwords hint sheet
    └── Recurring meeting agendas
```

The companion doesn't just *remember* things passively — the user can *tell* it things deliberately. "Add to knowledge base: client X prefers async communication and doesn't like video calls."

Any companion can query the knowledge base when relevant. The Explained mode can link its explanations to existing KB entries.

**Why this is unique:** It turns Aethvion from a *reactive* AI tool into a *second brain*. The user isn't just chatting — they're building a private, AI-readable knowledge repository that gets smarter over time.

**Effort:** High — requires a new data model, KB editor UI, and query integration into the companion engine. But the storage and companion injection patterns already exist.

---

### 4.6 Multi-Companion Collaboration

**The idea:** Put two or more companions in the same conversation thread. They each respond in turn, from their own perspective, and the user moderates.

**Use cases:**
- **Creative + Critical**: Lyra generates an idea, Axiom critiques it. The user decides what to keep.
- **Brainstorm + Synthesize**: Misaka runs wild with ideas, Axiom condenses them into actionable steps.
- **Debate**: Present a controversial decision to Misaka and Axiom. Watch them disagree. Make a better-informed call.

The conversation panel shows each companion's message attributed and styled by their identity (different accent colors, icons). Each companion has access to the full conversation history so they can respond to each other.

**Why this is unique:** No other AI product lets you run multiple distinct personalities in one conversation. This is a natural evolution of the Research Board concept, but personal and interactive rather than formal and one-shot.

**Effort:** Medium — the companion engine handles one companion at a time. Multi-companion requires a session coordinator that routes turns and maintains a shared history. The individual companion response logic is unchanged.

---

### 4.7 Adaptive Dashboard

**The idea:** The suite home and app navigation automatically reorganize based on what the user actually uses. Features the user touches frequently float to the top. Features untouched for 30+ days get visually de-emphasized (smaller, greyed).

The user never deletes features — they fade. One click restores full visibility. Nothing is lost.

Additionally: the home panel shows a **"Your Aethvion"** section — a curated summary of the user's most-used tools, active companions, recent agents, and upcoming scheduled tasks. Completely personalized, generated from usage data.

**Why this is unique:** It solves the "super app bloat" problem without requiring the user to manually configure anything. The app *learns* to be minimal for each user naturally.

**Effort:** Low-Medium — requires usage tracking (which clicks/opens happen) and a sorting layer. The rest is CSS transitions.

---

### 4.8 Ambient Intelligence — Passive Surface

**The idea:** A small, always-visible panel (collapsible, dockable) that surfaces observations and suggestions Aethvion has made *without being asked*.

Examples of what it might show:

```
💡 You've asked about authentication 6 times this week.
   Want me to build a reference doc?

⚡ Your CPU has spiked above 90% three times today at 2pm.
   That's when your agent job runs. Want to reschedule it?

📖 You bookmarked 4 articles about WASM last month and haven't
   revisited them. Want a summary?

🎵 You usually listen to lo-fi when you code. Want me to start
   Spotify?
```

Observations are generated by a lightweight background process that monitors usage patterns, bridge data, and memory — not a constant LLM call. Patterns are detected locally. The LLM is only called to phrase the suggestion once a pattern exceeds a threshold.

**Why this is unique:** This is the closest thing to an AI that *notices things about you*. Not because you asked, but because it's paying attention. It's the "super app" thesis in its purest form — the app is working for you even when you're not using it.

**Effort:** High — requires a background pattern-detection service, a suggestion queue, and a careful design to avoid being annoying. The key design constraint: no more than 2 suggestions visible at once, and each can be dismissed permanently.

---

### 4.9 Companion "Focus Sessions"

**The idea:** A structured work mode where a companion actively facilitates a productive session. The user declares a goal. The companion helps them reach it.

**Flow:**
```
User opens Focus Session, sets goal: "Finish the auth module"
Duration: 90 minutes

Misaka: "Alright. 90 minutes on the auth module. 
         I'll check in at 45 minutes. 
         What do you need to get started?"

[User works, chat is available but calm]

[45 minutes in]
Misaka: "How's the auth module going? 
         You mentioned you were stuck on token refresh — 
         did you get past that?"

[Session ends]
Misaka: "90 minutes done. You worked on [files accessed in workspace].
         Want me to summarize what you accomplished?"
```

The companion uses the workspace bridge, screen capture (if enabled), and session memory to give genuinely contextual check-ins. The session is saved to the companion's memory and the history.

**Why this is unique:** Every focus app has a timer. Aethvion is the only one where a companion with memory of your past work checks in on your current session. The Pomodoro technique, but with a co-worker.

**Effort:** Medium — new session data model, a companion prompt template for facilitation mode, and a minimal focus UI. The underlying companion engine is unchanged.

---

## 5. The Modular Feature Philosophy

A central tension in a "super app" is: how do you keep adding features without the app feeling overwhelming to a user who only wants two of them?

The answer for Aethvion is **opt-in activation**. Every feature beyond the core companion chat and home panel is off by default. Users activate features they want. Activated features appear in navigation and settings. Dormant features are invisible.

**Proposed activation model:**

```
Core (always on):
  • Companion chat (Misaka)
  • Home panel
  • Settings
  • Local model support

Tier 1 — activate individually:
  • Research Board
  • Agents + Workspaces
  • Additional companions (Axiom, Lyra, Nova)
  • Bridges (each bridge is a separate toggle)
  • Daily Brief

Tier 2 — activate as bundles or individually:
  • Games Suite
  • Creative Tools (Image gen, 3D, Audio)
  • Power Tools (Corp, Arena, Explained, External API)
  • Automation (Scheduler, event triggers)

Tier 3 — experimental / opt-in:
  • Multi-companion collaboration
  • Ambient Intelligence panel
  • Companion Timeline
```

A user who wants a simple personal assistant activates nothing beyond core. A developer who wants a full AI workstation activates everything. The same codebase, radically different experiences.

This is what "customizable without bloat" means in practice.

---

## 6. Prioritized Roadmap

### Phase 1 — Deepen what makes Aethvion unique (4–6 weeks)

| Feature | Why first | Effort |
|---|---|---|
| Companion Memory Visualizer | Makes the biggest differentiator *visible* | Medium |
| Suite Profiles | Solves the bloat problem structurally | Medium |
| Daily Brief | Delivers on "AI that knows you" every day | Medium |
| Corp Templates | Unlocks a powerful existing feature for new users | Low |
| Research Board: Live Debate | Makes the best collaborative feature better | Low–Medium |

### Phase 2 — New unique experiences (6–10 weeks)

| Feature | Why second | Effort |
|---|---|---|
| Companion Voice Call Mode | Most visceral demonstration of companion depth | Medium–High |
| Conversation Recipes | Power users build their own Aethvion | Medium–High |
| Multi-Companion Collaboration | Extends companions into a unique format | Medium |
| Bridges: Calendar + Browser | Completes the context picture | Medium |
| Arena: Save & Compare | Builds a personal model benchmark library | Low |

### Phase 3 — The intelligence layer (10–16 weeks)

| Feature | Why third | Effort |
|---|---|---|
| Personal Knowledge Base | Second brain, feeds everything else | High |
| Adaptive Dashboard | The app learns to be minimal for each user | Medium |
| Focus Sessions | Companion-facilitated productivity | Medium |
| Companion Relationship Timeline | Makes the relationship feel real and earned | Medium |
| Ambient Intelligence Panel | The "it just knows" moment | High |
| Event-Driven Scheduler | Full local automation layer | Medium–High |
| Opt-in Feature Activation System | Required infrastructure for super app at scale | Medium |

---

## 7. What Would Make Someone Tell a Friend About Aethvion

The features most likely to generate word-of-mouth are the ones that produce a reaction no other AI app produces:

1. **"My AI remembered something I mentioned three weeks ago."** — Companion memory, especially with the Memory Visualizer making it visible.

2. **"I had a voice conversation with my AI and it felt like talking to someone who knows me."** — Voice Call Mode + persistent memory.

3. **"I told it what I was working on and it checked in on me during my session."** — Focus Sessions.

4. **"I put two AIs in the same chat and watched them disagree."** — Multi-Companion Collaboration.

5. **"It noticed a pattern in how I work and suggested a change."** — Ambient Intelligence.

6. **"The app literally reorganized itself to show me only what I use."** — Adaptive Dashboard.

These are the moments that make Aethvion a product people demonstrate to others. Every phase in the roadmap above is aimed at producing more of them.

---

*Report generated by Claude. Feature designs based on full audit of live codebase.*
