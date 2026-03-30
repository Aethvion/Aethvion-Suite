# Aethvion Suite Documentation

**Note: This documentation was updated on 2026-03-30 to reflect the Aethvion Suite (v11) architecture.**

---

## 📚 Documentation Structure

This documentation is organized into two main tiers designed for different audiences:

### 👥 Human Tier (`/documentation/human/`)
Comprehensive, user-friendly guides for humans interacting with the system.

**Files:**
- **[readme-overview.md](./human/readme-overview.md)** - System philosophy and architecture
  - Understanding the "vibe" of Aethvion Suite
  - The Four Pillars (Nexus, Factory, Forge, Memory)
  - Infinite session goals and capabilities
  - Why this architecture matters
  
- **[getting-started.md](./human/getting-started.md)** - Practical guide for new users
  - Installation and setup instructions
  - API key configuration
  - Example use cases with code
  - Best practices and troubleshooting
  - Next steps for beginners to advanced users

### 🤖 AI Tier (`/documentation/ai/`)
Machine-readable specifications for AI agents operating within the system.

**Files:**
- **[system-spec.md](./ai/system-spec.md)** - Complete technical specification
  - Directory structure (detailed)
  - Data flow architecture (entry point → execution)
  - External API touchpoints
  - Model registry specification
  - Tool and agent definitions
  - Memory system specification
  - Configuration priorities
  
- **[agent-mission.md](./ai/agent-mission.md)** - Reasoning constraints and routing rules
  - Primary directives for AI agents
  - Core reasoning constraints
  - Cost-aware model selection
  - Security-first routing rules
  - Intelligent routing decision matrix
  - Agent coordination rules
  - Explicit DO/DON'T rules
  
- **[assistant-tools.md](./ai/assistant-tools.md)** - Assistant-specific capabilities
  - List of tools available to the dashboard assistant
  - Configuration toggles (context, control)
  - Emotion system IDs
  
- **[dashboard-interface-context.md](./ai/dashboard-interface-context.md)** - UI context for AI
  - Detailed description of all 14+ dashboard tabs
  - Navigation tag specifications ([SwitchTab])
  - Subtab deep-linking IDs

- **[evolution-logic.md](./ai/evolution-logic.md)** - Tool creation and validation
  - The Forge pipeline (4 phases: Analysis, Generation, Validation, Registration)
  - How the system "knows" a tool is ready
  - Tool lifecycle management
  - Self-improvement mechanism
  - Quality metrics and validation feedback loop

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

**Learn how tool generation works:**
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
3. [evolution-logic.md](./ai/evolution-logic.md) - Tool generation mechanics
4. [agent-mission.md](./ai/agent-mission.md) - Implementation guidelines

### For AI Agents
1. [agent-mission.md](./ai/agent-mission.md) - Primary directives and constraints
2. [system-spec.md](./ai/system-spec.md) - System reference
3. [evolution-logic.md](./ai/evolution-logic.md) - Tool creation workflow

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

### Planned Enhancements
- [ ] Video walkthroughs for Getting Started
- [ ] Interactive API documentation
- [ ] Advanced use case tutorials
- [ ] Tool creation workshop guide
- [ ] Multi-agent coordination patterns
- [ ] Performance optimization guide

---

## 📊 Documentation Coverage

### Human Tier (User-Facing)
- ✅ High-level overview and philosophy
- ✅ Installation and setup
- ✅ Basic to advanced examples
- ✅ Best practices
- ✅ Troubleshooting
- ⚠️ Video tutorials (planned)
- ⚠️ Advanced patterns library (planned)

### AI Tier (Machine-Readable)
- ✅ Complete system specification
- ✅ Data flow architecture
- ✅ Reasoning constraints
- ✅ Routing rules and decision matrices
- ✅ Tool generation pipeline
- ✅ Quality metrics
- ⚠️ Automated testing guides (planned)

### Code Documentation
- ✅ Inline docstrings in core modules
- ✅ Type hints throughout codebase
- ⚠️ Auto-generated API docs (planned)

---

## 🤝 Contributing to Documentation

### Found an Error?
1. Check if it's already reported in [Issues](https://github.com/Aethvion/Misaka-Cipher/issues)
2. If not, open a new issue with:
   - Documentation file name
   - Section/line number
   - Description of the error
   - Suggested correction

### Want to Add Content?
1. Identify the appropriate tier (Human or AI)
2. Follow the existing style and structure
3. Include the continuity header (date stamp)
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

### Related Documentation
- **Aethvion Framework:** [config/aethvion.yaml](../config/aethvion.yaml)
- **Provider Configuration:** [config/providers.yaml](../config/providers.yaml)
- **Model Registry:** [config/model_registry.json](../config/model_registry.json)
- **Security Rules:** [config/security.yaml](../config/security.yaml)

### Community
- **GitHub Repository:** [Aethvion/Aethvion-Suite](https://github.com/Aethvion/Aethvion-Suite)
- **Issues:** Report bugs or request features
- **Discussions:** Ask questions and share ideas
- **Pull Requests:** Contribute improvements

---

## 📝 Glossary

**Key Terms Referenced in Documentation:**

- **Nexus Core:** Central orchestration hub, single point of entry for all requests
- **The Factory:** Agent spawning engine that creates transient worker agents
- **The Forge:** Tool generation pipeline that writes Python tools autonomously
- **The Memory Tier:** Multi-tiered persistence system (Episodic, Insights, Knowledge Graph)
- **Trace ID:** Unique identifier (format: `MCTR-YYYYMMDDHHMMSS-UUID`) for request tracking
- **Aethvion Standard:** Naming convention `[Domain]_[Action]_[Object]` for tools/agents
- **Intelligence Firewall:** Security layer that scans for PII/credentials before external API calls
- **Provider:** External AI service (Google AI, OpenAI, xAI Grok)
- **Model Registry:** Configuration file defining available models and routing strategy
- **Episodic Memory:** Vector-based storage of raw interactions (ChromaDB)
- **Knowledge Graph:** NetworkX-based relationship mapping between entities
- **Core Insights:** High-level facts derived from episodic memory summarization
- **Tool Registry:** JSON file tracking all generated and standard tools
- **Agent Registry:** In-memory tracking of active agents
- **Infinite Session:** Long-running autonomous execution mode for complex goals
- **Self-Evolution:** System's ability to create tools and improve itself autonomously

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
- ✅ Always include the continuity header with generation date

---

**Last Updated:** 2026-03-30

**Maintained By:** Agentic Sprint Cycles + Human Contributors

**Feedback Welcome:** [Open an Issue](https://github.com/Aethvion/Aethvion-Suite/issues/new)
