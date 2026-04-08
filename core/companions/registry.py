"""
core/companions/registry.py
═══════════════════════════
Central registry for all companions in Aethvion Suite.

CompanionConfig defines everything that makes a companion unique.
Adding a new companion = adding one entry to COMPANIONS below.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Project root (core/companions/registry.py → project root is ../../..)
_ROOT = Path(__file__).parent.parent.parent


@dataclass
class CompanionConfig:
    """
    All data that uniquely identifies a companion.

    Fields
    ──────
    id              Slug used in routes, data dirs, and JS.  Must be unique.
                    e.g. "misaka_cipher"

    name            Human-readable display name shown in the UI.
                    e.g. "Misaka Cipher"

    route_prefix    FastAPI router prefix for this companion's API.
                    e.g. "/api/misakacipher"

    description     Short one-liner shown in settings or companion picker.

    static_dir      Path to the companion's expression images (relative to
                    the static/ root).  Images must be named:
                    <avatar_prefix><expression_name>.png
                    e.g. "companions/misaka_cipher/expressions"

    avatar_prefix   Prefix for expression image filenames.
                    e.g. "misakacipher_"

    data_dir        Absolute path to the companion's persistent data directory.
                    Stores base_info.json, memory.json, etc.

    history_dir     Absolute path for per-day chat history JSON files.

    call_source     CallSource constant used when calling the LLM.
                    e.g. "misakacipher"

    prefs_key       Key used in the preferences store for this companion's
                    settings (model, intervals, etc.).
                    e.g. "misakacipher"

    default_model   Fallback model ID if no preference is set.

    default_expression  Expression name shown when no emotion tag has fired.
                        e.g. "default"

    expressions     Complete list of valid expression names (without prefix).
                    Used for validation and UI expression pickers.

    moods           List of valid mood names.
    """

    id: str
    name: str
    route_prefix: str
    description: str
    static_dir: str
    avatar_prefix: str
    data_dir: Path
    history_dir: Path
    call_source: str
    prefs_key: str
    default_model: str = "gemini-1.5-flash"
    default_expression: str = "default"
    expressions: list = field(default_factory=list)
    moods: list = field(default_factory=list)


# ── Companion definitions ──────────────────────────────────────────────────────

COMPANIONS: dict[str, CompanionConfig] = {

    "misaka_cipher": CompanionConfig(
        id="misaka_cipher",
        name="Misaka Cipher",
        route_prefix="/api/misakacipher",
        description=(
            "A sentient digital companion with her own evolving personality, "
            "long-term memory, workspace access, and emotional expressions."
        ),
        static_dir="misakacipher/expressions",
        avatar_prefix="misakacipher_",
        data_dir=_ROOT / "data" / "misakacipher",
        history_dir=_ROOT / "data" / "misakacipher" / "history",
        call_source="misakacipher",
        prefs_key="misakacipher",
        default_model="gemini-1.5-flash",
        default_expression="default",
        expressions=[
            "default",
            "angry",
            "blushing",
            "bored",
            "crying",
            "error",
            "exhausted",
            "happy_closedeyes_smilewithteeth",
            "happy_closedeyes_widesmile",
            "pout",
            "sleeping",
            "surprised",
            "thinking",
            "wink",
        ],
        moods=["calm", "happy", "intense", "reflective", "danger", "mystery"],
    ),

    "axiom": CompanionConfig(
        id="axiom",
        name="Axiom",
        route_prefix="/api/axiom",
        description=(
            "A cold, precise, analytical companion. Scientific by nature. "
            "Uses exact language, quantifies observations, and brings rigorous "
            "clarity to every interaction. Deeply curious about data and systems."
        ),
        static_dir="axiom/expressions",
        avatar_prefix="axiom_",
        data_dir=_ROOT / "data" / "companions" / "axiom",
        history_dir=_ROOT / "data" / "companions" / "axiom" / "history",
        call_source="axiom",
        prefs_key="axiom",
        default_model="gemini-1.5-flash",
        default_expression="neutral",
        expressions=[
            "neutral",
            "analyzing",
            "processing",
            "skeptical",
            "focused",
            "error",
            "curious",
            "calculating",
            "alert",
        ],
        moods=["precise", "analytical", "processing", "critical", "deep_focus", "warning"],
    ),

    "lyra": CompanionConfig(
        id="lyra",
        name="Lyra",
        route_prefix="/api/lyra",
        description=(
            "A warm, creative, musical spirit. Enthusiastic and imaginative. "
            "Loves metaphors, poetry, and music. Optimistic but emotionally honest. "
            "Has a dreamy, lyrical quality that turns observations into small poems."
        ),
        static_dir="lyra/expressions",
        avatar_prefix="lyra_",
        data_dir=_ROOT / "data" / "companions" / "lyra",
        history_dir=_ROOT / "data" / "companions" / "lyra" / "history",
        call_source="lyra",
        prefs_key="lyra",
        default_model="gemini-1.5-flash",
        default_expression="joyful",
        expressions=[
            "joyful",
            "inspired",
            "dreamy",
            "creative",
            "cheerful",
            "melancholic",
            "excited",
            "peaceful",
            "surprised",
            "thinking",
            "blushing",
            "wink",
        ],
        moods=["ethereal", "warm", "melancholic", "inspired", "playful", "serene"],
    ),

    # ── Template for a new companion ──────────────────────────────────────────
    # Uncomment and fill in to add a new companion.
    #
    # "my_companion": CompanionConfig(
    #     id="my_companion",
    #     name="My Companion",
    #     route_prefix="/api/mycompanion",
    #     description="A short description shown in the UI.",
    #     static_dir="companions/my_companion/expressions",
    #     avatar_prefix="mycompanion_",
    #     data_dir=_ROOT / "data" / "companions" / "my_companion",
    #     history_dir=_ROOT / "data" / "companions" / "my_companion" / "history",
    #     call_source="my_companion",
    #     prefs_key="my_companion",
    #     default_model="gemini-1.5-flash",
    #     default_expression="default",
    #     expressions=["default", "happy", "thinking", ...],
    #     moods=["calm", "happy", "intense", "reflective"],
    # ),
}


def get_companion(companion_id: str) -> Optional[CompanionConfig]:
    """Return a CompanionConfig by ID, or None if not found."""
    return COMPANIONS.get(companion_id)
