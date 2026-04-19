# Aethvion Suite Documentation

**Note: This documentation was updated on 2026-04-19 to reflect the Aethvion Suite (v1.4) architecture.**

---

## 📚 Documentation Structure

This documentation is organized into two main tiers designed for different audiences:

### 👥 Human Tier (`/documentation/human/`)
Comprehensive, user-friendly guides for humans interacting with the system.

**Files:**
- **[readme-overview.md](./human/readme-overview.md)** - System philosophy and architecture
  - Understanding what makes Aethvion Suite different
  - The Five Pillars (AetherCore, Companions, Bridges, Workspaces, Memory)
  - Infinite session goals and agentic workflows
  - Why this architecture matters
  
- **[getting-started.md](./human/getting-started.md)** - Practical guide for new users
  - Installation and setup instructions
  - API key configuration
  - First session with a companion
  - Example use cases with code
  - Best practices and troubleshooting
  - Next steps for beginners to advanced users

### 🤖 AI Tier (`/documentation/ai/`)
Machine-readable specifications for AI agents operating within the system.

**Files:**
- **[system-spec.md](./ai/system-spec.md)** - Complete technical specification
  - Directory structure (detailed)
  - Data flow architecture (entry point → execution)
  - Companion system specification
  - Bridges system specification
  - External API touchpoints
  - Model registry specification
  - Memory system specification
  - Configuration priorities
  
- **[agent-mission.md](./ai/agent-mission.md)** - Reasoning constraints and routing rules
  - Primary directives for AI agents
  - Core reasoning constraints
  - Cost-aware model selection
  - Security-first routing rules
  - Companion system awareness
  - Intelligent routing decision matrix
  - Agent coordination rules
  - Explicit DO/DON'T rules
  
- **[assistant-tools.md](./ai/assistant-tools.md)** - Assistant-specific capabilities
  - List of tools available to the dashboard assistant
  - Configuration toggles (context, control)
  - Emotion system IDs
  - Full tab navigation ID reference
  
- **[dashboard-interface-context.md](./ai/dashboard-interface-context.md)** - UI context for AI
  - Detailed description of all dashboard tabs
  - Navigation tag specifications ([SwitchTab])
  - Companion tab descriptions

- **[evolution-logic.md](./ai/evolution-logic.md)** - Self-evolution strategy
  - Agentic Workspaces and Persistent Memory
  - Companion Memory growth system
  - Tool Forge pipeline (legacy)
  - Self-improvement feedback loops

---

## 🎯 Quick Navigation

### I want to...

**Understand what Aethvion Suite is:**
→ Read [readme-overview.md](./human/readme-overview.md)

**Get started with the system:**
→ Follow [getting-started.md](./human/getting-started.md)

**Implement an AI agent:**
→ Study [agent-mission.md](./ai/agent-mission.md) for constraints and rules

**Understand the technical architecture:**
→ Reference [system-spec.md](./ai/system-spec.md) for complete specs

**Learn how companions work:**
→ See the Companion System section in [system-spec.md](./ai/system-spec.md)

**Learn how bridges work:**
→ See the Bridges System section in [system-spec.md](./ai/system-spec.md)

**Learn how self-evolution works:**
→ Deep dive into [evolution-logic.md](./ai/evolution-logic.md)

**See the big picture:**
→ Start with root [README.md](../README.md)

---

## 📖 Reading Order Recommendations

### For New Users (Human Audience)
1. Root [README.md](../README.md) - Landing page overview
2. [readme-overview.md](./human/readme-overview.md) - Understand the philosophy
3. [getting-started.md](./human/getting-started.md) - Hands-on setup and examples

### For Developers
1. [readme-overview.md](./human/readme-overview.md) - High-level architecture
2. [system-spec.md](./ai/system-spec.md) - Technical details
3. [evolution-logic.md](./ai/evolution-logic.md) - Tool generation and companion memory mechanics
4. [agent-mission.md](./ai/agent-mission.md) - Implementation guidelines

### For AI Agents
1. [agent-mission.md](./ai/agent-mission.md) - Primary directives and constraints
2. [system-spec.md](./ai/system-spec.md) - System reference
3. [evolution-logic.md](./ai/evolution-logic.md) - Tool creation and memory workflow
4. [dashboard-interface-context.md](./ai/dashboard-interface-context.md) - UI navigation reference

---

## 🔄 Documentation Maintenance

### Update Frequency
- **Core Architecture Docs:** Updated on major architectural changes
- **Configuration Specs:** Updated when `config/` files change
- **Feature Docs:** Updated when new capabilities are added
- **Examples:** Expanded as common patterns emerge

### Version History
- **2026-02-18:** Initial comprehensive documentation created
  - Complete human tier guides
  - Machine-readable AI tier specs
  - Root README updated as landing page
- **2026-04-19:** Major update to v1.4 state
  - Companions system documented (Misaka Cipher, Axiom, Lyra)
  - Bridges system documented (6 active bridges)
  - AetherCore replacing Nexus Core references
  - Full tab registry updated (35+ tabs)
  - Companion memory evolution added to evolution-logic.md

### Planned Enhancements
- [ ] Video walkthroughs for Getting Started
- [ ] Interactive API documentation
- [ ] Advanced use case tutorials
- [ ] Companion creation guide
- [ ] Multi-agent coordination patterns
- [ ] Performance optimization guide

---

## 📊 Documentation Coverage

### Human Tier (User-Facing)
- ✅ High-level overview and philosophy
- ✅ Installation and setup
- ✅ Companion system overview
- ✅ Basic to advanced examples
- ✅ Best practices
- ✅ Troubleshooting
- ⚠️ Video tutorials (planned)
- ⚠️ Advanced patterns library (planned)

### AI Tier (Machine-Readable)
- ✅ Complete system specification
- ✅ Data flow architecture
- ✅ Companion system specification
- ✅ Bridges system specification
- ✅ Reasoning constraints
- ✅ Routing rules and decision matrices
- ✅ Evolution pipeline
- ✅ Quality metrics
- ⚠️ Automated testing guides (planned)

### Code Documentation
- ✅ Inline docstrings in core modules
- ✅ Type hints throughout codebase
- ⚠️ Auto-generated API docs (planned)

---

## 🤝 Contributing to Documentation

### Found an Error?
1. Check if it's already reported in [Issues](https://github.com/Aethvion/Aethvion-Suite/issues)
2. If not, open a new issue with:
   - Documentation file name
   - Section/line number
   - Description of the error
   - Suggested correction

### Want to Add Content?
1. Identify the appropriate tier (Human or AI)
2. Follow the existing style and structure
3. Include the date stamp header
4. Submit a pull request

### Documentation Standards
- **Markdown:** Use standard GitHub-flavored markdown
- **Headers:** Clear H1/H2/H3 hierarchy
- **Code Blocks:** Always specify language for syntax highlighting
- **Links:** Use relative paths for internal links
- **Examples:** Include practical, runnable examples
- **AI Tier:** Prioritize factual bullet points over prose

---

## 🔗 External Resources

### Related Configuration
- **Provider Configuration:** [config/providers.yaml](../config/providers.yaml)
- **Model Registry:** [data/config/model_registry.json](../data/config/model_registry.json)
- **Companion Registry:** [core/companions/registry.py](../core/companions/registry.py)
- **Bridge Registry:** [core/bridges/registry.json](../core/bridges/registry.json)
- **Canonical Paths:** [core/utils/paths.py](../core/utils/paths.py)

### Community
- **GitHub Repository:** [Aethvion/Aethvion-Suite](https://github.com/Aethvion/Aethvion-Suite)
- **Issues:** Report bugs or request features
- **Discussions:** Ask questions and share ideas
- **Pull Requests:** Contribute improvements

---

## 📝 Glossary

**Key Terms Referenced in Documentation:**

- **AetherCore:** Central AI gateway (`core/aether_core.py`); single point of entry for all AI requests; handles routing, provider failover, Intelligence Firewall, and Trace IDs
- **Companions:** Persistent AI personalities (Misaka Cipher, Axiom, Lyra) with per-companion memory, config, and tool access; primary user-facing AI layer
- **Companion Engine:** `core/companions/companion_engine.py`; manages chat history, tool execution, memory updates, and prompt injection for all companions
- **Bridges:** Registry-driven system integrations (`core/bridges/`); connects companions to Spotify, weather, system info, media, screen capture, and webcam; status injected as `{bridges_block}` into companion prompts
- **Intelligence Firewall:** Security layer in AetherCore that scans all requests for PII and credentials before external API calls
- **Workspaces:** Dedicated filesystems for agents to perform iterative ReAct loops (`data/modes/workspaces/`)
- **Persistent Memory:** Curated knowledge topics (JSON) for long-term consistency; stored in `data/modes/companions/knowledge/`
- **Companion Memory:** Per-companion dynamic profile (`memory.json`) and stable identity (`base_info.json`); synthesized via XML tag extraction from conversations
- **Agent Corp:** Multi-agent coordination hub for complex orchestrated tasks
- **Research Board:** Multi-director AI debate and research environment
- **Trace ID:** Unique identifier (format: `MCTR-YYYYMMDDHHMMSS-UUID`) for request tracking
- **Provider:** External AI service (Google AI, OpenAI, xAI Grok, Anthropic)
- **Model Registry:** Configuration file defining available models and routing strategy (`data/config/model_registry.json`)
- **Episodic Memory:** Vector-based storage of raw interactions (ChromaDB) per companion
- **Knowledge Graph:** NetworkX-based relationship mapping between entities
- **Core Insights:** High-level facts derived from episodic memory summarization
- **Schedule Manager:** Manages recurring AI tasks with cron-based scheduling
- **Notification Hub:** Real-time system-wide alerting and history

---

## 🎯 Documentation Philosophy

This documentation follows a **dual-tier approach**:

1. **Human Tier:** Explains the "why" and "how" with context, examples, and narrative
2. **AI Tier:** Provides "what" and "where" with factual specs and machine-readable structure

**Principles:**
- ✅ Keep human docs engaging and narrative
- ✅ Keep AI docs factual and structured
- ✅ Update both tiers simultaneously when architecture changes
- ✅ Include practical examples in human docs
- ✅ Include exact file paths and data structures in AI docs
- ✅ Document limitations and roadmap items honestly
- ✅ Always include the date stamp with generation date

---

**Last Updated:** 2026-04-19

**Maintained By:** Agentic Sprint Cycles + Human Contributors

**Feedback Welcome:** [Open an Issue](https://github.com/Aethvion/Aethvion-Suite/issues/new)
