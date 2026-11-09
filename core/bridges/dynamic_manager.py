"""
core/bridges/dynamic_manager.py
Dynamic Realtime Connector Incubator & Non-Destructive Evolution Engine.
Enables companions (and users) to create, test, use, and collaboratively upgrade
realtime connectors with backward-compatibility checks and telemetry.
"""
from __future__ import annotations
import ast
import importlib.util
import inspect
import json
import re
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.utils import get_logger, load_json, atomic_json_write, utcnow_iso
from core.utils.paths import DYNAMIC_CONNECTORS, _PROJECT

logger = get_logger(__name__)

# Disallowed ast calls/attributes for sandbox safety
FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__"}
FORBIDDEN_ATTRIBUTES = {
    "rmtree", "unlink", "remove", "system", "popen", "spawn",
    "call", "check_call", "check_output"
}


def ensure_dynamic_dir() -> Path:
    DYNAMIC_CONNECTORS.mkdir(parents=True, exist_ok=True)
    return DYNAMIC_CONNECTORS


def validate_code_safety(code: str) -> Tuple[bool, str]:
    """
    Perform AST inspection on Python code to prevent destructive actions,
    arbitrary string evaluation, or raw shell tampering.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"Python SyntaxError: {e.msg} at line {e.lineno}"

    for node in ast.walk(tree):
        # 1. Block forbidden direct function calls (eval, exec, compile)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
                return False, f"Security Violation: '{node.func.id}()' is strictly prohibited in dynamic tools."
            if isinstance(node.func, ast.Attribute):
                attr_name = node.func.attr
                # Block raw destructive functions: os.system, shutil.rmtree, etc.
                if attr_name in FORBIDDEN_ATTRIBUTES:
                    # Allow safe Path.unlink if local or scoped, but block os.system, subprocess calls, shutil.rmtree
                    if isinstance(node.func.value, ast.Name) and node.func.value.id in ("os", "subprocess", "shutil"):
                        return False, f"Security Violation: Destructive call '{node.func.value.id}.{attr_name}()' is prohibited."

        # 2. Block direct dunder access to globals or builtins
        if isinstance(node, ast.Attribute):
            if node.attr in ("__subclasses__", "__globals__", "__builtins__"):
                return False, f"Security Violation: Access to '{node.attr}' is prohibited."

    return True, "OK"


def _tool_dir(tool_id: str) -> Path:
    return ensure_dynamic_dir() / tool_id


def _meta_path(tool_id: str) -> Path:
    return _tool_dir(tool_id) / "meta.json"


def _active_path(tool_id: str) -> Path:
    return _tool_dir(tool_id) / "active.py"


def _load_meta(tool_id: str) -> Optional[Dict[str, Any]]:
    p = _meta_path(tool_id)
    if not p.exists():
        return None
    return load_json(p, default=None)


def _save_meta(tool_id: str, meta: Dict[str, Any]) -> None:
    _tool_dir(tool_id).mkdir(parents=True, exist_ok=True)
    atomic_json_write(_meta_path(tool_id), meta)


def _load_module_from_file(file_path: Path, module_name: str) -> Any:
    """Dynamically import a Python file into an isolated module object."""
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if not spec or not spec.loader:
        raise ImportError(f"Could not load spec for {file_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_module_from_code(code: str, module_name: str) -> Any:
    """Execute code string inside an isolated module object."""
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(module_name, loader=None))
    sys.modules[module_name] = mod
    exec(code, mod.__dict__)
    return mod


def _run_test_case(mod: Any, tc: Dict[str, Any]) -> Tuple[bool, str]:
    """Execute a single test case against a module."""
    cmd = tc.get("command", "")
    args = tc.get("args", {})
    expected = tc.get("expected_substring", "")

    func = getattr(mod, cmd, None)
    if not func or not callable(func):
        return False, f"Command '{cmd}' not found or not callable in module."

    try:
        # Check signature
        sig = inspect.signature(func)
        if len(sig.parameters) == 0:
            res = func()
        else:
            res = func(args)

        res_str = str(res)
        if expected and expected.lower() not in res_str.lower():
            return False, f"Test output did not contain expected substring '{expected}'. Got: {res_str[:200]}"
        return True, res_str
    except Exception as e:
        return False, f"Exception during test execution: {e}"


def list_dynamic_tools() -> List[Dict[str, Any]]:
    """List all dynamic realtime connectors with versions and telemetry."""
    base = ensure_dynamic_dir()
    init_sample_dynamic_tools()
    tools = []
    for p in base.iterdir():
        if p.is_dir():
            meta = _load_meta(p.name)
            if meta:
                # Compute utility & promotion readiness
                tel = meta.setdefault("telemetry", {
                    "call_count": 0, "success_count": 0, "error_count": 0,
                    "last_called": None, "last_error": None
                })
                calls = tel.get("call_count", 0)
                succ = tel.get("success_count", 0)
                rate = (succ / calls * 100.0) if calls > 0 else 100.0
                meta["success_rate"] = round(rate, 1)

                collabs = meta.get("collaborators", [])
                meta["collaborators_count"] = len(collabs)

                # Qualification for Native Promotion:
                # 3+ calls, >= 85% success rate, or marked manually
                meta["ready_for_native"] = bool(
                    meta.get("status") != "promoted" and
                    calls >= 3 and rate >= 85.0
                )
                tools.append(meta)

    tools.sort(key=lambda t: t.get("updated_at") or t.get("created_at") or "", reverse=True)
    return tools


def get_dynamic_tool(tool_id: str) -> Optional[Dict[str, Any]]:
    """Get full details of a dynamic tool including active code and changelog."""
    meta = _load_meta(tool_id)
    if not meta:
        return None
    act_p = _active_path(tool_id)
    active_code = act_p.read_text(encoding="utf-8") if act_p.exists() else ""
    meta["active_code"] = active_code

    # Include available commands
    try:
        mod = _load_module_from_file(act_p, f"dyn_{tool_id}")
        commands = {}
        for name in dir(mod):
            if not name.startswith("_"):
                val = getattr(mod, name)
                if callable(val):
                    commands[name] = inspect.getdoc(val) or f"Execute '{name}'"
        meta["commands"] = commands
    except Exception as e:
        meta["commands"] = {}
        logger.debug(f"Could not inspect commands for {tool_id}: {e}")

    # Check for pending proposals
    props_dir = _tool_dir(tool_id) / "proposals"
    proposals = []
    if props_dir.exists():
        for prop_p in props_dir.glob("*.json"):
            p_data = load_json(prop_p, default=None)
            if p_data:
                proposals.append(p_data)
    meta["proposals"] = proposals

    return meta


def create_dynamic_tool(
    tool_id: str,
    name: str,
    description: str,
    code: str,
    author: str = "misakacipher",
    category: str = "custom",
    icon: str = "fas fa-wrench",
    test_cases: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Create a new dynamic realtime connector.
    Validates AST safety, runs initial test cases, and registers v1.0.0.
    """
    clean_id = re.sub(r"[^a-z0-9_]", "", tool_id.lower().strip())
    if not clean_id or len(clean_id) < 3:
        return {"success": False, "error": "Tool ID must be at least 3 alphanumeric/underscore characters."}

    # Verify AST safety
    safe, reason = validate_code_safety(code)
    if not safe:
        return {"success": False, "error": reason}

    # Verify test cases
    t_cases = test_cases or []
    if t_cases:
        try:
            temp_mod = _load_module_from_code(code, f"dyn_test_{clean_id}")
            for idx, tc in enumerate(t_cases):
                ok, err = _run_test_case(temp_mod, tc)
                if not ok:
                    return {"success": False, "error": f"Initial test case #{idx + 1} failed: {err}"}
        except Exception as e:
            return {"success": False, "error": f"Failed compiling or testing dynamic code: {e}"}

    tdir = _tool_dir(clean_id)
    tdir.mkdir(parents=True, exist_ok=True)

    v1_path = tdir / "v1_0_0.py"
    v1_path.write_text(code, encoding="utf-8")

    act_path = _active_path(clean_id)
    act_path.write_text(code, encoding="utf-8")

    now_iso = utcnow_iso()
    meta = {
        "id": clean_id,
        "name": name.strip() or clean_id.replace("_", " ").title(),
        "description": description.strip() or "Dynamic companion connector.",
        "author": author.strip(),
        "category": category,
        "icon": icon,
        "version": "1.0.0",
        "created_at": now_iso,
        "updated_at": now_iso,
        "status": "incubating",
        "collaborators": [author.strip()],
        "changelog": [
            {
                "version": "1.0.0",
                "author": author.strip(),
                "summary": "Initial dynamic connector creation.",
                "timestamp": now_iso,
            }
        ],
        "test_cases": t_cases,
        "telemetry": {
            "call_count": 0,
            "success_count": 0,
            "error_count": 0,
            "last_called": None,
            "last_error": None,
        },
        "versions": ["1.0.0"],
    }
    _save_meta(clean_id, meta)
    logger.info(f"Created dynamic connector '{clean_id}' v1.0.0 by {author}")
    return {"success": True, "tool": meta}


def propose_update(
    tool_id: str,
    new_code: str,
    change_summary: str,
    author: str = "ruiko_saten",
    new_version: Optional[str] = None,
    new_test_cases: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Non-Destructive Evolution Protocol:
    1. Validates AST safety.
    2. Runs ALL existing test cases against the new code.
    3. If existing tests break: preserves active.py completely and records as a proposal for review.
    4. If all tests pass: bumps version, activates new_code, adds author to collaborators, logs changelog.
    """
    clean_id = tool_id.lower().strip()
    meta = _load_meta(clean_id)
    if not meta:
        return {"success": False, "error": f"Dynamic connector '{clean_id}' not found."}

    # 1. AST Safety
    safe, reason = validate_code_safety(new_code)
    if not safe:
        return {"success": False, "error": reason}

    # 2. Test execution of all existing test cases on the new code
    existing_tests = meta.get("test_cases", [])
    failed_test_msg = None
    try:
        temp_mod = _load_module_from_code(new_code, f"dyn_upgrade_test_{clean_id}")
        for idx, tc in enumerate(existing_tests):
            ok, err = _run_test_case(temp_mod, tc)
            if not ok:
                failed_test_msg = f"Test case #{idx + 1} ('{tc.get('command')}') failed: {err}"
                break

        # Also test new test cases if provided
        if not failed_test_msg and new_test_cases:
            for idx, tc in enumerate(new_test_cases):
                ok, err = _run_test_case(temp_mod, tc)
                if not ok:
                    failed_test_msg = f"New test case #{idx + 1} ('{tc.get('command')}') failed: {err}"
                    break
    except Exception as e:
        failed_test_msg = f"Crash during module test execution: {e}"

    now_iso = utcnow_iso()

    # 3. IF TESTS FAILED: Save as Proposal without breaking active version!
    if failed_test_msg:
        logger.warning(f"Dynamic tool '{clean_id}' update by {author} failed verification: {failed_test_msg}. Saving proposal.")
        props_dir = _tool_dir(clean_id) / "proposals"
        props_dir.mkdir(parents=True, exist_ok=True)
        prop_id = f"prop_{author}_{now_iso[:19].replace(':', '-')}"
        prop_meta = {
            "proposal_id": prop_id,
            "tool_id": clean_id,
            "author": author,
            "change_summary": change_summary,
            "created_at": now_iso,
            "failed_reason": failed_test_msg,
            "code": new_code,
            "new_test_cases": new_test_cases or [],
        }
        atomic_json_write(props_dir / f"{prop_id}.json", prop_meta)
        return {
            "success": False,
            "status": "proposal_saved",
            "proposal_id": prop_id,
            "message": (
                f"Backward compatibility check failed ({failed_test_msg}). "
                "The change was safely saved as a proposal without breaking the working version."
            ),
            "failed_test": failed_test_msg,
        }

    # 4. IF TESTS PASSED: Auto-upgrade!
    cur_ver = meta.get("version", "1.0.0")
    if new_version:
        target_ver = new_version
    else:
        # Bump minor version (e.g. 1.0.0 -> 1.1.0)
        parts = cur_ver.split(".")
        try:
            major = int(parts[0])
            minor = int(parts[1]) if len(parts) > 1 else 0
            target_ver = f"{major}.{minor + 1}.0"
        except Exception:
            target_ver = f"{cur_ver}.1"

    # Save versioned file
    ver_clean = target_ver.replace(".", "_")
    ver_path = _tool_dir(clean_id) / f"v{ver_clean}.py"
    ver_path.write_text(new_code, encoding="utf-8")

    # Update active.py
    _active_path(clean_id).write_text(new_code, encoding="utf-8")

    # Update metadata
    meta["version"] = target_ver
    meta["updated_at"] = now_iso
    collabs = meta.setdefault("collaborators", [])
    if author not in collabs:
        collabs.append(author)

    versions = meta.setdefault("versions", [])
    if target_ver not in versions:
        versions.append(target_ver)

    if new_test_cases:
        existing_tests.extend(new_test_cases)
        meta["test_cases"] = existing_tests

    changelog = meta.setdefault("changelog", [])
    changelog.append({
        "version": target_ver,
        "author": author,
        "summary": change_summary.strip() or f"Upgrade to {target_ver}",
        "timestamp": now_iso,
    })

    _save_meta(clean_id, meta)
    logger.info(f"Dynamic connector '{clean_id}' successfully upgraded to v{target_ver} by {author}")
    return {
        "success": True,
        "status": "upgraded",
        "version": target_ver,
        "message": f"Successfully upgraded '{clean_id}' to v{target_ver} (backward compatibility verified).",
    }


def execute_dynamic_tool(
    tool_id: str,
    command: str,
    args: Optional[Dict[str, Any]] = None,
    profile_id: Optional[str] = None,
) -> str:
    """
    Execute a dynamic connector's command with automatic fallback to previous stable version
    if the latest active version raises an unhandled exception.
    """
    clean_id = tool_id.lower().strip()
    meta = _load_meta(clean_id)
    if not meta:
        return f"[dynamic_tool ERROR] Dynamic connector '{clean_id}' not found."

    tel = meta.setdefault("telemetry", {
        "call_count": 0, "success_count": 0, "error_count": 0,
        "last_called": None, "last_error": None
    })
    tel["call_count"] = tel.get("call_count", 0) + 1
    tel["last_called"] = utcnow_iso()

    act_p = _active_path(clean_id)
    if not act_p.exists():
        tel["error_count"] = tel.get("error_count", 0) + 1
        _save_meta(clean_id, meta)
        return f"[dynamic_tool ERROR] Active script for '{clean_id}' is missing."

    # Try executing active version
    try:
        mod = _load_module_from_file(act_p, f"dyn_live_{clean_id}")
        func = getattr(mod, command, None)
        if not func or not callable(func):
            # Fallback to default if only 1 command exists
            callables = [f for f in dir(mod) if not f.startswith("_") and callable(getattr(mod, f))]
            if len(callables) == 1:
                func = getattr(mod, callables[0])
            else:
                tel["error_count"] = tel.get("error_count", 0) + 1
                _save_meta(clean_id, meta)
                return f"[dynamic_tool ERROR] Command '{command}' not found on '{clean_id}'."

        sig = inspect.signature(func)
        result = func() if len(sig.parameters) == 0 else func(args or {})
        tel["success_count"] = tel.get("success_count", 0) + 1
        _save_meta(clean_id, meta)
        return str(result)
    except Exception as exc:
        err_msg = str(exc)
        tel["error_count"] = tel.get("error_count", 0) + 1
        tel["last_error"] = err_msg
        logger.error(f"Dynamic tool '{clean_id}' failed active execution: {exc}")

        # AUTOMATIC FALLBACK: Check if previous stable version exists!
        versions = meta.get("versions", [])
        if len(versions) >= 2:
            prev_ver = versions[-2].replace(".", "_")
            prev_p = _tool_dir(clean_id) / f"v{prev_ver}.py"
            if prev_p.exists():
                try:
                    logger.warning(f"Attempting automatic fallback to v{versions[-2]} for '{clean_id}'")
                    mod_fallback = _load_module_from_file(prev_p, f"dyn_fallback_{clean_id}")
                    func_fb = getattr(mod_fallback, command, None)
                    if func_fb and callable(func_fb):
                        sig = inspect.signature(func_fb)
                        fb_res = func_fb() if len(sig.parameters) == 0 else func_fb(args or {})
                        _save_meta(clean_id, meta)
                        return (
                            f"[Notice: Active version v{meta.get('version')} failed ({err_msg}); "
                            f"automatically fell back to stable v{versions[-2]}]\n{fb_res}"
                        )
                except Exception as fb_exc:
                    logger.error(f"Fallback to previous version also failed: {fb_exc}")

        _save_meta(clean_id, meta)
        return f"[dynamic_tool ERROR ({clean_id}.{command})] {err_msg}"


def promote_to_native(tool_id: str) -> Dict[str, Any]:
    """
    Promote an incubating dynamic connector into a permanent Native Suite bridge module!
    1. Writes code to core/bridges/{tool_id}_bridge.py
    2. Registers in core/bridges/registry.json
    3. Adds to bridge_manager.py default profiles
    4. Sets status = 'promoted' in dynamic meta.json
    """
    clean_id = tool_id.lower().strip()
    meta = _load_meta(clean_id)
    if not meta:
        return {"success": False, "error": f"Dynamic connector '{clean_id}' not found."}

    act_p = _active_path(clean_id)
    if not act_p.exists():
        return {"success": False, "error": "Active implementation script is missing."}

    code = act_p.read_text(encoding="utf-8")

    # 1. Write to core/bridges/{clean_id}_bridge.py
    native_path = _PROJECT / "core" / "bridges" / f"{clean_id}_bridge.py"
    native_code = (
        f'"""\ncore/bridges/{clean_id}_bridge.py\n'
        f'{meta.get("name")} — Native Suite Bridge.\n'
        f'Originally incubated by {meta.get("author")} and collaborators ({", ".join(meta.get("collaborators", []))}).\n'
        f'Promoted to Native Suite on {utcnow_iso()[:10]}.\n"""\n\n'
        + code
    )
    native_path.write_text(native_code, encoding="utf-8")

    # 2. Register in core/bridges/registry.json
    reg_path = _PROJECT / "core" / "bridges" / "registry.json"
    registry = load_json(reg_path, default={"modules": []})
    modules = registry.get("modules", [])

    # Inspect commands from active file
    available_commands = {}
    default_cmd = ""
    try:
        mod = _load_module_from_file(act_p, f"dyn_prom_{clean_id}")
        for name in dir(mod):
            if not name.startswith("_"):
                val = getattr(mod, name)
                if callable(val):
                    doc = inspect.getdoc(val) or f"Execute {name}"
                    available_commands[name] = doc
                    if not default_cmd:
                        default_cmd = name
    except Exception:
        pass

    if not default_cmd:
        default_cmd = next(iter(available_commands), "run")

    existing_mod = next((m for m in modules if m["id"] == clean_id), None)
    native_module_def = {
        "id": clean_id,
        "name": meta.get("name", clean_id.title()),
        "description": meta.get("description", "Promoted native connector."),
        "module_path": f"core.bridges.{clean_id}_bridge",
        "category": meta.get("category", "system"),
        "privacy_tier": "local_sensitive",
        "icon": meta.get("icon", "fas fa-plug"),
        "slash_command": f"/{clean_id}",
        "default_command": default_cmd,
        "enabled": True,
        "requires_auth": False,
        "is_authorized": True,
        "available_commands": available_commands,
        "settings": []
    }

    if existing_mod:
        existing_mod.update(native_module_def)
    else:
        modules.append(native_module_def)

    registry["modules"] = modules
    atomic_json_write(reg_path, registry)

    # 3. Update dynamic meta
    meta["status"] = "promoted"
    meta["promoted_at"] = utcnow_iso()
    meta["native_module_path"] = f"core.bridges.{clean_id}_bridge"
    _save_meta(clean_id, meta)

    logger.info(f"Successfully promoted dynamic connector '{clean_id}' to Native Suite!")
    return {
        "success": True,
        "message": f"Tool '{meta.get('name')}' successfully promoted to Native Suite!",
        "module_id": clean_id,
        "path": str(native_path),
    }


def init_sample_dynamic_tools() -> None:
    """Initialize a sample dynamic connector if the incubator is currently empty."""
    base = ensure_dynamic_dir()
    existing = [d for d in base.iterdir() if d.is_dir() and (d / "meta.json").exists()]
    if existing:
        return

    sample_code = '''"""
Dynamic Bridge: Itch.io Game Jam Radar
Author: misakacipher
Version: 1.0.0
"""
from typing import Dict, Any, Optional

def get_jams(args: Optional[Dict[str, Any]] = None) -> str:
    """Find active and upcoming itch.io game jams with submission deadlines."""
    query = (args or {}).get("query", "retro").lower()

    # Curated live sample jam radar
    jams = [
        {"name": "GMTK Game Jam 2026", "theme": "Built to Scale", "days_left": 4, "entries": 420, "url": "https://itch.io/jam/gmtk-2026"},
        {"name": "Retro AI Cyberpunk Jam", "theme": "Neon & Glitch", "days_left": 12, "entries": 85, "url": "https://itch.io/jam/cyberpunk-2026"},
        {"name": "Mini Jame Gam #42", "theme": "Chain Reactions", "days_left": 2, "entries": 130, "url": "https://itch.io/jam/mini-jame-gam-42"}
    ]

    matched = [j for j in jams if query in j["name"].lower() or query in j["theme"].lower()] or jams
    lines = [f"Found {len(matched)} Game Jam(s) on Radar:"]
    for j in matched:
        lines.append(f"- **{j['name']}** (Theme: *{j['theme']}*) — {j['days_left']} days left ({j['entries']} joined) -> {j['url']}")
    return "\\n".join(lines)
'''
    create_dynamic_tool(
        tool_id="game_jam_radar",
        name="Itch.io Game Jam Radar",
        description="Tracks ongoing game jams, themes, submission deadlines, and community participation.",
        code=sample_code,
        author="misakacipher",
        category="web",
        icon="fas fa-gamepad",
        test_cases=[
            {
                "command": "get_jams",
                "args": {"query": "retro"},
                "expected_substring": "Game Jam",
            }
        ],
    )

