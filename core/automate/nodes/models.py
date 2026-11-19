"""
core/automate/nodes/models.py
Nodes that run models through the Model Hub, plus the checks that judge their output.

    model.run          any endpoint, any capability
    model3d.generate   text / image  -> 3D mesh
    model3d.texture    mesh (+ prompt / reference image) -> textured mesh
    mesh.inspect       deterministic facts about a mesh + budget checks
    quality.verify     an AI reviewer scores any output against criteria (quality gate)

Failure convention for these nodes: if the node's `error` port is wired, a failure is
routed there (data ports carry no value, so their branches are skipped).  If it is not
wired, the node fails visibly instead of passing an empty value downstream.
"""
from __future__ import annotations

import io
import json
import uuid
from pathlib import Path
from typing import Any

from ._utils import _to_str, _get_pm


# Shared helpers

def port_wired(ctx, node: dict, port: str) -> bool:
    nid = node.get("id")
    return any(c.get("sourceNodeId") == nid and c.get("sourcePort") == port for c in ctx.connections)


def fail(ctx, node: dict, message: str, data_ports: tuple[str, ...]) -> dict[str, Any]:
    """Route a failure to the error port if wired, otherwise raise so the node shows red."""
    if port_wired(ctx, node, "error"):
        return {**{p: None for p in data_ports}, "error": message}
    raise RuntimeError(message)


def input_wired(ctx, node: dict, port: str) -> bool:
    nid = node.get("id")
    return any(c.get("targetNodeId") == nid and c.get("targetPort") == port for c in ctx.connections)


def require_input(ctx, node: dict, inputs: dict, port: str, what: str, data_ports: tuple[str, ...]):
    """Return the value on *port*, or stop the node the right way when it is missing.

    Wired but empty  -> the upstream step failed or its branch was not taken: skip quietly.
    Not wired at all -> a mistake in the workflow: report it.
    """
    val = inputs.get(port)
    if val not in (None, ""):
        return val
    if input_wired(ctx, node, port):
        from core.automate.executor import NodeSkipped  # noqa: PLC0415
        raise NodeSkipped(f"no {what} arrived from the previous step")
    return fail(ctx, node, f"No {what} connected.", data_ports) and None


def parse_params(*sources: Any) -> dict:
    """Merge parameter sources (dicts or JSON object strings); later sources win."""
    out: dict = {}
    for src in sources:
        if isinstance(src, dict):
            out.update(src)
        elif isinstance(src, str) and src.strip():
            try:
                obj = json.loads(src)
            except ValueError as exc:
                raise ValueError(f"Parameters must be a JSON object: {exc}") from exc
            if not isinstance(obj, dict):
                raise ValueError("Parameters must be a JSON object, e.g. {\"seed\": 42}")
            out.update(obj)
    return out


def _tags(raw: Any) -> list[str]:
    return [t.strip() for t in str(raw or "").split(",") if t.strip()]


def _text_in(inputs: dict, p: dict, port: str, prop: str | None = None) -> str:
    wired = inputs.get(port)
    if wired not in (None, ""):
        return _to_str(wired).strip()
    return str(p.get(prop or port, "") or "").strip()


_DATA_PORTS = ("out", "asset", "text", "path", "url", "all")


def _invoke(node: dict, inputs: dict, ctx, capability: str, *, extra_params: dict | None = None,
            default_endpoint: str | None = None) -> dict[str, Any]:
    from core.modelhub import hub  # noqa: PLC0415

    p = node.get("properties", {})
    endpoint = _text_in(inputs, p, "model", "endpoint") or (default_endpoint or "")
    if not endpoint:
        raise ValueError("No model selected — open the node's properties and pick one.")

    try:
        params = parse_params(extra_params or {}, p.get("params", ""), inputs.get("params"))
    except ValueError as exc:
        return fail(ctx, node, str(exc), _DATA_PORTS)

    result = hub.invoke(
        endpoint, capability,
        prompt=_text_in(inputs, p, "prompt"),
        system_prompt=_text_in(inputs, p, "system_prompt"),
        negative_prompt=_text_in(inputs, p, "negative_prompt"),
        image=inputs.get("image"),
        mesh=inputs.get("mesh"),
        audio=inputs.get("audio"),
        params=params,
        source=ctx.asset_source(node),
        name=str(p.get("name", "") or "").strip(),
        tags=_tags(p.get("tags")),
        cancel=lambda: ctx.cancelled,
        log=lambda m: ctx._info(f"    {m}"),
    )
    if not result.ok:
        return fail(ctx, node, result.error, _DATA_PORTS)

    refs = result.refs
    first = refs[0] if refs else None
    return {
        "out":   first if first else result.text,
        "asset": first,
        "text":  result.text or None,
        "path":  first["path"] if first else None,
        "url":   first["url"] if first else None,
        "all":   refs or None,
        "error": "",
    }


# model.run — universal

def model_run(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p = node.get("properties", {})
    capability = str(p.get("capability", "") or "").strip()
    if capability in ("auto", "(auto)"):
        capability = ""
    return _invoke(node, inputs, ctx, capability)


# model3d.generate / model3d.texture

def _seed_param(p: dict) -> dict:
    raw = str(p.get("seed", "") or "").strip()
    try:
        return {"seed": int(raw)} if raw else {}
    except ValueError:
        return {}


def model3d_generate(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    out = _invoke(node, inputs, ctx, "mesh.generate", extra_params=_seed_param(node.get("properties", {})))
    out["mesh"] = out.get("asset")
    return out


def model3d_texture(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    if require_input(ctx, node, inputs, "mesh", "mesh", _DATA_PORTS + ("mesh",)) is None:
        return {**{p: None for p in _DATA_PORTS + ("mesh",)}, "error": "No mesh connected."}
    out = _invoke(node, inputs, ctx, "mesh.texture", extra_params=_seed_param(node.get("properties", {})))
    out["mesh"] = out.get("asset")
    return out


def _is_enabled(inputs: dict, p: dict) -> bool:
    raw = inputs.get("enabled")
    if raw is None:
        raw = p.get("enabled", True)
    if isinstance(raw, str):
        return raw.strip().lower() not in ("false", "0", "no", "off", "")
    return bool(raw)


# image.prep_3d — clean background removal, tight crop & square padding for 3D generation

def _remove_bg_via_3d_venv(img_bytes: bytes) -> tuple[bytes | None, str]:
    """Run rembg inside an installed 3D worker venv when the host env lacks rembg."""
    import subprocess  # noqa: PLC0415
    import sys         # noqa: PLC0415
    import tempfile    # noqa: PLC0415
    from core.utils.paths import LOCAL_MODELS_3D  # noqa: PLC0415

    py_rel = Path("venv") / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    script = (
        "import sys; from PIL import Image; import rembg; "
        "rembg.remove(Image.open(sys.argv[1])).convert('RGBA').save(sys.argv[2], 'PNG')"
    )
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    last_err = "no 3D venv with rembg installed"
    for sub in ("hunyuan3d", "trellis2", "triposr"):
        py_exe = LOCAL_MODELS_3D / sub / py_rel
        if not py_exe.is_file():
            continue
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                in_p = Path(tmpdir) / "in.png"
                out_p = Path(tmpdir) / "out.png"
                in_p.write_bytes(img_bytes)
                proc = subprocess.run(
                    [str(py_exe), "-c", script, str(in_p), str(out_p)],
                    capture_output=True, text=True, timeout=120, creationflags=flags,
                )
                if proc.returncode == 0 and out_p.is_file() and out_p.stat().st_size > 0:
                    return out_p.read_bytes(), sub
                tail = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip().splitlines()
                last_err = f"{sub}: {tail[-1]}" if tail else f"{sub}: exit {proc.returncode}"
        except Exception as exc:  # noqa: BLE001
            last_err = f"{sub}: {exc}"
    return None, last_err


def image_prep_3d(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    from core.assets import store, values  # noqa: PLC0415
    from PIL import Image                # noqa: PLC0415

    ports = ("image", "path", "url", "width", "height")
    val = require_input(ctx, node, inputs, "image", "image", ports)
    if val is None:
        return {**{k: None for k in ports}, "error": "No image connected."}

    media = values.read_media(val)
    if not media:
        return fail(ctx, node, "Could not read reference image.", ports)

    p = node.get("properties", {})
    try:
        target_size = max(128, min(4096, int(p.get("size", 1024) or 1024)))
    except (TypeError, ValueError):
        target_size = 1024
    try:
        padding_ratio = max(0.0, min(0.45, float(p.get("padding_ratio", 0.12) or 0.12)))
    except (TypeError, ValueError):
        padding_ratio = 0.12
    remove_bg = p.get("remove_bg", True) is not False
    bg_mode = str(p.get("background", "transparent") or "transparent").strip().lower()

    im = Image.open(io.BytesIO(media[0]))
    if im.mode != "RGBA":
        im = im.convert("RGBA")

    ext = im.getchannel("A").getextrema()
    has_transparency = bool(ext and ext[0] < 250)
    bg_removed = has_transparency
    if remove_bg and not has_transparency:
        try:
            import rembg  # noqa: PLC0415
            im = rembg.remove(im).convert("RGBA")
            bg_removed = True
        except Exception as exc:  # noqa: BLE001
            cut_bytes, bg_src = _remove_bg_via_3d_venv(media[0])
            if cut_bytes:
                im = Image.open(io.BytesIO(cut_bytes)).convert("RGBA")
                bg_removed = True
                ctx._info(f"    Background removed via {bg_src} rembg.")
            else:
                ctx._warn(
                    f"    Background removal skipped ({exc}; 3D venv fallback: {bg_src}); "
                    "keeping opaque canvas so 3D worker runs segmentation."
                )

    if bg_removed:
        alpha = im.getchannel("A")
        a_ext = alpha.getextrema()
        if a_ext and a_ext[0] < 250:
            bbox = alpha.getbbox()
            if bbox:
                im = im.crop(bbox)

    inner = max(16, int(round(target_size * (1.0 - 2.0 * padding_ratio))))
    w, h = im.size
    if w > 0 and h > 0:
        scale = inner / max(w, h)
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.LANCZOS)
        im = im.resize((new_w, new_h), resample)

    ox = (target_size - im.width) // 2
    oy = (target_size - im.height) // 2
    if bg_removed:
        bg_color = (255, 255, 255, 255) if bg_mode == "white" else (0, 0, 0, 0)
        canvas = Image.new("RGBA", (target_size, target_size), bg_color)
        canvas.paste(im, (ox, oy), im)
    else:
        # Keep opaque RGB so downstream 3D workers still run their own background remover
        canvas = Image.new("RGB", (target_size, target_size), (255, 255, 255))
        canvas.paste(im.convert("RGB"), (ox, oy))

    out_buf = io.BytesIO()
    canvas.save(out_buf, format="PNG")
    parent = values.asset_id_of(val)
    rec = store.create_from_bytes(
        out_buf.getvalue(),
        ext="png",
        kind="image",
        name=str(p.get("name", "") or "prepped_3d"),
        source=ctx.asset_source(node),
        parents=[parent] if parent else [],
        tags=_tags(p.get("tags") or "prepped, 3d-input"),
    )
    ref = store.asset_ref(rec)
    return {
        "image": ref,
        "path": ref["path"],
        "url": ref["url"],
        "width": target_size,
        "height": target_size,
        "error": "",
    }


# model3d.trellis / model3d.hunyuan — dedicated engine nodes with toggleable branch execution

def model3d_trellis(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p = node.get("properties", {})
    if not _is_enabled(inputs, p):
        from core.automate.executor import NodeSkipped  # noqa: PLC0415
        raise NodeSkipped("TRELLIS.2 branch disabled")
    if require_input(ctx, node, inputs, "image", "reference image", _DATA_PORTS + ("mesh",)) is None:
        return {**{k: None for k in _DATA_PORTS + ("mesh",)}, "error": "No reference image connected."}

    extra: dict[str, Any] = {
        "resolution": str(p.get("resolution", "1024") or "1024"),
        "texture_size": int(p.get("texture_size", 2048) or 2048),
        "decimation_target": int(p.get("decimation_target", 100000) or 100000),
        "remesh": p.get("remesh", True) is not False,
        "textured": True,
        "pbr": True,
    }
    extra.update(_seed_param(p))
    out = _invoke(node, inputs, ctx, "mesh.generate", extra_params=extra, default_endpoint="3d:trellis-2")
    out["mesh"] = out.get("asset")
    return out


def model3d_hunyuan(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p = node.get("properties", {})
    if not _is_enabled(inputs, p):
        from core.automate.executor import NodeSkipped  # noqa: PLC0415
        raise NodeSkipped("Hunyuan3D 2.1 branch disabled")
    if require_input(ctx, node, inputs, "image", "reference image", _DATA_PORTS + ("mesh",)) is None:
        return {**{k: None for k in _DATA_PORTS + ("mesh",)}, "error": "No reference image connected."}

    textured = p.get("textured", True) is not False
    extra: dict[str, Any] = {
        "textured": textured,
        "pbr": textured,
        "max_num_view": int(p.get("max_num_view", 6) or 6),
        "texture_resolution": int(p.get("texture_resolution", 512) or 512),
        "steps": int(p.get("steps", 50) or 50),
    }
    extra.update(_seed_param(p))
    out = _invoke(node, inputs, ctx, "mesh.generate", extra_params=extra, default_endpoint="3d:hunyuan3d")
    out["mesh"] = out.get("asset")
    return out


# mesh.normalize — center XZ, ground Y=0, scale & rotate GLB in pure Python

def mesh_normalize(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    from core.assets import store, values  # noqa: PLC0415
    from core.modelhub import glb           # noqa: PLC0415

    ports = ("mesh", "path", "url", "stats")
    mesh_val = require_input(ctx, node, inputs, "mesh", "mesh", ports)
    if mesh_val is None:
        return {**{k: None for k in ports}, "error": "No mesh connected."}

    p = node.get("properties", {})
    path = values.local_path(mesh_val) or str(p.get("path", "") or "").strip()
    if not path or not Path(path).is_file():
        return fail(ctx, node, "No valid mesh file found to normalize.", ports)

    raw_bytes = Path(path).read_bytes()
    try:
        target_size = float(p.get("target_size", 1.0) or 1.0)
    except (TypeError, ValueError):
        target_size = 1.0
    try:
        rotate_y_deg = float(p.get("rotate_y_deg", 0.0) or 0.0)
    except (TypeError, ValueError):
        rotate_y_deg = 0.0

    try:
        out_bytes, stats = glb.normalize_glb(
            raw_bytes,
            center_xz=p.get("center_xz", True) is not False,
            ground_y=p.get("ground_y", True) is not False,
            target_size=target_size,
            rotate_y_deg=rotate_y_deg,
        )
    except Exception as exc:  # noqa: BLE001
        return fail(ctx, node, f"Mesh normalization failed: {exc}", ports)

    parent = values.asset_id_of(mesh_val)
    default_name = f"{Path(path).stem}_norm"
    rec = store.create_from_bytes(
        out_bytes,
        ext="glb",
        kind="mesh",
        name=str(p.get("name", "") or default_name),
        source=ctx.asset_source(node),
        parents=[parent] if parent else [],
        tags=_tags(p.get("tags") or "normalized, game-ready"),
    )
    ref = store.asset_ref(rec)
    return {
        "mesh": ref,
        "path": ref["path"],
        "url": ref["url"],
        "stats": stats,
        "error": "",
    }


# mesh.inspect

def _mesh_summary(stats: dict) -> str:
    if stats.get("error"):
        return f"Could not read mesh: {stats['error']}"
    lines = [f"File: {stats.get('file')} ({stats.get('format', '?').upper()}, {stats.get('size_bytes', 0):,} bytes)"]
    if "triangles" in stats:
        lines.append(f"Geometry: {stats['triangles']:,} triangles, {stats['vertices']:,} vertices, "
                     f"{stats.get('meshes', 1)} mesh(es)")
        lines.append(f"UVs: {'yes' if stats.get('has_uvs') else 'NO'} · normals: "
                     f"{'yes' if stats.get('has_normals') else 'NO'} · materials: {stats.get('materials', 0)} · "
                     f"textures: {stats.get('textures', 0)} · fully textured: {'yes' if stats.get('is_textured') else 'no'}"
                     f" · vertex colours: {'yes' if stats.get('has_vertex_colors') else 'no'}")
        if stats.get("size"):
            lines.append("Bounding box size (x, y, z): " + ", ".join(f"{v:g}" for v in stats["size"]))
        if stats.get("animations") or stats.get("skins"):
            lines.append(f"Animations: {stats.get('animations', 0)} · skins: {stats.get('skins', 0)}")
    if stats.get("note"):
        lines.append(stats["note"])
    return "\n".join(lines)


def mesh_inspect(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    from core.assets import store, values   # noqa: PLC0415
    from core.modelhub import glb           # noqa: PLC0415

    ports = ("stats", "summary", "triangles", "texture", "textures", "pass", "fail")
    p = node.get("properties", {})
    mesh_val = inputs.get("mesh")
    if mesh_val in (None, "") and input_wired(ctx, node, "mesh"):
        from core.automate.executor import NodeSkipped  # noqa: PLC0415
        raise NodeSkipped("no mesh arrived from the previous step")
    path = values.local_path(mesh_val) or str(p.get("path", "") or "").strip()
    if not path:
        return fail(ctx, node, "No mesh connected (expected a mesh asset or a file path).", ports)

    try:
        stats = glb.inspect_mesh(path)
    except OSError as exc:
        return fail(ctx, node, f"Could not read mesh file: {exc}", ports)
    if stats.get("error"):
        return fail(ctx, node, f"Could not read mesh: {stats['error']}", ports)

    issues: list[str] = []
    try:
        max_tris = int(float(p.get("max_triangles", 0) or 0))
    except (TypeError, ValueError):
        max_tris = 0
    tris = stats.get("triangles")
    if max_tris > 0 and isinstance(tris, int) and tris > max_tris:
        issues.append(f"Triangle count {tris:,} exceeds the budget of {max_tris:,}.")
    if p.get("require_uvs") and stats.get("has_uvs") is False:
        issues.append("Mesh has no UV coordinates.")
    if p.get("require_textures") and not stats.get("is_textured"):
        issues.append("Mesh is not (fully) textured.")
    if isinstance(tris, int) and tris == 0 and "triangles" in stats:
        issues.append("Mesh contains no triangles.")

    texture_refs: list[dict] = []
    if p.get("extract_textures", True):
        parent = values.asset_id_of(mesh_val)
        try:
            for name, mime, blob in glb.extract_images(path)[:8]:
                rec = store.create_from_bytes(
                    blob, ext=store.ext_for_mime(mime, "png"), kind="image", name=f"{name}",
                    source={**ctx.asset_source(node), "capability": "mesh.inspect"},
                    parents=[parent] if parent else [], tags=["texture", "extracted"],
                )
                texture_refs.append(store.asset_ref(rec))
        except Exception as exc:  # noqa: BLE001 — texture extraction is a bonus, never fatal
            ctx._warn(f"    Could not extract textures: {exc}")

    ok = not issues
    summary = _mesh_summary(stats)
    if issues:
        summary += "\nIssues:\n" + "\n".join(f"- {i}" for i in issues)
    passthrough = mesh_val if mesh_val not in (None, "") else path
    return {
        "stats":     stats,
        "summary":   summary,
        "triangles": tris if isinstance(tris, int) else None,
        "texture":   texture_refs[0] if texture_refs else None,
        "textures":  texture_refs or None,
        "ok":        ok,
        "issues":    "\n".join(issues),
        "pass":      passthrough if ok else None,
        "fail":      None if ok else passthrough,
        "error":     "",
    }


# quality.verify — AI reviewer / quality gate

_REVIEW_SYSTEM = (
    "You are a meticulous quality reviewer in a production pipeline. Judge the submitted "
    "work strictly against the stated criteria and nothing else. Be concrete: name what is "
    "wrong and what would fix it. Respond with ONLY a JSON object, no prose around it:\n"
    '{"score": <integer 0-100>, "passed": <true|false>, "issues": ["..."], '
    '"feedback": "<actionable instructions for the next attempt, or empty if nothing to fix>"}'
)


def quality_verify(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    from core.assets import values                       # noqa: PLC0415
    from core.modelhub import glb                         # noqa: PLC0415
    from .ai import _extract_json_from_response           # noqa: PLC0415

    ports = ("pass", "fail", "score", "feedback", "issues", "report")
    p = node.get("properties", {})
    subject = inputs.get("in")
    if subject in (None, "") and input_wired(ctx, node, "in"):
        from core.automate.executor import NodeSkipped  # noqa: PLC0415
        raise NodeSkipped("nothing to verify arrived from the previous step")
    if subject in (None, ""):
        return fail(ctx, node, "Nothing to verify — wire the output you want checked into Subject.", ports)

    model_id = _text_in(inputs, p, "model")
    if model_id.startswith("llm:"):
        model_id = model_id[4:]
    if not model_id:
        raise ValueError("No reviewer model selected — open the node's properties and pick one.")

    criteria = _text_in(inputs, p, "criteria")
    if not criteria:
        raise ValueError("No criteria given — describe what a good result looks like.")
    try:
        threshold = max(0.0, min(100.0, float(p.get("threshold", 70))))
    except (TypeError, ValueError):
        threshold = 70.0

    parts = [f"## Criteria\n{criteria}"]
    context = _to_str(inputs.get("context", "")).strip()
    images: list[dict] = []

    def _add_image(val: Any) -> bool:
        media = values.read_media(val)
        if media and media[1].startswith("image/") and len(images) < 4:
            images.append({"data": media[0], "mime_type": media[1]})
            return True
        return False

    ref = values.as_asset_ref(subject)
    kind = ref["kind"] if ref else ""
    if kind == "mesh":
        stats = glb.inspect_mesh(ref["path"])
        parts.append("## Submitted work: a 3D model\nMeasured facts about the mesh file "
                     "(trust these over any assumption):\n" + _mesh_summary(stats))
        try:
            for _name, mime, blob in glb.extract_images(ref["path"])[:2]:
                images.append({"data": blob, "mime_type": mime})
            if images:
                parts.append("The attached image(s) are the texture maps embedded in the model "
                             "(flat UV layouts, not renders).")
        except Exception:  # noqa: BLE001
            pass
    elif kind == "image" or (not ref and _add_image(subject)):
        if ref:
            _add_image(ref)
        parts.append("## Submitted work: the attached image")
    elif ref:
        media = values.read_media(ref)
        text = media[0].decode("utf-8", errors="replace")[:20000] if media and kind in ("text", "json") else ""
        parts.append(f"## Submitted work: {kind} file '{ref['name']}.{ref['ext']}'\n{text}")
    else:
        parts.append("## Submitted work\n" + _to_str(subject)[:20000])

    extra = inputs.get("image")
    for item in (extra if isinstance(extra, list) else [extra]):
        if item not in (None, "") and _add_image(item):
            parts.append("An additional preview image of the work is attached.")
    if context:
        parts.append(f"## Additional context\n{context[:8000]}")
    parts.append(f"A score of {threshold:g} or higher passes.")

    kwargs: dict[str, Any] = {"images": images} if images else {}
    resp = _get_pm().call_with_failover(
        prompt="\n\n".join(parts),
        trace_id=f"automate-verify-{uuid.uuid4().hex[:8]}",
        system_prompt=_REVIEW_SYSTEM,
        temperature=0.1,
        model=model_id,
        request_type="generation",
        source="automate-execution",
        **kwargs,
    )
    if not resp.success:
        return fail(ctx, node, resp.error or "Reviewer model call failed", ports)

    verdict = _extract_json_from_response(resp.content or "")
    if not verdict or ("score" not in verdict and "passed" not in verdict):
        return fail(ctx, node, f"Reviewer did not return a verdict. Raw reply: {(resp.content or '')[:300]}", ports)

    try:
        score = float(verdict.get("score"))
        passed = score >= threshold
    except (TypeError, ValueError):
        score = None
        passed = bool(verdict.get("passed"))
    issues = verdict.get("issues") if isinstance(verdict.get("issues"), list) else []
    feedback = str(verdict.get("feedback", "") or "").strip() or "; ".join(map(str, issues))

    ctx._info(f"    Verdict: {'PASS' if passed else 'FAIL'}"
              + (f" — score {score:g}/{threshold:g}" if score is not None else ""))
    return {
        "pass":     subject if passed else None,
        "fail":     None if passed else subject,
        "passed":   passed,
        "score":    score,
        "feedback": feedback,
        "issues":   "\n".join(f"- {i}" for i in issues),
        "report":   {"passed": passed, "score": score, "threshold": threshold, "issues": issues,
                     "feedback": feedback, "reviewer": model_id},
        "error":    "",
    }
