"""
core/modelhub/adapters.py
How each kind of endpoint is actually called.

Every adapter is a function  (endpoint, request) -> RawResult  where

    request   InvokeRequest — capability, prompt, media inputs, params
    RawResult text and/or a list of produced files (bytes + ext), plus raw data

The hub (hub.py) turns produced files into assets with lineage; adapters only talk to
the model.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import os
import shlex
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from core.assets import store, values
from core.utils.logger import get_logger

from .capabilities import output_kind
from .templating import LazyVars, lookup, render

logger = get_logger(__name__)


class EndpointError(RuntimeError):
    """A model endpoint failed in a way worth showing to the user as-is."""


@dataclass
class InvokeRequest:
    capability: str
    prompt: str = ""
    system_prompt: str = ""
    negative_prompt: str = ""
    image: Any = None            # any media value (asset ref, path, data URI…)
    mesh: Any = None
    audio: Any = None
    params: dict = field(default_factory=dict)
    cancel: Optional[Callable[[], bool]] = None   # returns True when the run was cancelled
    log: Optional[Callable[[str], None]] = None

    def cancelled(self) -> bool:
        return bool(self.cancel and self.cancel())

    def info(self, msg: str) -> None:
        if self.log:
            self.log(msg)


@dataclass
class ProducedFile:
    data: bytes
    ext: str
    kind: str = ""
    name: str = ""


@dataclass
class RawResult:
    text: str = ""
    files: list[ProducedFile] = field(default_factory=list)
    data: Any = None             # raw response (JSON) when useful downstream
    model: str = ""


def _run_coro(coro) -> Any:
    """Run an async function to completion from sync code, whatever thread we're on."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    box: dict[str, Any] = {}

    def _runner() -> None:
        try:
            box["value"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001
            box["error"] = exc

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join()
    if "error" in box:
        raise box["error"]
    return box.get("value")


def _num(val: Any, default: Any = None, cast=float) -> Any:
    try:
        return cast(val)
    except (TypeError, ValueError):
        return default


# llm — any chat model through the ProviderManager

def call_llm(endpoint: dict, req: InvokeRequest) -> RawResult:
    from core.providers import get_provider_manager  # noqa: PLC0415

    model_id = endpoint["id"].split(":", 1)[1]
    kwargs: dict[str, Any] = {}
    media = values.read_media(req.image)
    if media:
        data, mime, _ = media
        kwargs["images"] = [{"data": data, "mime_type": mime}]
    max_tokens = _num(req.params.get("max_tokens"), None, int)
    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    resp = get_provider_manager().call_with_failover(
        prompt=req.prompt or "(no input)",
        trace_id=f"modelhub-{uuid.uuid4().hex[:8]}",
        system_prompt=req.system_prompt or None,
        temperature=_num(req.params.get("temperature"), 0.7),
        model=model_id,
        request_type="generation",
        source="automate-execution",
        **kwargs,
    )
    if not resp.success:
        raise EndpointError(resp.error or "Model call failed")
    return RawResult(text=resp.content or "", model=resp.model or model_id)


# suite-image — the Image tab's generation pipeline (local GPU / SD WebUI / cloud)

def call_suite_image(endpoint: dict, req: InvokeRequest) -> RawResult:
    from core.interfaces.dashboard import photo_routes  # noqa: PLC0415
    from fastapi import HTTPException  # noqa: PLC0415

    model_id = endpoint["id"].split(":", 1)[1]
    p = req.params
    image_b64 = values.to_base64(req.image)
    body = photo_routes.ImageGenerationRequest(
        prompt=req.prompt,
        model=model_id,
        n=1,
        size=str(p.get("size") or "1024x1024"),
        aspect_ratio=str(p["aspect_ratio"]) if p.get("aspect_ratio") else None,
        negative_prompt=req.negative_prompt or None,
        seed=_num(p.get("seed"), None, int),
        steps=_num(p.get("steps"), 25, int),
        cfg_scale=_num(p.get("cfg_scale"), 7.0),
        action=str(p.get("action") or ("img2img" if image_b64 and req.capability == "image.edit" else "generate")),
        input_image=image_b64 or None,
    )
    try:
        resp = _run_coro(photo_routes.generate_image(body))
    except HTTPException as exc:
        raise EndpointError(str(exc.detail)) from exc
    if not resp.success or not resp.images:
        raise EndpointError(resp.error or "Image generation returned no images")

    files = []
    for img in resp.images:
        path = Path(img.get("path", ""))
        if path.is_file():
            files.append(ProducedFile(path.read_bytes(), path.suffix.lstrip(".") or "png", "image"))
    if not files:
        raise EndpointError("Image generation succeeded but the output file is missing")
    return RawResult(files=files, model=model_id, data=resp.metadata)


# suite-3d — the 3D tab's local worker processes

def call_suite_3d(endpoint: dict, req: InvokeRequest) -> RawResult:
    from core.interfaces.dashboard import three_d_routes  # noqa: PLC0415

    model_id = endpoint["id"].split(":", 1)[1]
    image_b64 = values.to_base64(req.image)
    if not image_b64 and not req.prompt:
        raise EndpointError("3D generation needs a prompt or a reference image")
    body = three_d_routes.ThreeDGenerationRequest(
        action="image23d" if image_b64 else "generate",
        prompt=req.prompt or None,
        input_image=image_b64 or None,
        model=model_id,
        seed=_num(req.params.get("seed"), None, int),
    )
    req.info(f"Starting local 3D worker '{model_id}' (first run loads the model and can take minutes)…")
    resp = _run_coro(three_d_routes.generate_3d_asset(body))
    if not resp.success or not resp.asset:
        raise EndpointError(resp.error or "3D generation failed")
    path = Path(resp.asset.path)
    if not path.is_file():
        raise EndpointError("3D generation succeeded but the output file is missing")
    return RawResult(files=[ProducedFile(path.read_bytes(), "glb", "mesh")], model=model_id)


# demo — placeholder generators (no model), so a pipeline can be tried end to end

def _prompt_colour(prompt: str) -> tuple[int, int, int]:
    h = hashlib.sha256((prompt or "aethvion").encode("utf-8")).digest()
    return 64 + h[0] % 160, 64 + h[1] % 160, 64 + h[2] % 160


def _demo_png(prompt: str, size: int = 512, label: str = "DEMO") -> bytes:
    from PIL import Image, ImageDraw  # noqa: PLC0415

    r, g, b = _prompt_colour(prompt)
    img = Image.new("RGB", (size, size), (r, g, b))
    draw = ImageDraw.Draw(img)
    step = size // 8
    for y in range(8):
        for x in range(8):
            if (x + y) % 2 == 0:
                draw.rectangle([x * step, y * step, (x + 1) * step - 1, (y + 1) * step - 1],
                               fill=(max(r - 28, 0), max(g - 28, 0), max(b - 28, 0)))
    draw.rectangle([0, 0, size - 1, size - 1], outline=(255, 255, 255), width=4)
    text = f"{label}: {(prompt or '').strip()[:48]}"
    draw.rectangle([10, 10, min(size - 10, 20 + 7 * len(text)), 34], fill=(0, 0, 0))
    draw.text((16, 15), text, fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def call_demo(endpoint: dict, req: InvokeRequest) -> RawResult:
    from . import glb  # noqa: PLC0415

    which = endpoint["id"].split(":", 1)[1]
    if which == "image":
        return RawResult(files=[ProducedFile(_demo_png(req.prompt, label="DEMO IMAGE"), "png", "image")], model="demo")

    if which == "mesh":
        p = req.params
        size = (_num(p.get("width"), 1.0) or 1.0, _num(p.get("height"), 1.0) or 1.0, _num(p.get("depth"), 1.0) or 1.0)
        return RawResult(files=[ProducedFile(glb.make_box_glb(size), "glb", "mesh")], model="demo")

    if which == "texture":
        mesh = values.read_media(req.mesh)
        if not mesh:
            raise EndpointError("Texturing needs a mesh input")
        if mesh[2] != "glb":
            raise EndpointError("The demo texture endpoint only handles .glb meshes")
        ref = values.read_media(req.image)
        tex, mime = (ref[0], ref[1]) if ref and ref[1].startswith("image/") else (_demo_png(req.prompt, label="DEMO TEXTURE"), "image/png")
        try:
            out = glb.apply_base_color_texture(mesh[0], tex, mime)
        except glb.MeshFormatError as exc:
            raise EndpointError(f"Could not read mesh: {exc}") from exc
        return RawResult(files=[ProducedFile(out, "glb", "mesh")], model="demo")

    raise EndpointError(f"Unknown demo endpoint: {which}")


# Shared template variables for http / command adapters

def _template_vars(req: InvokeRequest, extra: Optional[dict] = None) -> LazyVars:
    v = LazyVars({
        "prompt":          req.prompt,
        "system_prompt":   req.system_prompt,
        "negative_prompt": req.negative_prompt,
        "capability":      req.capability,
        "params":          dict(req.params),
        "env":             dict(os.environ),
    })
    for name, val in (("image", req.image), ("mesh", req.mesh), ("audio", req.audio)):
        v[f"{name}_b64"]      = (lambda val=val: values.to_base64(val))
        v[f"{name}_data_uri"] = (lambda val=val: values.to_data_uri(val))
        v[f"{name}_path"]     = (lambda val=val: _materialise(val))
        v[f"{name}_name"]     = (lambda val=val: (values.as_asset_ref(val) or {}).get("name", ""))
    if extra:
        v.update(extra)
    return v


def _materialise(val: Any) -> str:
    """A local file path for a media value — writes a temp file for data URIs / bytes."""
    p = values.local_path(val)
    if p:
        return p
    media = values.read_media(val)
    if not media:
        return ""
    data, _mime, ext = media
    tmp = Path(tempfile.gettempdir()) / f"aethvion_in_{uuid.uuid4().hex[:10]}.{ext or 'bin'}"
    tmp.write_bytes(data)
    return str(tmp)


def _check_required(defn: dict, req: InvokeRequest) -> None:
    for name in defn.get("requires", []) or []:
        val = getattr(req, name, None)
        if val in (None, "") or (name in ("image", "mesh", "audio") and not values.read_media(val)):
            raise EndpointError(f"This endpoint requires a '{name}' input")


def _default_params(defn: dict, req: InvokeRequest) -> None:
    for spec in defn.get("params") or []:
        key = spec.get("key")
        if key and key not in req.params and "default" in spec:
            req.params[key] = spec["default"]


# http — any HTTP API

def call_http(endpoint: dict, req: InvokeRequest) -> RawResult:
    import httpx  # noqa: PLC0415

    defn = endpoint.get("definition") or {}
    cfg  = defn.get("http") or {}
    _check_required(defn, req)
    _default_params(defn, req)

    variables = _template_vars(req)
    timeout   = float(cfg.get("timeout", 600))
    headers   = render(cfg.get("headers") or {}, variables)
    method    = str(cfg.get("method", "POST")).upper()
    url       = render(cfg.get("url", ""), variables)
    verify    = cfg.get("verify_tls", True) is not False

    def _send(client: "httpx.Client", method: str, url: str, body_cfg: dict) -> "httpx.Response":
        kwargs: dict[str, Any] = {"headers": headers}
        body = render(body_cfg.get("body"), variables) if body_cfg.get("body") is not None else None
        query = render(body_cfg.get("query") or {}, variables)
        if query:
            kwargs["params"] = query
        if str(body_cfg.get("body_type", "json")) == "multipart":
            files = {}
            for fld, input_name in (body_cfg.get("files") or {}).items():
                media = values.read_media(getattr(req, str(input_name), None))
                if media:
                    files[fld] = (f"{input_name}.{media[2] or 'bin'}", media[0], media[1])
            kwargs["files"] = files or None
            kwargs["data"] = {k: (v if isinstance(v, str) else str(v)) for k, v in (body or {}).items()}
        elif body is not None and method != "GET":
            kwargs["json"] = body
        return client.request(method, url, **kwargs)

    with httpx.Client(timeout=timeout, verify=verify, follow_redirects=True) as client:
        try:
            resp = _send(client, method, url, cfg)
        except httpx.HTTPError as exc:
            raise EndpointError(f"Could not reach {url}: {exc}") from exc
        if resp.status_code >= 400:
            raise EndpointError(f"HTTP {resp.status_code} from {url}: {resp.text[:400]}")

        payload: Any = None
        result_cfg = cfg.get("result") or {"type": "binary"}

        # Asynchronous APIs: submit a job, then poll until it finishes
        poll = cfg.get("poll")
        if poll:
            try:
                variables["response"] = resp.json()
            except ValueError as exc:
                raise EndpointError("Expected a JSON response to start polling") from exc
            interval = max(0.5, float(poll.get("interval", 3)))
            deadline = time.time() + float(poll.get("timeout", 900))
            done   = {str(s).lower() for s in poll.get("done", ["succeeded", "completed", "success", "done"])}
            failed = {str(s).lower() for s in poll.get("failed", ["failed", "error", "canceled", "cancelled"])}
            while True:
                if req.cancelled():
                    raise EndpointError("Cancelled")
                if time.time() > deadline:
                    raise EndpointError("Timed out waiting for the job to finish")
                time.sleep(interval)
                p_url = render(poll.get("url", ""), variables)
                try:
                    presp = client.request(str(poll.get("method", "GET")).upper(), p_url, headers=headers)
                except httpx.HTTPError as exc:
                    raise EndpointError(f"Polling failed: {exc}") from exc
                if presp.status_code >= 400:
                    raise EndpointError(f"HTTP {presp.status_code} while polling: {presp.text[:300]}")
                payload = presp.json()
                status = str(lookup(payload, poll.get("status_path", "status")) or "").lower()
                progress = lookup(payload, poll["progress_path"]) if poll.get("progress_path") else None
                req.info(f"Job status: {status or '?'}" + (f" ({progress}%)" if progress is not None else ""))
                if status in done:
                    break
                if status in failed:
                    msg = lookup(payload, poll.get("error_path", "error")) or status
                    raise EndpointError(f"Job failed: {msg}")
            variables["result"] = payload

        rtype = str(result_cfg.get("type", "binary")).lower()
        if rtype == "binary" and payload is None:
            ext = result_cfg.get("ext") or _output_ext(defn, req, resp.headers.get("content-type", ""))
            return RawResult(files=[ProducedFile(resp.content, ext)], model=defn.get("id", ""))

        if payload is None:
            try:
                payload = resp.json()
            except ValueError as exc:
                raise EndpointError(f"Expected JSON from {url}, got: {resp.text[:200]}") from exc

        err_path = result_cfg.get("error_path")
        if err_path and lookup(payload, err_path):
            raise EndpointError(str(lookup(payload, err_path)))
        ok_path = result_cfg.get("success_path")
        if ok_path and lookup(payload, ok_path) in (False, None, 0, "false"):
            raise EndpointError(str(lookup(payload, err_path or "error") or "Endpoint reported failure"))

        if rtype == "json":
            import json as _json  # noqa: PLC0415
            return RawResult(text=_json.dumps(payload, ensure_ascii=False, indent=2), data=payload)

        value = lookup(payload, result_cfg.get("path", "")) if result_cfg.get("path") else payload
        if value in (None, ""):
            raise EndpointError(f"Response has no value at '{result_cfg.get('path', '')}': {str(payload)[:300]}")

        if rtype == "text":
            return RawResult(text=value if isinstance(value, str) else str(value), data=payload)

        items = value if isinstance(value, list) else [value]
        files: list[ProducedFile] = []
        for item in items:
            if rtype == "base64":
                s = str(item)
                mime = ""
                if s.startswith("data:") and "," in s:
                    mime, s = s[5:].split(";")[0], s.split(",", 1)[1]
                files.append(ProducedFile(base64.b64decode(s), result_cfg.get("ext") or _output_ext(defn, req, mime)))
            elif rtype == "url":
                dl_headers = headers if result_cfg.get("download_with_headers") else None
                try:
                    dresp = client.get(str(item), headers=dl_headers)
                except httpx.HTTPError as exc:
                    raise EndpointError(f"Could not download result: {exc}") from exc
                if dresp.status_code >= 400:
                    raise EndpointError(f"HTTP {dresp.status_code} downloading result")
                ext = result_cfg.get("ext") or _ext_from_url(str(item)) or _output_ext(defn, req, dresp.headers.get("content-type", ""))
                files.append(ProducedFile(dresp.content, ext))
            else:
                raise EndpointError(f"Unknown result type '{rtype}'")
        return RawResult(files=files, data=payload, model=defn.get("id", ""))


def _ext_from_url(url: str) -> str:
    tail = url.split("?", 1)[0].rsplit("/", 1)[-1]
    if "." in tail:
        ext = tail.rsplit(".", 1)[1].lower()
        if 1 <= len(ext) <= 5 and ext.isalnum():
            return ext
    return ""


_KIND_DEFAULT_EXT = {"image": "png", "mesh": "glb", "audio": "wav", "video": "mp4", "text": "txt", "json": "json"}


def _output_ext(defn: dict, req: InvokeRequest, mime: str = "") -> str:
    out = defn.get("output") or {}
    if out.get("ext"):
        return str(out["ext"]).lstrip(".")
    if mime and mime.split(";")[0].strip() not in ("application/octet-stream", "application/json", "text/plain"):
        ext = store.ext_for_mime(mime, "")
        if ext:
            return ext
    kind = out.get("kind") or output_kind(req.capability)
    return _KIND_DEFAULT_EXT.get(kind, "bin")


# command — any command-line tool

def call_command(endpoint: dict, req: InvokeRequest) -> RawResult:
    defn = endpoint.get("definition") or {}
    cfg  = defn.get("command") or {}
    _check_required(defn, req)
    _default_params(defn, req)

    ext = _output_ext(defn, req)
    out_dir = Path(tempfile.mkdtemp(prefix="aethvion_cmd_"))
    out_path = out_dir / f"output.{ext}"
    scripts_dir = Path(__file__).parent / "scripts"
    variables = _template_vars(req, {
        "output_path": str(out_path), "output_dir": str(out_dir), "scripts_dir": str(scripts_dir),
    })

    args = [str(a) for a in render(cfg.get("args") or [], variables)]
    if not args:
        raise EndpointError("command.args rendered to an empty command")
    cwd = render(cfg.get("cwd", ""), variables) or None
    env = {**os.environ, **{k: str(v) for k, v in (render(cfg.get("env") or {}, variables) or {}).items()}}
    timeout = float(cfg.get("timeout", 900))

    req.info("Running: " + " ".join(shlex.quote(a) for a in args)[:300])
    try:
        proc = subprocess.Popen(
            args, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except FileNotFoundError as exc:
        raise EndpointError(f"Program not found: {args[0]} — is it installed and on PATH?") from exc
    except OSError as exc:
        raise EndpointError(f"Could not start command: {exc}") from exc

    # communicate() in a helper thread so the run can be cancelled while it works
    box: dict[str, Any] = {}
    t = threading.Thread(target=lambda: box.update(zip(("out", "err"), proc.communicate())), daemon=True)
    t.start()
    deadline = time.time() + timeout
    while t.is_alive():
        t.join(0.5)
        if req.cancelled() or time.time() > deadline:
            proc.kill()
            t.join(5)
            raise EndpointError("Cancelled" if req.cancelled() else f"Command timed out after {int(timeout)}s")

    stdout, stderr = box.get("out", "") or "", box.get("err", "") or ""
    if proc.returncode != 0:
        tail = (stderr.strip() or stdout.strip())[-600:]
        raise EndpointError(f"Command exited with code {proc.returncode}: {tail}")

    rtype = str((cfg.get("result") or {}).get("type", "file")).lower()
    if rtype == "stdout":
        return RawResult(text=stdout.strip(), model=defn.get("id", ""))

    produced = [out_path] if out_path.is_file() else sorted(p for p in out_dir.iterdir() if p.is_file())
    if not produced:
        raise EndpointError("Command finished but wrote no output file. It must write to {{output_path}} "
                            f"(or into {{{{output_dir}}}}). Output: {(stdout or stderr)[-300:]}")
    files = [ProducedFile(p.read_bytes(), p.suffix.lstrip(".") or ext, name=p.stem if p != out_path else "") for p in produced]
    return RawResult(files=files, text=stdout.strip()[-2000:], model=defn.get("id", ""))


ADAPTERS: dict[str, Callable[[dict, InvokeRequest], RawResult]] = {
    "llm":         call_llm,
    "suite-image": call_suite_image,
    "suite-3d":    call_suite_3d,
    "demo":        call_demo,
    "http":        call_http,
    "command":     call_command,
}
