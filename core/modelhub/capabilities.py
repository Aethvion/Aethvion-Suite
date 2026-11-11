"""
core/modelhub/capabilities.py
The vocabulary of the Model Hub: what a model endpoint can do.

A capability is a contract — which inputs a step provides and what kind of thing comes
back.  Workflow nodes ask for a capability; any endpoint that declares it can serve the
request, so the model behind a step is interchangeable.
"""
from __future__ import annotations

# id -> {label, inputs (names an endpoint may use), output kind, description}
CAPABILITIES: dict[str, dict] = {
    "text.generate": {
        "label": "Text generation",
        "inputs": ["prompt", "system_prompt", "image"],
        "output": "text",
        "description": "Prompt in, text out (chat / reasoning models).",
    },
    "image.generate": {
        "label": "Image generation",
        "inputs": ["prompt", "negative_prompt", "image"],
        "output": "image",
        "description": "Text (and optionally a reference image) in, image out.",
    },
    "image.edit": {
        "label": "Image editing",
        "inputs": ["prompt", "image"],
        "output": "image",
        "description": "Image + instruction in, edited image out (upscale, inpaint, restyle…).",
    },
    "image.analyze": {
        "label": "Image understanding",
        "inputs": ["prompt", "image"],
        "output": "text",
        "description": "Image + question in, text out (vision models).",
    },
    "mesh.generate": {
        "label": "3D model generation",
        "inputs": ["prompt", "image"],
        "output": "mesh",
        "description": "Text and/or a reference image in, 3D mesh out.",
    },
    "mesh.texture": {
        "label": "3D texturing",
        "inputs": ["mesh", "prompt", "image"],
        "output": "mesh",
        "description": "Mesh + style prompt / reference image in, textured mesh out.",
    },
    "mesh.process": {
        "label": "3D processing",
        "inputs": ["mesh", "prompt"],
        "output": "mesh",
        "description": "Mesh in, mesh out (decimate, retopologise, convert, rig…).",
    },
    "mesh.render": {
        "label": "3D rendering",
        "inputs": ["mesh"],
        "output": "image",
        "description": "Mesh in, rendered preview image out.",
    },
    "audio.speak": {
        "label": "Text to speech",
        "inputs": ["prompt"],
        "output": "audio",
        "description": "Text in, speech audio out.",
    },
    "audio.generate": {
        "label": "Audio generation",
        "inputs": ["prompt"],
        "output": "audio",
        "description": "Prompt in, sound effect or music out.",
    },
    "audio.transcribe": {
        "label": "Speech to text",
        "inputs": ["audio"],
        "output": "text",
        "description": "Audio in, transcript out.",
    },
    "custom": {
        "label": "Custom",
        "inputs": ["prompt", "image", "mesh", "audio"],
        "output": "file",
        "description": "Anything else — the endpoint definition decides inputs and output.",
    },
}


def is_capability(cap: str) -> bool:
    return cap in CAPABILITIES


def output_kind(cap: str) -> str:
    return CAPABILITIES.get(cap, {}).get("output", "file")
