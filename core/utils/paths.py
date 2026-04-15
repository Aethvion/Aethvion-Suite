"""
Aethvion Suite — Canonical Data Paths
Single source of truth for all data directory/file locations.
Import constants from here instead of constructing paths manually.
"""
from pathlib import Path

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
APPS        = DATA / "apps"
CONFIG      = DATA / "config"
HISTORY     = DATA / "history"
LOGS        = DATA / "logs"
SYSTEM      = DATA / "system"
VAULT       = DATA / "vault"
WORKSPACES  = DATA / "workspaces"
EXPLAINED    = DATA / "explained"


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

# ── History ───────────────────────────────────────────────────────────────────
HISTORY_CHAT     = HISTORY / "chat"             # Standard Misaka chat sessions
HISTORY_AI_CONV  = HISTORY / "ai_conversations" # AI Conversations feature saves
HISTORY_ADVANCED = HISTORY / "advanced"         # Advanced AI Conversations
HISTORY_AGENTS   = HISTORY / "agents"           # Agent Workspace threads
# HISTORY_EXPLAINED moved to EXPLAINED


# ── Scheduled Tasks ───────────────────────────────────────────────────────────
SCHEDULED_TASKS  = DATA / "scheduled_tasks"     # Recurring AI task definitions

# ── Logs ──────────────────────────────────────────────────────────────────────
LOGS_USAGE          = LOGS / "usage"          # AI API usage — YYYY-MM/usage_YYYY-MM-DD.json
LOGS_SYSTEM         = LOGS / "system"         # System / launcher / app logs
LOGS_NOTIFICATIONS  = LOGS / "notifications"  # Notifications — YYYY-MM/YYYY-MM-DD.json

# ── System runtime ────────────────────────────────────────────────────────────
LOCK_FILE    = SYSTEM / "aethvion.lock"
LAUNCHER_LOG = SYSTEM / "launcher.log"
PORTS_JSON   = SYSTEM / "ports.json"
PORTS_LOCK   = SYSTEM / "ports.lock"

# ── Companions ────────────────────────────────────────────────────────────────
COMPANIONS          = DATA / "companions"
COMPANIONS_MISAKA   = COMPANIONS / "misaka_cipher"

# ── Vault (persistent brain) ──────────────────────────────────────────────────
VAULT_PERSONAS  = VAULT / "personas"
VAULT_KNOWLEDGE = VAULT / "knowledge"
VAULT_SEARCH    = VAULT / "search"
VAULT_EPISODIC  = VAULT / "episodic"

# Misaka Cipher persona
PERSONA_MISAKA         = VAULT_PERSONAS / "misakacipher"
PERSONA_MISAKA_MEM     = PERSONA_MISAKA / "memory.json"
PERSONA_MISAKA_BASE    = PERSONA_MISAKA / "base_info.json"
PERSONA_MISAKA_THREADS = PERSONA_MISAKA / "threads"

# Knowledge base
KNOWLEDGE_GRAPH    = VAULT_KNOWLEDGE / "graph.json"
KNOWLEDGE_SOCIAL   = VAULT_KNOWLEDGE / "social.json"
KNOWLEDGE_INSIGHTS = VAULT_KNOWLEDGE / "insights.json"

# ── Workspaces ────────────────────────────────────────────────────────────────
WS_OUTPUTS     = WORKSPACES / "outputs"
WS_TOOLS       = WORKSPACES / "tools"
WS_MEDIA       = WORKSPACES / "media"
WS_UPLOADS     = WORKSPACES / "uploads"
WS_PROJECTS    = WORKSPACES / "projects"
WS_PREFERENCES = WORKSPACES / "preferences.json"
WS_PACKAGES    = WORKSPACES / "packages.json"
WS_FILES_INDEX = WORKSPACES / "files.json"

# ── Agent Corp ─────────────────────────────────────────────────────────────────
CORP_ROOT = DATA / "agent_corps"


def ensure_all() -> None:
    """Create all required data directories. Safe to call at startup."""
    dirs = [
        # Local model weights
        LOCAL_MODELS, LOCAL_MODELS_GGUF, LOCAL_MODELS_AUDIO, LOCAL_MODELS_3D,
        LOCAL_MODELS_AUDIO / "kokoro",
        LOCAL_MODELS_AUDIO / "xtts-v2",
        LOCAL_MODELS_AUDIO / "whisper",
        LOCAL_MODELS_AUDIO_VOICES,
        # App data
        APPS, APP_ARENA, APP_AUDIO, APP_CODE, APP_DRIVEINFO, APP_FINANCE,
        APP_GAMES, APP_HARDWARE, APP_NEXUS, APP_PHOTO, APP_TRACKING, APP_VTUBER,
        CONFIG,
        HISTORY, HISTORY_CHAT, HISTORY_AI_CONV, HISTORY_ADVANCED, HISTORY_AGENTS,
        EXPLAINED,
        LOGS, LOGS_USAGE, LOGS_SYSTEM, LOGS_NOTIFICATIONS,
        SYSTEM,
        COMPANIONS, COMPANIONS_MISAKA, COMPANIONS_MISAKA / "history",
        VAULT, VAULT_PERSONAS, VAULT_KNOWLEDGE, VAULT_SEARCH, VAULT_EPISODIC,
        PERSONA_MISAKA, PERSONA_MISAKA_THREADS,
        WORKSPACES, WS_OUTPUTS, WS_TOOLS, WS_MEDIA, WS_UPLOADS, WS_PROJECTS,
        CORP_ROOT,
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
