# Getting Started with Aethvion Suite

**Note: This documentation was updated on 2026-03-30 to reflect the current Aethvion Suite (v11) state.**

---

## Why Aethvion Suite? The Value Proposition

### The Problem with Traditional AI Systems

**Traditional Approach:**
```
User: "I need to analyze 1000 CSV files and generate insights"
AI: "Here's some sample code you can run..."
User: Copies code, debugs errors, manually runs on each file
Result: Hours of manual work, inconsistent quality
```

**AI Wrapper Limitation:**
```
User: Same request
AI Wrapper: Analyzes all 1000 files with GPT-4
Result: $200 in API costs, but automatic execution
```

### The Aethvion Suite Difference

**Current Approach (cloud providers + smart routing):**
```
User: "I need to analyze 1000 CSV files and generate insights"

Aethvion Suite:
1. Recognizes this is a data processing objective.
2. Routes to local model or Gemini Flash for fast, cheap bulk processing.
3. Spawns an agent in a dedicated Workspace to perform the analysis iteratively.
4. Agent documents reusable findings as a Topic in **Persistent Memory**.
5. Routes final strategic insights to Gemini Pro.

Result: Fully automatic, model-agnostic, self-improving system.
```

**Planned Future Approach (once local model support is added):**
```
1. Routes file reading to local Llama model (near-zero cost)
2. Distills raw results with Gemini Flash ($0.10)
3. Routes strategic insights to Gemini Pro ($1.50)
Result: ~$1.60 in API costs vs. $200 with a naive GPT-4 wrapper
```

> **Note:** Local GGUF model inference (via llama-cpp-python) is supported — place models in `localmodels/gguf/`. Local audio models (Kokoro TTS, XTTS-v2, Whisper STT) are available via the Audio Models tab. Full Ollama/vLLM integration for cloud-routing replacement is still on the roadmap.

### The Exponential Advantage

**Why Multi-Provider Support + Model Advancement = Compounding Progress**

1. **Today's Reality:**
    - GPT-4o excels at reasoning
    - Gemini 2.0 Flash is incredibly fast and cheap
    - Each model has different strengths — Misaka routes between them

2. **Tomorrow's Advantage:**
    - GPT-5 releases → Misaka automatically uses it (config change only)
    - Gemini 3 releases → System routes high-stakes tasks there
    - Claude Opus 4 releases → Add to failover chain
    - Local models improve → More tasks run at zero cost (planned)

3. **The Compound Effect:**
    ```
    Week 1: GPT-4o + Gemini Flash
    → System is 2x better than single-model approach

    Month 3: GPT-5 + Gemini 3 + Better local models
    → System is 5x better (model improvements + system learning)

    Year 1: GPT-6 + Gemini 4 + Advanced local models + 500 forged tools
    → System is 20x better (model improvements + massive tool library + deep memory)
    ```

4. **Cost Efficiency at Scale:**
    - Traditional: Every improvement costs more (better model = higher prices)
    - Aethvion Suite: Cost per task decreases over time (smart routing + forged tools reduce cloud API needs)

---

## Installation & Setup

### Prerequisites

- Python 3.10 or higher
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
```

### Step 4: Verify Installation (Optional)

```bash
python -m core.main --test
```

You should see:
```
============================================================
AETHVION SUITE - SPRINT 1 VERIFICATION TEST
============================================================

SYSTEM STATUS
--------------------------------------------------------------
Initialized: True
Active Traces: 0

Firewall Status:
  ...

Provider Status:
  google_ai:
    Status: available
    Model: gemini-2.0-flash
    Healthy: True
```

---

## Your First Session

### Option 1: Web Dashboard (Recommended)

Launch the web interface:

```bash
python -m core.main
```

Open your browser to `http://localhost:8080`

The dashboard includes 25+ tabs: Chat, Agent Workspaces, Image Studio, LLM Arena, AI Conversations, Audio, Audio Models, Files, Tools, Packages, Memory, Games, Logs, Usage analytics, Status, Port Manager, and Settings. See the [Dashboard Context docs](/core/documentation/ai/dashboard-interface-context.md) for full tab descriptions.

**Web Interface Features:**
- Real-time chat with the Misaka Cipher persona
- Live system logs and terminal
- **Agent Workspaces** — multi-step AI task execution with real-time streaming
- Memory explorer
- Visual system status
- LLM Arena (model comparison with enhanced leaderboard)
- AI Image Studio
- **Advanced AI Conversation lab** — human participant, pause/inject, shareable links, history persistence
- **Local Audio Models** — Kokoro (TTS), XTTS-v2 (voice cloning), Whisper (STT)
- **Tabbed Model Registry** — manage cloud and local models in one place
- API usage analytics with Local/API filters
- Package manager

### Option 2: Interactive CLI (For Power Users)

Launch the command-line interface:

```bash
python -m core.main --cli
```

You'll see the main menu:

```
============================================================
         AETHVION SUITE - M.I.S.A.K.A.
    Multitask Intelligence & Strategic Analysis
            Kernel Architecture
============================================================

1. Nexus Core         — Direct AI Interaction
2. The Factory        — Agent Spawning & Execution (Workspaces)
3. The Forge          — Legacy Tool Generation [Advanced]
4. Memory             — Query Knowledge & Persistent Memory
5. Chat History       — Browse Unified History
6. Advanced AI Conv.  — Research Lab
7. LLM Arena          — Model Comparison & Leaderboard
8. Settings           — Configuration & Providers
9. System Status      — Diagnostics
0. Exit

Select option:
```

---

## Example Use Cases

### Use Case 1: Direct AI Interaction

**Scenario:** Ask a question or get help with a problem

**Steps (CLI):**
1. Select `1. Nexus Core`
2. Choose provider (or press Enter for auto-routing)
3. Enter your prompt: "Explain quantum computing to a 10-year-old"
4. Get response with full traceability

**What Happens Behind the Scenes:**
- Request receives unique Trace ID
- Intelligence Firewall scans for PII/sensitive data
- Router selects optimal provider (Gemini Flash for simple questions)
- Response returns with metadata
- Interaction stored in episodic memory

### Use Case 2: Manage Persistent Memory

**Scenario:** Save an important fact about a project for future agents to use.

**Steps (Web Dashboard):**
1. Select the **Persistent Memory** tab.
2. Click **Create Topic**.
3. Enter Topic: `Project_Alpha_Architecture`.
4. Enter Content: `The project uses a microservices architecture with a shared Redis cache.`
5. Click **Commit**.
6. Future agents spawned for this project will now automatically retrieve this context.

**What Happens Behind the Scenes:**
- Topic is stored in `data/vault/knowledge/persistent_memory.json`.
- Entry is indexed for semantic retrieval.
- Agents injected with "Project Alpha" context will prioritize this Topic.

### Use Case 3: Spawn a Specialized Agent

**Scenario:** Analyze Python files in a directory

**Steps (CLI):**
1. Select `2. The Factory`
2. Choose `1. Spawn New Agent`
3. Enter agent details:
   ```
   Name: Code_Analysis_Python
   Domain: Code
   Objective: Analyze all Python files in 'src/' directory for complexity metrics
   ```
4. Agent spawns → executes → reports results → terminates

**What the Agent Does:**
- Reads all .py files in src/
- Analyzes complexity (cyclomatic complexity, line counts, etc.)
- Routes analysis to appropriate model (local for reading, Flash for analysis)
- Stores findings in memory
- Returns structured report

### Use Case 4: Query System Memory

**Scenario:** Recall past interactions or insights

**Steps (CLI):**
1. Select `4. The Memory Tier`
2. Choose `1. Search Episodic Memory`
3. Enter query: "tool generation"
4. System returns semantically similar past interactions

**Memory Types:**
- **Episodic**: "Remember when I asked you to forge a CSV tool?"
- **Core Insights**: "User frequently requests data analysis tools"
- **Knowledge Graph**: Relationships between concepts, tools, agents

---

## Best Practices

### 1. Start Small, Then Scale

**Recommended Progression:**
```
Day 1: Basic interactions (Nexus Core)
↓
Day 2: Forge your first tool
↓
Day 3: Spawn your first agent
↓
Week 1: Combine tools + agents for complex tasks
↓
Week 2: Let system run autonomous multi-day projects
```

### 2. Leverage Smart Routing

**Let the System Decide:**
```python
# DON'T: Force expensive model for simple tasks
Request(prompt="Hello", preferred_provider="openai", model="gpt-4o")

# DO: Let router optimize
Request(prompt="Hello")  # Auto-routes to Gemini Flash (cheaper)
```

**Manual Override for Complex Tasks:**
```python
# Complex architectural decision
Request(
    prompt="Design microservices architecture for e-commerce platform",
    preferred_provider="google_ai",
    model="gemini-1.5-pro-latest"  # Force Pro model
)
```

### 3. Use Memory Effectively

**Store Important Insights:**
- After forging a tool → Check memory to see if similar tools exist
- Before starting complex project → Query memory for past similar projects
- Periodic review → "Show me all tools forged this month"

### 4. Monitor System Status

**Regular Health Checks:**
```bash
# Check provider status
Select: 5. System Status → View Provider Health

# Check active operations
Select: 5. System Status → View Active Traces

# Review recent logs
Check: data/logs/system/aethvion.log
```

### 5. Incremental Tool Building

**Build Tools Progressively:**
```
Session 1: Forge basic CSV reader
↓
Session 2: Forge CSV analyzer (uses CSV reader)
↓
Session 3: Forge CSV visualizer (uses analyzer)
↓
Result: Complete data pipeline, each tool tested independently
```

---

## Configuration & Customization

### Provider Priority

Edit `config/providers.yaml`:

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

Edit `config/model_registry.json`:

```json
{
  "routing_strategy": {
    "verification": "flash",
    "generation": "flash",
    "complex_architecture": "pro",
    "image_generation": "imagen",
    "simple_chat": "flash"
  }
}
```

### Memory Settings

Edit `config/memory.yaml`:

```yaml
episodic_memory:
  enabled: true
  embedding_model: "sentence-transformers/all-MiniLM-L6-v2"
  max_results: 10

knowledge_graph:
  enabled: true
  auto_update: true
```

---

## Troubleshooting

### "Provider not available" Error

**Check:**
1. API key is correctly set in `.env`
2. API key has sufficient credits/quota
3. Network connectivity to provider API

**Fix:**
```bash
# Test specific provider
python -c "from providers import ProviderManager; pm = ProviderManager(); print(pm.health_check_all())"
```

### Tool Generation Fails

**Common Issues:**
1. Description too vague → Be specific about inputs/outputs
2. Complex tool requires Pro model → Retry with model override
3. Security validation fails → Review generated code in logs

**Fix:**
```python
# Force Pro model for complex tools
forge.forge_tool(
    description="Your description",
    force_model="gemini-1.5-pro-latest"
)
```

### High API Costs

**Optimization Steps:**
1. Check `data/logs/system/` for routing decisions
2. Verify simple tasks use Flash model, not Pro
3. Use local GGUF models for data processing — place models in `localmodels/gguf/`
4. Review `data/config/model_registry.json` routing strategy (or use the Model Registry in Settings)

---

## Next Steps

### Beginner Track
1. ✅ Complete installation
2. ✅ Run verification tests
3. → Try 5 different prompts in Nexus Core
4. → Forge your first tool
5. → Spawn your first agent
6. → Query memory to see your history

### Intermediate Track
1. → Build a tool pipeline (3+ tools working together)
2. → Create a custom agent template
3. → Explore knowledge graph relationships
4. → Optimize routing strategy for your use case

### Advanced Track
1. → Design and execute a multi-day autonomous project
2. → Integrate local model for cost reduction (when available)
3. → Contribute custom agent types to the system
4. → Build domain-specific tool libraries

---

## Community & Support

- **Issues**: [GitHub Issues](https://github.com/Aethvion/Aethvion-Suite/issues)
- **Discussions**: [GitHub Discussions](https://github.com/Aethvion/Aethvion-Suite/discussions)
- **Documentation**: [Full Docs](/core/documentation/)

---

## The Vision: Where We're Going

**Current State (v11):**
- ✅ Core orchestration (Nexus)
- ✅ Agent spawning (Factory) + **Agent Workspaces** with ReAct runner and SSE streaming
- ✅ Tool generation (Forge)
- ✅ Memory persistence
- ✅ Multi-provider support + **Tabbed Model Registry**
- ✅ Web dashboard (FastAPI) with 25+ tabs
- ✅ Package manager with safety scoring
- ✅ API usage analytics with Local/API filters
- ✅ LLM Arena with enhanced leaderboard
- ✅ AI Image Studio
- ✅ **AI Conversations** — human participant, pause/inject, shareable links, history persistence
- ✅ **Code IDE** — chat threads, streaming execution, Ctrl+P, status bar, Project Notes, python-exec, continuation loop
- ✅ **Local Audio Models** — Kokoro, XTTS-v2, Whisper
- ✅ Finance: AI market analysis and per-ticker detail panel
- ✅ Tracking: revamped UI with HUD, telemetry, FPS counter
- ✅ Self-update via dashboard Settings

**Near-Term (Next 3 Months):**
- 🔄 Ollama integration for local model management UI
- 🔄 Advanced multi-agent coordination and reliability
- 🔄 Tool forge validation improvements
- 🔄 Enhanced memory retrieval and deeper agent integration

**Long-Term Vision:**
- 🌟 True infinite sessions (weeks-long autonomous work)
- 🌟 Self-improving architecture (system refactors itself)
- 🌟 Cross-domain expertise (single system handles diverse fields)
- 🌟 Human-AI collaboration tools (pair programming at scale)

**The Ultimate Goal:**
```
Give Aethvion Suite a goal of any complexity
→ System breaks it down autonomously
→ Forges necessary tools
→ Spawns required agents
→ Learns from execution
→ Iterates until complete
→ Delivers production-ready result

No human intervention needed.
```

---

**Ready to start?** Fire up the system and experience the power of v11! 🚀

```bash
python -m core.main --cli
```

**Last Updated:** 2026-03-31

---

**Next Reading:**
- [System Overview](./README_Overview.md) - Deeper dive into architecture
- [AI Documentation](/documentation/ai/) - Technical specifications for advanced users
