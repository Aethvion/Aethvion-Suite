"""
core/modelhub/registry.py
The list of model endpoints the Suite can call, whatever they are.

Endpoints come from two places:

  Built-in (discovered at call time, nothing to configure)
      llm:<model>      every chat model in the model registry           text.generate, image.analyze
      image:<model>    the Image tab's backends (local / SD WebUI / cloud)   image.generate, image.edit
      3d:<model>       the 3D tab's local worker models                 mesh.generate
      demo:*           placeholder generators that need no model at all (for trying pipelines)

  Custom (JSON files in data/config/model_endpoints/<id>.json)
      adapter "http"     any HTTP API — local server or hosted service
      adapter "command"  any command-line tool — Blender, a Python script, an .exe

See docs/modelhub/overview.md for the endpoint file format.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from core.utils import atomic_json_write, load_json
from core.utils.logger import get_logger
from core.utils.paths import CONFIG, LOCAL_MODELS_3D, LOCAL_MODELS_IMAGE, MODEL_REGISTRY, SUGGESTED_IMAGE_MODELS

from .capabilities import CAPABILITIES, is_capability

logger = get_logger(__name__)

ENDPOINTS_DIR = CONFIG / "model_endpoints"
TEMPLATES_DIR = Path(__file__).parent.parent / "config" / "model_endpoints"

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{1,62}$")
_BUILTIN_PREFIXES = ("llm:", "image:", "3d:", "demo:")

# Folder name under localmodels/3d  ->  model id used by the 3D tab
_KNOWN_3D = {"trellis2": "trellis-2", "triposr": "triposr", "crm": "crm"}


def _ep(id: str, name: str, adapter: str, capabilities: list[str], *, description: str = "",
        available: bool = True, reason: str = "", builtin: bool = True, group: str = "",
        params: Optional[list] = None, raw: Optional[dict] = None) -> dict:
    return {
        "id": id, "name": name, "adapter": adapter, "capabilities": capabilities,
        "description": description, "available": available, "reason": reason,
        "builtin": builtin, "group": group or adapter, "params": params or [],
        **({"definition": raw} if raw is not None else {}),
    }


# Built-in discovery

def _llm_endpoints() -> list[dict]:
    out: list[dict] = []
    reg = load_json(MODEL_REGISTRY, default={}) or {}
    for prov_id, prov in (reg.get("providers") or {}).items():
        if not prov.get("active", False):
            continue
        for model_id, mdata in (prov.get("models") or {}).items():
            caps = [str(c).upper() for c in mdata.get("capabilities", [])]
            if "CHAT" not in caps:
                continue
            out.append(_ep(
                f"llm:{model_id}", model_id, "llm", ["text.generate", "image.analyze"],
                description=mdata.get("description", "") or f"{prov.get('name', prov_id)} chat model",
                group=prov.get("name", prov_id),
            ))
    try:
        from core.automate.automate_routes import _get_installed_local_models  # noqa: PLC0415
        seen = {e["id"] for e in out}
        for m in _get_installed_local_models():
            eid = f"llm:{m['id']}"
            if eid not in seen:
                out.append(_ep(eid, m["label"], "llm", ["text.generate"],
                               description=f"Installed offline model ({m['provider']})", group="Local"))
    except Exception as exc:  # noqa: BLE001 — discovery must never break listing
        logger.debug("modelhub: local LLM discovery skipped: %s", exc)
    return out


def _image_endpoints() -> list[dict]:
    out: list[dict] = []
    caps = ["image.generate", "image.edit"]

    suggested = (load_json(SUGGESTED_IMAGE_MODELS, default={}) or {}).get("image_models", [])
    known_files: set[str] = set()
    for m in suggested:
        fn = m.get("filename") or ""
        if fn and (LOCAL_MODELS_IMAGE / fn).exists():
            known_files.add(fn.lower())
            out.append(_ep(f"image:{m.get('id', fn)}", m.get("name", fn), "suite-image", caps,
                           description="Local checkpoint (native GPU engine)", group="Local image"))
    if LOCAL_MODELS_IMAGE.exists():
        for f in sorted(LOCAL_MODELS_IMAGE.glob("*")):
            if f.is_file() and f.suffix.lower() in (".safetensors", ".ckpt") and f.name.lower() not in known_files:
                out.append(_ep(f"image:local:{f.name}", f.stem, "suite-image", caps,
                               description="Custom local checkpoint", group="Local image"))

    active: set[str] = set()
    reg = load_json(MODEL_REGISTRY, default={}) or {}
    for prov_id, prov in (reg.get("providers") or {}).items():
        if prov.get("active", False):
            active.add(prov_id)
            for model_id, mdata in (prov.get("models") or {}).items():
                mcaps = [str(c).upper() for c in mdata.get("capabilities", [])]
                if "IMAGE" in mcaps or "IMAGE_GENERATION" in mcaps:
                    out.append(_ep(f"image:{model_id}", model_id, "suite-image", ["image.generate"],
                                   description=mdata.get("description", ""), group=prov.get("name", prov_id)))
    seen = {e["id"] for e in out}
    cloud_defaults = [("google_ai", "imagen-3.0-generate-002", "Google Imagen 3"),
                      ("openai",    "dall-e-3",                "OpenAI DALL·E 3")]
    for prov_id, model_id, label in cloud_defaults:
        if prov_id in active and f"image:{model_id}" not in seen:
            out.append(_ep(f"image:{model_id}", label, "suite-image", ["image.generate"],
                           description="Cloud image model via the configured provider key",
                           group="Cloud image"))
    return out


def _3d_endpoints() -> list[dict]:
    out: list[dict] = []
    dirs: dict[str, Path] = {}
    if LOCAL_MODELS_3D.exists():
        dirs = {d.name: d for d in LOCAL_MODELS_3D.iterdir() if d.is_dir()}
    names = sorted(set(_KNOWN_3D) | set(dirs))
    for folder in names:
        model_id = _KNOWN_3D.get(folder, folder)
        d = dirs.get(folder)
        installed = bool(d and (d / "venv").exists() and (d / "run_server.py").exists())
        out.append(_ep(
            f"3d:{model_id}", model_id, "suite-3d", ["mesh.generate"],
            description="Local 3D generation worker (3D tab)",
            available=installed,
            reason="" if installed else "Not installed — install it from the 3D tab.",
            group="Local 3D",
        ))
    return out


def _demo_endpoints() -> list[dict]:
    note = "Placeholder generator — no model involved. Use it to try a pipeline end to end."
    return [
        _ep("demo:image",   "Demo image (placeholder)",   "demo", ["image.generate"], description=note, group="Demo"),
        _ep("demo:mesh",    "Demo mesh (placeholder box)", "demo", ["mesh.generate"],  description=note, group="Demo",
            params=[{"key": "width", "type": "number", "default": 1}, {"key": "height", "type": "number", "default": 1},
                    {"key": "depth", "type": "number", "default": 1}]),
        _ep("demo:texture", "Demo texture (placeholder)",  "demo", ["mesh.texture"],   description=note, group="Demo"),
    ]


# Custom endpoints

def validate_definition(d: Any) -> list[str]:
    """Return a list of problems with a custom endpoint definition (empty = valid)."""
    errs: list[str] = []
    if not isinstance(d, dict):
        return ["Definition must be a JSON object."]
    eid = str(d.get("id", ""))
    if not _ID_RE.match(eid):
        errs.append("id: 2–63 chars, lowercase letters, digits, '-' or '_', starting with a letter or digit.")
    if eid.startswith(tuple(p.rstrip(":") for p in _BUILTIN_PREFIXES)) and ":" in eid:
        errs.append("id must not use a built-in prefix.")
    if not str(d.get("name", "")).strip():
        errs.append("name is required.")
    caps = d.get("capabilities")
    if not isinstance(caps, list) or not caps:
        errs.append("capabilities: list at least one capability.")
    else:
        bad = [c for c in caps if not is_capability(str(c))]
        if bad:
            errs.append(f"Unknown capabilities: {', '.join(map(str, bad))}. Known: {', '.join(CAPABILITIES)}.")
    adapter = d.get("adapter")
    if adapter == "http":
        http = d.get("http")
        if not isinstance(http, dict) or not str(http.get("url", "")).strip():
            errs.append("http.url is required for the http adapter.")
        elif not isinstance(http.get("result", {}), dict):
            errs.append("http.result must be an object.")
    elif adapter == "command":
        cmd = d.get("command")
        if not isinstance(cmd, dict) or not isinstance(cmd.get("args"), list) or not cmd.get("args"):
            errs.append("command.args (a non-empty list) is required for the command adapter.")
    else:
        errs.append("adapter must be 'http' or 'command'.")
    return errs


def _custom_endpoints() -> list[dict]:
    out: list[dict] = []
    if not ENDPOINTS_DIR.exists():
        return out
    for p in sorted(ENDPOINTS_DIR.glob("*.json")):
        d = load_json(p, default=None)
        errs = validate_definition(d)
        if errs:
            logger.warning("modelhub: skipping invalid endpoint file %s: %s", p.name, "; ".join(errs))
            continue
        enabled = d.get("enabled", True) is not False
        reason = "" if enabled else "Disabled."
        available = enabled
        if enabled:
            from .templating import missing_env  # noqa: PLC0415
            miss = missing_env(d.get("http") or d.get("command") or {})
            if miss:
                available, reason = False, f"Missing environment variable(s): {', '.join(miss)} (add to .env)."
        out.append(_ep(d["id"], d["name"], d["adapter"], [str(c) for c in d["capabilities"]],
                       description=d.get("description", ""), available=available, reason=reason,
                       builtin=False, group="Custom", params=d.get("params") or [], raw=d))
    return out


def save_custom(definition: dict) -> dict:
    errs = validate_definition(definition)
    if errs:
        raise ValueError("; ".join(errs))
    ENDPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in definition.items() if k != "template"}
    atomic_json_write(ENDPOINTS_DIR / f"{clean['id']}.json", clean)
    return clean


def delete_custom(endpoint_id: str) -> bool:
    if not _ID_RE.match(endpoint_id):
        return False
    p = ENDPOINTS_DIR / f"{endpoint_id}.json"
    if p.exists():
        p.unlink()
        return True
    return False


def list_templates() -> list[dict]:
    out = []
    if TEMPLATES_DIR.exists():
        for p in sorted(TEMPLATES_DIR.glob("*.json")):
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except ValueError as exc:
                logger.warning("modelhub: bad template %s: %s", p.name, exc)
    return out


# Public listing / lookup

def list_endpoints(capability: str = "", include_unavailable: bool = True,
                   with_definition: bool = False) -> list[dict]:
    eps: list[dict] = []
    for fn in (_custom_endpoints, _3d_endpoints, _image_endpoints, _llm_endpoints, _demo_endpoints):
        try:
            eps.extend(fn())
        except Exception as exc:  # noqa: BLE001
            logger.warning("modelhub: %s failed: %s", fn.__name__, exc)
    if capability:
        eps = [e for e in eps if capability in e["capabilities"]]
    if not include_unavailable:
        eps = [e for e in eps if e["available"]]
    if not with_definition:
        eps = [{k: v for k, v in e.items() if k != "definition"} for e in eps]
    return eps


def resolve(endpoint_id: str, capability: str = "") -> Optional[dict]:
    """Find an endpoint by id.

    Accepts bare model ids for convenience and backward compatibility:
    "imagen-3.0-generate-002" resolves to "image:imagen-3.0-generate-002" when the
    requested capability is an image one, "gpt-4o" to "llm:gpt-4o", and so on.
    """
    endpoint_id = (endpoint_id or "").strip()
    if not endpoint_id:
        return None
    eps = list_endpoints(with_definition=True)
    by_id = {e["id"]: e for e in eps}
    if endpoint_id in by_id:
        return by_id[endpoint_id]

    prefixes = {"image": ["image:"], "mesh": ["3d:"], "text": ["llm:"]}.get(capability.split(".")[0], [])
    for pref in prefixes + ["llm:", "image:", "3d:"]:
        if pref + endpoint_id in by_id:
            return by_id[pref + endpoint_id]

    # Unknown bare id: let the matching built-in adapter try it (new cloud model names etc.)
    if capability.startswith("image."):
        return _ep(f"image:{endpoint_id}", endpoint_id, "suite-image", ["image.generate", "image.edit"])
    if capability in ("text.generate", "image.analyze"):
        return _ep(f"llm:{endpoint_id}", endpoint_id, "llm", ["text.generate", "image.analyze"])
    return None
