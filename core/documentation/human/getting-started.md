# Getting Started with Aethvion Suite

**Note: This documentation was updated on 2026-04-19 to reflect the current Aethvion Suite (v1.4) state.**

---

## Why Aethvion Suite?

Most AI tools give you a chat window and a subscription bill. Aethvion Suite is different:

- **It runs on your machine.** Your conversations never leave your hardware unless you decide to use a cloud provider.
- **It remembers you.** Companions build a memory profile over time — facts about your projects, preferences, and goals persist across sessions.
- **It works for you.** Autonomous agents can read files, write code, run commands, and report back — no copy-pasting required.
- **It's yours to configure.** Show only the tabs you use, activate only the bridges you need, create companions with personalities that fit you.

---

## Installation & Setup

### Prerequisites

- Python 3.10 or higher (3.12+ recommended)
- pip (Python package manager)
- At least one API key (Google AI recommended, others optional)

### Step 1: Clone the Repository

```bash
git clone https://github.com/Aethvion/Aethvion-Suite.git
cd Aethvion-Suite
```

### Step 2: Automated Setup (Windows)

Double-click `Start_Aethvion_Suite.bat` in the root directory.

This script will:
- Check your Python version (3.12+ recommended)
- Create a virtual environment (`.venv`)
- Install all necessary dependencies from `pyproject.toml`
- Configure your `.env` file (creates from `.env.example` if missing)
- Check for existing browser tabs before launching the dashboard

### Step 2 (Alternative): Manual Setup

```bash
# Create and activate venv
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate     # Windows

# Install dependencies
pip install -e ".[memory]"
```

### Step 3: Configure API Keys

Open the `.env` file in the root directory and add your API keys:

```env
# Required: At least one provider
GOOGLE_AI_API_KEY=your_google_api_key_here

# Optional: Additional providers for failover
OPENAI_API_KEY=your_openai_api_key_here
GROK_API_KEY=your_grok_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

Alternatively, enter keys in the dashboard under **Settings → API Providers** after launch.

### Step 4: Launch

```bash
python -m core.main
```

Open your browser to `http://localhost:8080`. The suite starts on the Home panel.

---

## Your First Session: Talking to a Companion

The first thing most users do is open a companion tab. Companions are the primary AI interface — they have personalities, they remember things about you, and they have access to tools and live bridge data.

### Open Misaka Cipher

Click **Misaka Cipher** in the sidebar (under the Companions folder, or just search for it by clicking the sidebar search).

Say hello. She'll introduce herself and start building context from your conversation.

**What companions can do in chat:**
- Answer questions and discuss any topic
- Remember facts you share with them (stored in memory profile)
- Tell you what's playing on Spotify, what the weather is, or system stats — if those bridges are active
- List and browse your workspaces
- Explain what tools and bridges are available

### Try the Other Companions

Each companion has a different personality suited to different tasks:

- **Axiom** — Ask him a logic puzzle, a research question, or to break down a complex topic step by step
- **Lyra** — Ask her to help with creative writing, come up with names, brainstorm ideas for a project

---

## Example Use Cases

### Use Case 1: Agent Task — Analyze a Folder

**Scenario:** You have a folder of Python files and want a summary of what they do.

**Steps:**
1. Open the **Agents** tab
2. Create a new workspace or select an existing folder
3. Enter prompt: `Read all .py files in this workspace and write a summary of what each file does and how they connect`
4. Click Run — watch the agent work in real time

**What happens:**
- Agent reads each file using `read_file`
- Summarizes each module
- Writes findings to a results file in the workspace
- Reports back with a structured summary

---

### Use Case 2: Persistent Memory — Save a Project Fact

**Scenario:** You're working on a long-running project and want the AI to always remember its architecture.

**Steps:**
1. Open the **Persistent Memory** tab
2. Click **Create Topic**
3. Topic: `Project_Alpha_Architecture`
4. Content: `The project uses FastAPI for the backend, React for the frontend, and PostgreSQL for storage. The main entry point is main.py.`
5. Click **Save**

Future agent tasks and companion conversations about this project will automatically receive this context.

---

### Use Case 3: Schedule — Daily Research Summary

**Scenario:** Get a brief AI summary of a topic every morning.

**Steps:**
1. Open the **Schedule** tab
2. Create a new task: `Daily AI News Brief`
3. Prompt: `Give me a 5-bullet summary of the most important AI developments from the last 24 hours`
4. Schedule: `Every day at 8:00 AM`
5. Enable notifications in **Settings → Notifications**

Every morning a notification appears with a link to the result. Click it to jump straight to the output.

---

### Use Case 4: Research Board — Deep Analysis

**Scenario:** You want multiple AI perspectives on a controversial topic.

**Steps:**
1. Open the **Research Board** tab
2. Enter your research question
3. The board assigns director personas to argue different positions
4. Watch structured AI debate produce analysis you wouldn't get from a single prompt

---

### Use Case 5: Bridges — Live Context in Chat

**Scenario:** You want your companion to know what you're listening to.

**Steps:**
1. Open **Settings** and find the **Bridges** section
2. Enable the **Spotify** bridge and enter your Spotify client credentials
3. Play a song in Spotify
4. Ask Misaka Cipher: "What am I listening to right now?"

She'll pull the live bridge data directly from the `{bridges_block}` injected into her prompt.

---

### Use Case 6: Local Audio Models — TTS and STT

**Scenario:** You want the AI to speak responses aloud.

**Steps:**
1. Open **Audio & Speech** tab
2. Install the Kokoro TTS model (via the Install button)
3. Load the model
4. Enter test text and click Generate
5. To use TTS in companion chat, enable it in **Settings → Companion Settings**

**Supported models:**
- **Kokoro** — fast, lightweight TTS
- **XTTS-v2** — higher quality TTS with voice cloning (upload a WAV file as your voice source)
- **Whisper** — speech-to-text transcription

---

## Configuration & Customization

### Sidebar Layout

The sidebar is fully customizable. Click the **layout icon** at the top of the sidebar to:
- Choose a preset layout (Professional, Creative, Researcher, Companion Hub, Full Suite, Custom)
- Drag tabs into folders
- Hide tabs you don't use

Your layout saves automatically as a named profile. Switch between profiles instantly.

### Provider Priority

Edit `config/providers.yaml` or use the **API Providers** tab:

```yaml
providers:
  google_ai:
    priority: 1  # Try first
  openai:
    priority: 2  # Fallback
  grok:
    priority: 3  # Last resort
```

### Model Selection Strategy

Edit `data/config/model_registry.json` or use the **Settings → Model Registry**:

```json
{
  "routing_strategy": {
    "simple_chat": "flash",
    "generation": "flash",
    "complex_architecture": "pro",
    "image_generation": "imagen"
  }
}
```

### Companion Configuration

Edit `core/companions/configs/{companion_id}.json` to change:
- System prompt template
- Personality defaults
- Tool access
- Context window size

---

## Best Practices

### 1. Let Companions Remember Things For You

Instead of re-explaining your project every session, just tell a companion once:
> "Remember that I'm working on a Python project called Project Alpha — it's a FastAPI backend with a React frontend."

The companion extracts this into its memory profile automatically.

### 2. Use Persistent Memory for Ground Truth

For facts that all agents and companions should know (project names, architecture decisions, personal preferences), save them as Persistent Memory Topics. They're injected as context automatically.

### 3. Match Task to Tool

| Task | Best tool |
|---|---|
| Quick question | Companion chat |
| Multi-file analysis | Agent (Agents tab) |
| Recurring tasks | Schedule |
| Deep research | Research Board |
| Model comparison | LLM Arena |
| Creative generation | Companion + Photo/3D/Audio |

### 4. Start with the Right Companion

- **Misaka Cipher** for general use, personal tasks, casual conversation
- **Axiom** for analysis, debugging, structured research
- **Lyra** for creative projects, writing, brainstorming

### 5. Monitor Usage

Check the **Usage** tab regularly. Smart routing (Flash for simple tasks, Pro for complex) keeps costs low, but it's good to see where tokens are going.

---

## Troubleshooting

### "Provider not available" Error

**Check:**
1. API key is correctly set in `.env` or Settings → API Providers
2. API key has sufficient credits/quota
3. Network connectivity to provider API

### Companion Doesn't Remember Past Conversations

**Check:**
1. The companion's memory file exists: `data/modes/companions/personas/{companion_id}/memory.json`
2. Memory extraction is enabled in companion config
3. You used `<memory>` tags or told the companion something it would store

### Bridge Not Showing Data

**Check:**
1. Bridge is enabled in Settings → Bridges
2. Required credentials are entered (Spotify needs client ID + secret)
3. The bridge service is running (e.g., Spotify app must be open for the Spotify bridge)

### Agent Gets Stuck in a Loop

**Check:**
1. Max iterations is 20 — the agent will stop automatically
2. Review the step log in the Agents tab for the last action taken
3. Rephrase the task with clearer exit criteria: "When you have written the summary file, use the done action."

### High API Costs

**Optimization steps:**
1. Check the **Usage** tab for model breakdown
2. Ensure simple tasks use Flash, not Pro
3. Install local GGUF models in `localmodels/gguf/` for bulk file reading tasks
4. Review the routing strategy in Settings → Model Registry

---

## What's In The Suite — Quick Reference

| Category | Features |
|---|---|
| **Companions** | Misaka Cipher, Axiom, Lyra, Companion Creator |
| **Agents** | Agent Workspaces, Agent Corp, Schedule |
| **Research** | Research Board, Advanced AI Conversations, LLM Arena, AI Conversations, Explained |
| **Creative** | Photo Studio, Image Models, Audio, Audio & Speech (TTS/STT), 3D Workspace, 3D Models |
| **Games** | Checkers, Are You Smarter Than AI?, Sudoku, Blackjack, Word Search, Logic Quest |
| **Memory** | Companion Memory, Persistent Memory, Episodic Memory |
| **Storage** | Output, Gallery, Camera, Uploads |
| **Model Hub** | Text & Chat Models, Image Models, Audio & Speech, 3D Models, API Providers |
| **System** | Logs, Documentation, Usage Analytics, Status, Port Manager |

---

## Current State (v1.4)

- ✅ Companion system (Misaka Cipher, Axiom, Lyra) with persistent memory
- ✅ Bridges system (6 active bridges with live context injection)
- ✅ AetherCore AI gateway with failover and Intelligence Firewall
- ✅ Agent Workspaces with real-time SSE streaming
- ✅ Agent Corp for multi-agent coordination
- ✅ Research Board (multi-director AI debate)
- ✅ Schedule & Notifications (cron-based with deep-link navigation)
- ✅ Local Audio Models (Kokoro, XTTS-v2, Whisper)
- ✅ 35+ configurable sidebar tabs with layout profiles
- ✅ LLM Arena with leaderboard
- ✅ Advanced AI Conversations (human participant, pause/inject, shareable links)
- ✅ Code IDE with streaming execution
- ✅ Finance dashboard with AI market analysis
- ✅ Persistent Memory knowledge hub
- ✅ Companion Creator for custom companions

**Near-term roadmap:**
- Ollama integration for local model management UI
- Advanced multi-agent coordination reliability
- Voice call mode (real-time audio in companion chat)
- Suite Profiles (Work / Creative / Companion modes)

---

**Ready to start?** Launch the suite and open your first companion tab.

```bash
python -m core.main
```

**Last Updated:** 2026-04-19

---

**Next Reading:**
- [System Overview](./readme-overview.md) - Deeper dive into architecture
- [AI Documentation](/core/documentation/ai/) - Technical specifications for advanced users
