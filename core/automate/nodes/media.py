"""
core/automate/nodes/media.py
Handler functions for screenshot, camera, vision, image generation,
text-to-speech, and speech-to-text node types.

All heavy dependencies (mss, cv2, TTS manager) are imported lazily so the
executor can start without them installed — each node returns a clear error
message if the required library is missing.
"""
from __future__ import annotations

import base64
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from ._utils import _to_str, _get_pm


def _file_to_data_uri(path: str, mime: str = "image/png") -> str:
    """Read an image file and return a data URI suitable for an <img> src."""
    try:
        data = Path(path).read_bytes()
        return f"data:{mime};base64," + base64.b64encode(data).decode()
    except Exception:
        return ""


# OCR — extract text from image

def action_ocr(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Extract text from an image using Tesseract OCR (pytesseract + Pillow).

    Accepts either a file path or a base64 data URI on the ``image`` / ``path``
    input.  Falls back to the ``image_path`` property if no wire is connected.
    """
    p           = node.get("properties", {})
    image_input = _to_str(
        inputs.get("image") or inputs.get("path") or p.get("image_path", "")
    ).strip()
    language    = str(p.get("language", "eng")).strip() or "eng"
    config      = str(p.get("config", "")).strip()

    if not image_input:
        return {"out": "", "error": "OCR: no image path or data URI provided"}

    try:
        import pytesseract          # noqa: PLC0415
        from PIL import Image       # noqa: PLC0415
    except ImportError:
        return {
            "out": "",
            "error": "pytesseract / Pillow not installed — run: pip install pytesseract Pillow",
        }

    try:
        if image_input.startswith("data:"):
            import io as _io            # noqa: PLC0415
            import base64 as _b64       # noqa: PLC0415
            _header, b64data = image_input.split(",", 1)
            image_bytes = _b64.b64decode(b64data)
            img = Image.open(_io.BytesIO(image_bytes))
        else:
            img = Image.open(image_input)

        text = pytesseract.image_to_string(img, lang=language, config=config).strip()
        return {"out": text, "error": ""}

    except Exception as exc:
        return {"out": "", "error": str(exc)}


# Screenshot

def action_screenshot(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p         = node.get("properties", {})
    monitor   = int(p.get("monitor", 0))
    save_path = _to_str(inputs.get("path") or p.get("path", "")).strip()

    try:
        import mss          # noqa: PLC0415
        import mss.tools    # noqa: PLC0415
    except ImportError:
        return {"out": "", "image": "", "error": "mss not installed — run: pip install mss"}

    try:
        with mss.mss() as sct:
            monitors = sct.monitors
            if monitor < 0 or monitor >= len(monitors):
                return {"out": "", "image": "",
                        "error": f"Monitor {monitor} out of range (0–{len(monitors)-1})"}

            sct_img = sct.grab(monitors[monitor])

            if not save_path:
                ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_path = str(Path(tempfile.gettempdir()) / f"automate_screenshot_{ts}.png")

            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            mss.tools.to_png(sct_img.rgb, sct_img.size, output=save_path)

        return {
            "out":    save_path,
            "image":  _file_to_data_uri(save_path, "image/png"),
            "width":  sct_img.width,
            "height": sct_img.height,
            "error":  "",
        }
    except Exception as exc:
        return {"out": "", "image": "", "width": 0, "height": 0, "error": str(exc)}


# Camera capture

def action_camera_capture(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p            = node.get("properties", {})
    camera_index = int(p.get("camera_index", 0))
    width        = int(p.get("width",  1280))
    height       = int(p.get("height", 720))
    save_path    = _to_str(inputs.get("path") or p.get("path", "")).strip()

    try:
        import cv2  # noqa: PLC0415
    except ImportError:
        return {"out": "", "image": "", "width": 0, "height": 0,
                "error": "opencv-python not installed — run: pip install opencv-python"}

    try:
        flag = cv2.CAP_DSHOW if sys.platform == "win32" else 0
        cap  = cv2.VideoCapture(camera_index, flag)
        if not cap.isOpened():
            return {"out": "", "image": "", "width": 0, "height": 0,
                    "error": f"Could not open camera at index {camera_index}"}

        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        # Flush the hardware buffer — read and discard several warmup frames
        for _ in range(5):
            cap.read()

        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            return {"out": "", "image": "", "width": 0, "height": 0,
                    "error": "Failed to capture frame from camera"}

        if not save_path:
            ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = str(Path(tempfile.gettempdir()) / f"automate_webcam_{ts}.jpg")

        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(save_path, frame)

        return {
            "out":    save_path,
            "image":  _file_to_data_uri(save_path, "image/jpeg"),
            "width":  frame.shape[1],
            "height": frame.shape[0],
            "error":  "",
        }
    except Exception as exc:
        return {"out": "", "image": "", "width": 0, "height": 0, "error": str(exc)}


# Vision — analyse image

_MIME_MAP = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png",  ".gif":  "image/gif",
    ".webp": "image/webp", ".bmp": "image/bmp",
}


def ai_analyze_image(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p           = node.get("properties", {})
    model_id    = _to_str(inputs.get("model") or p.get("model", "")).strip()
    image_input = _to_str(inputs.get("image") or p.get("image_path", "")).strip()
    question    = _to_str(inputs.get("in") or p.get("question",
                          "Describe this image in detail."))
    system      = str(p.get("system_prompt", "You are a helpful vision assistant.")).strip() or None
    temperature = float(p.get("temperature", 0.3))

    if not model_id:
        return {"out": "", "error": "ai.analyze_image: No model selected"}
    if not image_input:
        return {"out": "", "error": "ai.analyze_image: No image path configured"}

    # Load image bytes — support both file path and pre-loaded base64 data URI
    try:
        if image_input.startswith("data:"):
            import base64 as _b64  # noqa: PLC0415
            # data:<mime>;base64,<data>
            header, b64data = image_input.split(",", 1)
            mime_type   = header.split(";")[0].split(":")[1]
            image_bytes = _b64.b64decode(b64data)
        else:
            mime_type   = _MIME_MAP.get(Path(image_input).suffix.lower(), "image/jpeg")
            with open(image_input, "rb") as fh:
                image_bytes = fh.read()
    except Exception as exc:
        return {"out": "", "error": f"Could not load image: {exc}"}

    pm   = _get_pm()
    resp = pm.call_with_failover(
        prompt=question,
        trace_id=f"automate-vision-{uuid.uuid4().hex[:8]}",
        system_prompt=system,
        temperature=temperature,
        model=model_id,
        images=[{"data": image_bytes, "mime_type": mime_type}],
        request_type="generation",
        source="automate-execution",
    )

    if not resp.success:
        return {"out": "", "error": resp.error or "Vision call failed"}
    return {"out": resp.content, "error": ""}


# Image generation

def ai_generate_image(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p            = node.get("properties", {})
    prompt       = _to_str(inputs.get("in", "")).strip()
    model_id     = _to_str(inputs.get("model") or p.get("model",
                            "imagen-3.0-generate-002")).strip()
    save_path    = _to_str(inputs.get("path") or p.get("path", "")).strip()
    aspect_ratio = str(p.get("aspect_ratio", "1:1"))

    if not prompt:
        return {"out": "", "path": "", "count": 0, "error": "No prompt provided"}

    pm              = _get_pm()
    google_provider = getattr(pm, "providers", {}).get("google_ai")
    if not google_provider:
        return {"out": "", "path": "", "count": 0,
                "error": "Google AI provider not configured — image generation requires Google AI"}

    try:
        resp = google_provider.generate_image(
            prompt=prompt,
            trace_id=f"automate-imggen-{uuid.uuid4().hex[:8]}",
            model=model_id,
            aspect_ratio=aspect_ratio,
        )
    except Exception as exc:
        return {"out": "", "path": "", "count": 0, "error": str(exc)}

    if not resp.success:
        return {"out": "", "path": "", "count": 0,
                "error": resp.error or "Image generation failed"}

    images_bytes: list = resp.metadata.get("images", []) if resp.metadata else []
    if not images_bytes:
        return {"out": "", "path": "", "count": 0,
                "error": "No image data returned from provider"}

    if not save_path:
        ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = str(Path(tempfile.gettempdir()) / f"automate_gen_{ts}.png")

    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "wb") as fh:
        fh.write(images_bytes[0])

    return {
        "out":   save_path,
        "path":  save_path,
        "count": len(images_bytes),
        "error": "",
    }


# Text-to-Speech

def ai_text_to_speech(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p         = node.get("properties", {})
    text      = _to_str(inputs.get("in", ""))
    model_id  = str(p.get("model_id", "kokoro")).strip() or "kokoro"
    voice_id  = str(p.get("voice_id", "")).strip() or None
    speed     = float(p.get("speed", 1.0))
    language  = str(p.get("language", "en")).strip() or "en"
    device    = str(p.get("device", "cpu")).strip()
    save_path = _to_str(inputs.get("path") or p.get("path", "")).strip()

    if not text:
        return {"out": "", "path": "", "duration_ms": 0, "error": "No text provided"}

    try:
        from apps.audio.tts_manager import tts_manager  # noqa: PLC0415
    except ImportError as exc:
        return {"out": "", "path": "", "duration_ms": 0,
                "error": f"TTS system unavailable: {exc}"}

    try:
        result = tts_manager.generate_tts(
            text=text, model_id=model_id,
            voice_id=voice_id, speed=speed,
            language=language, device=device,
        )
    except Exception as exc:
        return {"out": "", "path": "", "duration_ms": 0, "error": str(exc)}

    if not save_path:
        ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext       = getattr(result, "format", "wav") or "wav"
        save_path = str(Path(tempfile.gettempdir()) / f"automate_tts_{ts}.{ext}")

    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "wb") as fh:
        fh.write(result.audio_bytes)

    return {
        "out":         save_path,
        "path":        save_path,
        "duration_ms": getattr(result, "duration_ms", 0) or 0,
        "error":       "",
    }


# Speech-to-Text

def ai_speech_to_text(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p          = node.get("properties", {})
    audio_path = _to_str(inputs.get("path") or p.get("path", "")).strip()
    model_id   = str(p.get("model_id", "whisper")).strip() or "whisper"
    language   = str(p.get("language", "")).strip() or None
    device     = str(p.get("device", "cpu")).strip()

    if not audio_path:
        return {"out": "", "language": "", "error": "No audio file path configured"}

    try:
        with open(audio_path, "rb") as fh:
            audio_bytes = fh.read()
    except Exception as exc:
        return {"out": "", "language": "", "error": f"Could not read audio file: {exc}"}

    try:
        from apps.audio.tts_manager import tts_manager  # noqa: PLC0415
    except ImportError as exc:
        return {"out": "", "language": "", "error": f"STT system unavailable: {exc}"}

    try:
        result = tts_manager.transcribe(
            audio_bytes, model_id=model_id,
            language=language, device=device,
        )
    except Exception as exc:
        return {"out": "", "language": "", "error": str(exc)}

    return {
        "out":      result.text,
        "language": result.language or "",
        "error":    "",
    }
