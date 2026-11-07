import importlib
import re
from pathlib import Path
from typing import Optional
from core.utils import get_logger, load_json, atomic_json_write

logger = get_logger(__name__)

PROJECT_ROOT  = Path(__file__).parent.parent.parent
REGISTRY_FILE = Path(__file__).parent / "registry.json"
PROFILES_FILE = PROJECT_ROOT / "data" / "bridges" / "connector_profiles.json"

DEFAULT_PROFILES = [
    {
        "id": "full_local",
        "name": "Full Local Suite",
        "description": "Unrestricted access to all system, co-working, media, and web connectors. Recommended for local GGUF models and trusted companions.",
        "privacy_badge": "Local & Cloud",
        "icon": "fas fa-shield-halved",
        "builtin": True,
        "allowed_connectors": [
            "screen_capture",
            "screen_ocr",
            "window_focus",
            "clipboard_link",
            "git_link",
            "process_watcher",
            "media_sentinel",
            "system_link",
            "webcam_capture",
            "companion_tasks",
            "web_search",
            "webpage_reader",
            "youtube_link",
            "reddit",
            "weather_link",
            "spotify"
        ]
    },
    {
        "id": "cloud_safe",
        "name": "Public / Cloud Safe",
        "description": "Blocks local screen, clipboard, git, webcam, and PC telemetry connectors so private machine data is never uploaded to cloud APIs.",
        "privacy_badge": "Cloud Safe",
        "icon": "fas fa-cloud-shield",
        "builtin": True,
        "allowed_connectors": [
            "companion_tasks",
            "web_search",
            "webpage_reader",
            "youtube_link",
            "reddit",
            "weather_link",
            "spotify"
        ]
    },
    {
        "id": "ambient_observer",
        "name": "Ambient Context Only",
        "description": "Passive read-only context (active window focus, now-playing media, PC stats, tasks, weather) without screenshots, camera, or active web queries.",
        "privacy_badge": "Passive Only",
        "icon": "fas fa-eye",
        "builtin": True,
        "allowed_connectors": [
            "window_focus",
            "process_watcher",
            "media_sentinel",
            "system_link",
            "companion_tasks",
            "weather_link"
        ]
    },
    {
        "id": "sandboxed",
        "name": "Sandboxed (No Connectors)",
        "description": "Disables all external and local connectors for strictly isolated conversation.",
        "privacy_badge": "Isolated",
        "icon": "fas fa-lock",
        "builtin": True,
        "allowed_connectors": []
    }
]


def get_registry() -> dict:
    """Load the Bridge registry."""
    return load_json(REGISTRY_FILE, default={"modules": []})


def save_registry(registry: dict) -> None:
    """Persist the Bridge registry atomically."""
    atomic_json_write(REGISTRY_FILE, registry)


def get_profiles() -> list[dict]:
    """Load saved Connector Profiles (initializing defaults and syncing new built-in connectors)."""
    PROFILES_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not PROFILES_FILE.exists():
        atomic_json_write(PROFILES_FILE, {"profiles": DEFAULT_PROFILES})
        return [dict(p) for p in DEFAULT_PROFILES]
    data = load_json(PROFILES_FILE, default={"profiles": DEFAULT_PROFILES})
    profiles = data.get("profiles", [])
    if not profiles:
        atomic_json_write(PROFILES_FILE, {"profiles": DEFAULT_PROFILES})
        return [dict(p) for p in DEFAULT_PROFILES]

    # Ensure built-in profiles stay synced with newly registered connectors
    default_map = {dp["id"]: dp for dp in DEFAULT_PROFILES}
    changed = False
    for p in profiles:
        pid = p.get("id")
        if pid in default_map and p.get("builtin"):
            expected = default_map[pid]["allowed_connectors"]
            cur = p.get("allowed_connectors", [])
            for cid in expected:
                if cid not in cur:
                    cur.append(cid)
                    changed = True
            p["allowed_connectors"] = cur
    if changed:
        atomic_json_write(PROFILES_FILE, {"profiles": profiles})
    return profiles


def save_profiles(profiles: list[dict]) -> None:
    """Persist Connector Profiles atomically."""
    PROFILES_FILE.parent.mkdir(parents=True, exist_ok=True)
    atomic_json_write(PROFILES_FILE, {"profiles": profiles})


def get_profile(profile_id: Optional[str]) -> Optional[dict]:
    """Retrieve a single Connector Profile by ID."""
    if not profile_id:
        return None
    for p in get_profiles():
        if p.get("id") == profile_id:
            return p
    return None


def is_module_allowed(module_id: str, profile_id: Optional[str] = None) -> tuple[bool, str]:
    """
    Check if a connector module is globally enabled AND permitted by the active profile.
    Returns (allowed: bool, reason: str).
    """
    registry = get_registry()
    mod = next((m for m in registry.get("modules", []) if m.get("id") == module_id), None)
    if not mod:
        return False, f"Connector '{module_id}' not found in registry."
    if not mod.get("enabled", True):
        return False, f"Connector '{mod.get('name', module_id)}' is globally disabled in the Connectors Library."

    if profile_id:
        prof = get_profile(profile_id)
        if prof is not None:
            allowed = prof.get("allowed_connectors", [])
            if module_id not in allowed:
                return (
                    False,
                    f"Connector '{mod.get('name', module_id)}' is blocked by active profile '{prof.get('name', profile_id)}'."
                )
    return True, "OK"


def set_module_enabled(module_id: str, enabled: bool) -> Optional[dict]:
    """Toggle global enabled state of a connector module."""
    registry = get_registry()
    updated = None
    for mod in registry.get("modules", []):
        if mod["id"] == module_id:
            mod["enabled"] = bool(enabled)
            updated = mod
            break
    if updated is not None:
        save_registry(registry)
    return updated


def update_auth_state(module_id: str, is_authorized: bool):
    """Updates the authorization state of a module."""
    registry = get_registry()
    for mod in registry.get("modules", []):
        if mod["id"] == module_id:
            mod["is_authorized"] = is_authorized
            break
    save_registry(registry)


def _inject_saved_settings(module_id: str, args: dict) -> dict:
    """Populate default arguments from saved connector settings if not explicitly provided."""
    merged = dict(args or {})
    try:
        from core.workspace.preferences_manager import get_preferences_manager
        pm = get_preferences_manager()
        nexus_cfg = pm.get("nexus", {}).get(module_id, {})
        if isinstance(nexus_cfg, dict):
            if module_id in ("screen_capture", "screen_ocr") and "monitor" not in merged and nexus_cfg.get("default_monitor") is not None:
                merged["monitor"] = nexus_cfg.get("default_monitor")
            elif module_id == "webcam_capture" and "index" not in merged and nexus_cfg.get("default_camera_index") is not None:
                merged["index"] = nexus_cfg.get("default_camera_index")
            elif module_id == "reddit" and "subreddit" not in merged and nexus_cfg.get("default_subreddit"):
                merged["subreddit"] = nexus_cfg.get("default_subreddit")
            elif module_id == "weather_link" and "location" not in merged and nexus_cfg.get("default_location"):
                merged["location"] = nexus_cfg.get("default_location")
            elif module_id == "git_link" and "repo_path" not in merged and nexus_cfg.get("default_repo_path"):
                merged["repo_path"] = nexus_cfg.get("default_repo_path")
            merged.setdefault("settings", nexus_cfg)
    except Exception:
        pass
    return merged


def call_module(module_id: str, command: str = "", args: dict = None, profile_id: Optional[str] = None) -> str:
    """
    Dynamically loads a Bridge/Connector module and calls a command.
    Includes profile permission checks and an execution sandbox to catch errors.
    """
    if args is None:
        args = {}

    registry = get_registry()
    module_info = next((m for m in registry.get("modules", []) if m["id"] == module_id), None)

    if not module_info:
        return f"Bridge Error: Module '{module_id}' not found in registry."

    allowed, reason = is_module_allowed(module_id, profile_id)
    if not allowed:
        return f"Bridge Blocked: {reason}"

    if not command:
        command = module_info.get("default_command") or next(iter(module_info.get("available_commands", {})), "")

    module_path = module_info.get("module_path")
    if not module_path:
        return f"Bridge Error: Module '{module_id}' has no module_path defined."

    _ALLOWED_PREFIX = "core.bridges."
    if not module_path.startswith(_ALLOWED_PREFIX):
        logger.error(
            f"Bridge Security: Refusing to import '{module_path}' — "
            f"only '{_ALLOWED_PREFIX}*' modules are permitted."
        )
        return (
            f"Bridge Error: Module '{module_id}' has an invalid module_path "
            f"(must be within core.bridges)."
        )

    if not command or command.startswith("_"):
        logger.error(
            f"Bridge Security: Refusing command '{command}' — "
            "commands must not start with an underscore."
        )
        return f"Bridge Error: Invalid command '{command}'."

    try:
        module = importlib.import_module(module_path)
        func = getattr(module, command, None)
        if not func:
            return f"Bridge Error: Command '{command}' not found in module '{module_id}'."

        merged_args = _inject_saved_settings(module_id, args)
        result = func(merged_args)
        return str(result)

    except Exception as e:
        logger.error(f"Bridge Sandbox Error ({module_id}.{command}): {e}", exc_info=True)
        return f"Bridge Error: {module_id} failed. {str(e)}"


def parse_and_execute_slash_commands(message: str, profile_id: Optional[str] = None) -> dict:
    """
    Scan user message for connector slash commands (e.g. '/screen_capture', '/ocr', '/window',
    '/clipboard', '/git', '/processes', '/read_url', '/youtube', '/remind', '/weather', '/reddit').
    Executes matching connectors and returns context + attachments.
    """
    if not message or "/" not in message:
        return {"triggered": False, "results": [], "cleaned_message": message, "attachments": []}

    registry = get_registry()
    modules = registry.get("modules", [])

    # Build lookup by slash_command and /<module_id>
    slash_map: dict[str, dict] = {}
    for mod in modules:
        sc = (mod.get("slash_command") or "").strip().lower()
        if sc:
            slash_map[sc] = mod
        slash_map[f"/{mod['id'].lower()}"] = mod

    # Friendly aliases
    if "/screen_capture" in slash_map:
        slash_map["/screenshot"] = slash_map["/screen_capture"]
        slash_map["/screen"] = slash_map["/screen_capture"]
    if "/clipboard" in slash_map:
        slash_map["/clip"] = slash_map["/clipboard"]
    if "/read_url" in slash_map:
        slash_map["/url"] = slash_map["/read_url"]
    if "/youtube" in slash_map:
        slash_map["/yt"] = slash_map["/youtube"]
    if "/remind" in slash_map:
        slash_map["/tasks"] = slash_map["/remind"]
        slash_map["/todo"] = slash_map["/remind"]
    if "/processes" in slash_map:
        slash_map["/gpu"] = slash_map["/processes"]

    tokens = message.strip().split()
    if not tokens:
        return {"triggered": False, "results": [], "cleaned_message": message, "attachments": []}

    triggered_results = []
    raw_outputs = []
    remaining_prompt = message

    # Check if message starts with a slash command or contains an explicit /command token
    first_tok = tokens[0].lower()
    matched_mod = slash_map.get(first_tok)
    arg_text = ""

    if matched_mod:
        rest = message.strip()[len(tokens[0]):].strip()
        arg_text = rest
        remaining_prompt = rest
    else:
        # Check inline slash command anywhere in message
        for tok in tokens:
            t_low = tok.lower()
            if t_low in slash_map:
                matched_mod = slash_map[t_low]
                remaining_prompt = message.replace(tok, "", 1).strip()
                arg_text = remaining_prompt
                break

    if not matched_mod:
        return {"triggered": False, "results": [], "cleaned_message": message, "attachments": []}

    mod_id = matched_mod["id"]
    cmd = matched_mod.get("default_command") or next(iter(matched_mod.get("available_commands", {})), "")
    args: dict = {}

    # Smart argument extraction for specific connectors
    if mod_id == "web_search" and arg_text:
        args["query"] = arg_text
    elif mod_id == "weather_link" and arg_text:
        args["location"] = arg_text.split("?")[0].strip()[:40]
    elif mod_id == "reddit" and arg_text:
        first_arg = arg_text.split()[0].lstrip("r/")
        if len(arg_text.split()) == 1:
            args["subreddit"] = first_arg
        else:
            args["query"] = arg_text
            cmd = "search_reddit"
    elif mod_id in ("screen_capture", "screen_ocr") and arg_text:
        m = re.match(r"^monitor\s*(\d+)\b|^(\d+)\b", arg_text.strip(), re.IGNORECASE)
        if m:
            mon_num = m.group(1) or m.group(2)
            args["monitor"] = int(mon_num)
    elif mod_id == "git_link" and arg_text:
        low_arg = arg_text.lower()
        if "diff" in low_arg or "review" in low_arg or "changes" in low_arg:
            cmd = "get_diff"
        elif "log" in low_arg or "commits" in low_arg or "history" in low_arg:
            cmd = "get_log"
        else:
            cmd = "get_status"
    elif mod_id == "webpage_reader" and arg_text:
        args["url"] = arg_text
    elif mod_id == "youtube_link" and arg_text:
        args["url"] = arg_text
    elif mod_id == "companion_tasks":
        if not arg_text or arg_text.lower() in ("list", "show", "tasks", "status"):
            cmd = "list_tasks"
        elif arg_text.lower().startswith(("done ", "complete ", "finish ")):
            cmd = "complete_task"
            args["text"] = arg_text.split(None, 1)[1] if len(arg_text.split()) > 1 else ""
        else:
            cmd = "add_task"
            args["text"] = arg_text

    output = call_module(mod_id, cmd, args, profile_id=profile_id)
    raw_outputs.append(output)
    triggered_results.append({
        "module_id": mod_id,
        "name": matched_mod.get("name", mod_id),
        "command": cmd,
        "output": output
    })

    # Extract any screenshot/webcam attachments
    attachments = []
    captures = []
    try:
        from core.companions.engine.tools import extract_peripheral_captures
        captures, attachments = extract_peripheral_captures(raw_outputs, [])
    except Exception as e:
        logger.warning(f"Failed to extract peripheral captures from slash command: {e}")

    return {
        "triggered": True,
        "results": triggered_results,
        "raw_outputs": raw_outputs,
        "cleaned_message": remaining_prompt or f"Analyze the result from {matched_mod.get('name', mod_id)}.",
        "attachments": attachments,
        "captures": captures,
    }
