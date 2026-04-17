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
SUGGESTED_API_MODELS    = _CORE_CONFIG / "suggested_apimodels.json"
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
COMPANIONS     = DATA / "companions"
MODES          = DATA / "modes"
DEFAULT_OUTPUT = DATA / "default_output"

# ── Modes (Tab-specific data) ─────────────────────────────────────────────────
MODE_CHAT         = MODES / "chat"
MODE_AGENTS       = MODES / "agents"
MODE_AGENT_CORP   = MODES / "agent_corp"
MODE_AI_CONV      = MODES / "ai_conversations"
MODE_ADV_AICONV   = MODES / "advanced_ai_conversations"
MODE_EXPLAINED    = MODES / "explained"
MODE_VAULT        = MODES / "vault"
MODE_WORKSPACES   = MODES / "workspaces"

# Legacy compatibility / Common aliases
HISTORY     = MODES     # Generic history root
VAULT       = MODE_VAULT
WORKSPACES  = MODE_WORKSPACES
CORP_ROOT   = MODE_AGENT_CORP

# ── Apps ──────────────────────────────────────────────────────────────────────
APP_ARENA     = APPS / "arena"
APP_AUDIO     = APPS / "audio"
APP_CODE      = APPS / "code"
APP_DRIVEINFO = APPS / "driveinfo"
APP_FINANCE   = APPS / "finance"
APP_GAMES     = APPS / "games"
APP_HARDWARE  = APPS / "hardwareinfo"
APP_NEXUS     = APPS / "nexus"
APP_PHOTO     = APPS / "photo"
APP_TRACKING  = APPS / "tracking"
APP_VTUBER    = APPS / "vtuber"

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
# Agents
HISTORY_AGENTS   = MODE_AGENTS
# Explained
HISTORY_EXPLAINED = MODE_EXPLAINED

# ── Scheduled Tasks ───────────────────────────────────────────────────────────
SCHEDULED_TASKS  = DATA / "scheduled_tasks"     # Recurring AI task definitions

# ── Logs ──────────────────────────────────────────────────────────────────────
LOGS_USAGE          = LOGS / "usage"          # AI API usage — YYYY-MM/usage_YYYY-MM-DD.json
LOGS_NOTIFICATIONS  = LOGS / "notifications"  # Notifications — YYYY-MM/YYYY-MM-DD.json
LAUNCHER_LOG        = LOGS / "launcher.log"
CRASH_LOG           = LOGS / "crashlog.log"

# ── System runtime ────────────────────────────────────────────────────────────
LOCK_FILE    = SYSTEM / "aethvion.lock"
PORTS_JSON   = SYSTEM / "ports.json"
PORTS_LOCK   = SYSTEM / "ports.lock"

# ── Companions ────────────────────────────────────────────────────────────────
COMPANIONS_MISAKA   = COMPANIONS / "misaka_cipher"

# ── Vault (persistent brain) ──────────────────────────────────────────────────
VAULT_PERSONAS  = MODE_VAULT / "personas"
VAULT_KNOWLEDGE = MODE_VAULT / "knowledge"
VAULT_SEARCH    = MODE_VAULT / "search"
VAULT_EPISODIC  = MODE_VAULT / "episodic"

# Misaka Cipher persona
PERSONA_MISAKA         = VAULT_PERSONAS / "misakacipher"
PERSONA_MISAKA_MEM     = PERSONA_MISAKA / "memory.json"
PERSONA_MISAKA_BASE    = PERSONA_MISAKA / "base_info.json"
PERSONA_MISAKA_THREADS = PERSONA_MISAKA / "threads"

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
        # Apps
        APP_ARENA, APP_AUDIO, APP_CODE, APP_DRIVEINFO, APP_FINANCE,
        APP_GAMES, APP_HARDWARE, APP_NEXUS, APP_PHOTO, APP_TRACKING, APP_VTUBER,
        # Modes
        MODE_CHAT, MODE_AGENTS, MODE_AGENT_CORP, MODE_AI_CONV, MODE_ADV_AICONV,
        MODE_EXPLAINED, MODE_VAULT, MODE_WORKSPACES,
        # Sub-directories
        LOGS_USAGE, LOGS_NOTIFICATIONS,
        COMPANIONS_MISAKA, COMPANIONS_MISAKA / "history",
        VAULT_PERSONAS, VAULT_KNOWLEDGE, VAULT_SEARCH, VAULT_EPISODIC,
        PERSONA_MISAKA, PERSONA_MISAKA_THREADS,
        WS_OUTPUTS, WS_TOOLS, WS_MEDIA, WS_UPLOADS, WS_PROJECTS,
        OUT_IMAGES, OUT_MODELS, OUT_DOCS,
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
