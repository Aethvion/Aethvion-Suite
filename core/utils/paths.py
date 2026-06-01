"""
Aethvion Suite — Canonical Data Paths
Single source of truth for all data directory/file locations.
Import constants from here instead of constructing paths manually.
"""
from pathlib import Path

# ── Root ──────────────────────────────────────────────────────────────────────
# ── Root ──────────────────────────────────────────────────────────────────────
_PROJECT = Path(__file__).parent.parent.parent
DATA = _PROJECT / "data"

# ── Committed config (lives in core/config/, version-controlled) ──────────────
_CORE_CONFIG = _PROJECT / "core" / "config"
MODEL_DEFAULTS_DIR       = _CORE_CONFIG / "model_defaults"
SUGGESTED_MODELS_DIR    = MODEL_DEFAULTS_DIR / "suggested"
SUGGESTED_API_MODELS    = _CORE_CONFIG / "suggested_apimodels.json" # Legacy
SUGGESTED_LOCAL_MODELS  = _CORE_CONFIG / "suggested_localmodels.json"
SUGGESTED_AUDIO_MODELS  = _CORE_CONFIG / "suggested_localaudiomodels.json"

# ── Local model storage (user-downloaded weights, separate from app data) ─────
LOCAL_MODELS       = _PROJECT / "localmodels"
LOCAL_MODELS_GGUF  = LOCAL_MODELS / "gguf"    # GGUF chat models (llama.cpp)
LOCAL_MODELS_AUDIO = LOCAL_MODELS / "audio"   # TTS / STT / voice models
LOCAL_MODELS_AUDIO_VOICES = LOCAL_MODELS_AUDIO / "voices"  # cloned voice WAVs
LOCAL_MODELS_3D    = LOCAL_MODELS / "3d"      # 3D models and pipelines

# ── Top-level directories ─────────────────────────────────────────────────────
APPS           = DATA / "apps"
CONFIG         = DATA / "config"
LOGS           = DATA / "logs"
SYSTEM         = DATA / "system"
MODES          = DATA / "modes"
COMPANIONS     = DATA / "companions"   # Top-level — not a mode subdir
DEFAULT_OUTPUT = DATA / "default_output"

# ── Modes (Tab-specific state & history) ──────────────────────────────────────
MODE_CHAT         = MODES / "chat"
MODE_AGENTS       = MODES / "agents"
MODE_AGENT_CORP   = MODES / "agent_corp"
MODE_AI_CONV      = MODES / "ai_conversations"
MODE_ADV_AICONV   = MODES / "advanced_ai_conversations"
MODE_EXPLAINED    = MODES / "explained"
EXPLAINED         = MODE_EXPLAINED
MODE_WORKSPACES   = MODES / "workspaces"
MODE_SCHEDULE     = MODES / "schedule"
MODE_WORLDSIM     = MODES / "worldsim"
WORLDSIM          = MODE_WORLDSIM   # kept for WorldSim (separate product)
MODE_COMPANIONS   = COMPANIONS      # Alias kept for backward compatibility

# ── AethvionDB data root ──────────────────────────────────────────────────────
AETHVIONDB        = DATA / "aethviondb"

# ── Code IDE + Agent workspaces ───────────────────────────────────────────────
# Standalone feature root — workspaces, threads, project memory, blueprints.
# (Moved from data/modes/agents/ to give Code a proper top-level home.)
CODE              = DATA / "code"

# Legacy compatibility / Common aliases
HISTORY     = MODES     # Generic history root
VAULT       = COMPANIONS
WORKSPACES  = MODE_WORKSPACES
CORP_ROOT   = MODE_AGENT_CORP

# ── Apps ──────────────────────────────────────────────────────────────────────
APP_ARENA     = APPS / "arena"
APP_AUDIO     = APPS / "audio"
APP_CODE      = APPS / "code"
APP_DRIVEINFO = APPS / "driveinfo"
APP_HARDWARE  = APPS / "hardwareinfo"
APP_BRIDGES  = APPS / "nexus"
APP_PHOTO     = APPS / "photo"

# ── Config files ──────────────────────────────────────────────────────────────
MODEL_REGISTRY         = CONFIG / "model_registry.json"
SETTINGS               = CONFIG / "settings.json"
LOCAL_INFERENCE_CONFIG = CONFIG / "local_inference_config.json"
WEBHOOKS_CONFIG        = CONFIG / "webhooks.json"
SYSTEM_SPECS           = CONFIG / "system_specs.json"

# ── Mode Subpaths ─────────────────────────────────────────────────────────────
# Chat
HISTORY_CHAT     = MODE_CHAT
# AI Conversations
HISTORY_AI_CONV  = MODE_AI_CONV
# Advanced AI Conversations
HISTORY_ADVANCED = MODE_ADV_AICONV
# Agents / Code workspaces (redirected to the new top-level CODE root)
HISTORY_AGENTS   = CODE
# Explained
HISTORY_EXPLAINED = MODE_EXPLAINED

# ── Scheduled Tasks ───────────────────────────────────────────────────────────
SCHEDULED_TASKS  = MODE_SCHEDULE           # Recurring AI task definitions

# ── Logs ──────────────────────────────────────────────────────────────────────
LOGS_USAGE          = LOGS / "usage"          # AI API usage — YYYY-MM/usage_YYYY-MM-DD.json
LOGS_NOTIFICATIONS  = LOGS / "notifications"  # Notifications — YYYY-MM/YYYY-MM-DD.json
LAUNCHER_LOG        = LOGS / "launcher.log"
CRASH_LOG           = LOGS / "crashlog.log"
LOGS_SYSTEM         = LOGS                    # Unified system logs root

# ── System runtime ────────────────────────────────────────────────────────────
LOCK_FILE    = SYSTEM / "aethvion.lock"
PORTS_JSON   = SYSTEM / "ports.json"
PORTS_LOCK   = SYSTEM / "ports.lock"


# ── Companions (persistent brain) ─────────────────────────────────────────────
COMPANIONS_PERSONAS  = COMPANIONS / "personas"
COMPANIONS_KNOWLEDGE = COMPANIONS / "knowledge"
COMPANIONS_MEMORY    = COMPANIONS / "memory"
VAULT_PERSONAS       = COMPANIONS_PERSONAS
VAULT_KNOWLEDGE      = COMPANIONS_KNOWLEDGE
VAULT_MEMORY         = COMPANIONS_MEMORY
VAULT_EPISODIC       = VAULT_MEMORY           # Legacy alias for memory storage
VAULT_SEARCH         = VAULT_MEMORY           # Legacy alias for search storage

# ── Legacy Companion Shortcuts (Deprecated: Use dynamic paths) ───────────────
COMPANIONS_MISAKA        = COMPANIONS_PERSONAS / "misakacipher"
PERSONA_MISAKA           = COMPANIONS_MISAKA
PERSONA_MISAKA_KNOWLEDGE = COMPANIONS_KNOWLEDGE / "misakacipher"
PERSONA_MISAKA_EPISODIC  = COMPANIONS_MEMORY / "misakacipher"


# Knowledge base
KNOWLEDGE_GRAPH    = VAULT_KNOWLEDGE / "graph.json"
KNOWLEDGE_SOCIAL   = VAULT_KNOWLEDGE / "social.json"
KNOWLEDGE_INSIGHTS = VAULT_KNOWLEDGE / "insights.json"
PERSISTENT_MEMORY_JSON = VAULT_KNOWLEDGE / "persistent_memory.json"

# ── Workspaces ────────────────────────────────────────────────────────────────
WS_OUTPUTS     = MODE_WORKSPACES / "outputs"
WS_TOOLS       = MODE_WORKSPACES / "tools"
WS_MEDIA       = MODE_WORKSPACES / "media"
WS_UPLOADS     = MODE_WORKSPACES / "uploads"
WS_PROJECTS    = MODE_WORKSPACES / "projects"
WS_PREFERENCES = MODE_WORKSPACES / "preferences.json"
WS_PACKAGES    = MODE_WORKSPACES / "packages.json"
WS_FILES_INDEX = MODE_WORKSPACES / "files.json"

# ── Code agent prompts ──────────────────────────────────────────────────────
CODE_AGENT_PROMPT = _CORE_CONFIG / "code" / "agent_system_prompt.txt"
CODE_CORP_PROMPT  = _CORE_CONFIG / "code" / "corp_system_prompt.txt"

# ── External API ─────────────────────────────────────────────────────────────
EXT_API_DIR    = DATA / "external_api"
EXT_API_KEYS   = EXT_API_DIR / "keys.json"
EXT_API_CONFIG = EXT_API_DIR / "config.json"

# ── Overlay ───────────────────────────────────────────────────────────────────
OVERLAY_DIR    = DATA / "overlay"
OVERLAY_CONFIG = OVERLAY_DIR / "config.json"
OVERLAY_SCRIPT = _PROJECT / "apps" / "overlay" / "main.py"

# ── Performance Tests ─────────────────────────────────────────────────────────
PERFORMANCE_DIR = _PROJECT / "core" / "tests" / "performance"
PERFORMANCE_REPORT_JSON = PERFORMANCE_DIR / "latest_report.json"
PERFORMANCE_REPORT_MD = PERFORMANCE_DIR / "latest_report.md"

# ── Default Output ────────────────────────────────────────────────────────────
OUT_IMAGES    = DEFAULT_OUTPUT / "images"
OUT_MODELS    = DEFAULT_OUTPUT / "models"
OUT_DOCS      = DEFAULT_OUTPUT / "documents"


def ensure_all() -> None:
    """Create all required data directories. Safe to call at startup."""
    dirs = [
        # Local model weights
        LOCAL_MODELS, LOCAL_MODELS_GGUF, LOCAL_MODELS_AUDIO, LOCAL_MODELS_3D,
        LOCAL_MODELS_AUDIO / "kokoro", LOCAL_MODELS_AUDIO / "xtts-v2",
        LOCAL_MODELS_AUDIO / "whisper", LOCAL_MODELS_AUDIO_VOICES,
        # Top level
        APPS, CONFIG, LOGS, SYSTEM, COMPANIONS, MODES, DEFAULT_OUTPUT,
        APP_ARENA, APP_AUDIO, APP_CODE, APP_DRIVEINFO,
        APP_HARDWARE, APP_BRIDGES, APP_PHOTO,
        # Modes
        MODE_CHAT, MODE_AGENTS, MODE_AGENT_CORP, MODE_AI_CONV, MODE_ADV_AICONV,
        MODE_EXPLAINED, MODE_WORKSPACES, MODE_WORLDSIM,
        AETHVIONDB,
        # Code / Agent workspaces
        CODE,
        # Sub-directories
        LOGS_USAGE, LOGS_NOTIFICATIONS,
        COMPANIONS_PERSONAS, COMPANIONS_KNOWLEDGE, COMPANIONS_MEMORY,
        WS_OUTPUTS, WS_TOOLS, WS_MEDIA, WS_UPLOADS, WS_PROJECTS,
        OUT_IMAGES, OUT_MODELS, OUT_DOCS,
        SCHEDULED_TASKS,
        EXT_API_DIR,
        OVERLAY_DIR,
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
