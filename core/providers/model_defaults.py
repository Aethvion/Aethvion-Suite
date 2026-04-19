"""
core/devtools/model_defaults.py
------------------------------
Logic for loading, merging, and building model registry defaults.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

# We'll import paths later if possible, but for now we can define them or use relative
# In the final version, this should use core.utils.paths
try:
    from core.utils.paths import MODEL_DEFAULTS_DIR, SUGGESTED_MODELS_DIR, MODEL_REGISTRY
except ImportError:
    # Fallback for during development/creation
    ROOT = Path(__file__).parent.parent.parent
    MODEL_DEFAULTS_DIR = ROOT / "core" / "config" / "model_defaults"
    SUGGESTED_MODELS_DIR = MODEL_DEFAULTS_DIR / "suggested"
    MODEL_REGISTRY = ROOT / "data" / "config" / "model_registry.json"

def load_suggested_models() -> Dict[str, Dict[str, Any]]:
    """
    Load all suggested model definitions from the suggested/ folder.
    Returns: { provider_id: { "name": ..., "api_key_env": ..., "models": [...] } }
    """
    suggested = {}
    if not SUGGESTED_MODELS_DIR.exists():
        return suggested
        
    for file in SUGGESTED_MODELS_DIR.glob("*.json"):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Should be { "provider_id": { ... } }
                suggested.update(data)
        except Exception:
            continue
            
    return suggested

def load_defaults() -> Dict[str, List[str]]:
    """
    Load the defaults.json file which lists which models to include by default.
    Returns: { provider_id: [model_id, ...] }
    """
    defaults_path = MODEL_DEFAULTS_DIR / "defaults.json"
    if not defaults_path.exists():
        return {}
        
    try:
        with open(defaults_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def build_initial_registry() -> Dict[str, Any]:
    """
    Create a fresh runtime registry from defaults + suggested definitions.
    """
    suggested = load_suggested_models()
    defaults = load_defaults()
    
    registry = {
        "providers": {},
        "profiles": {
            "chat_profiles": {"default": []},
            "agent_profiles": {"default": []}
        },
        "auto_routing": {
            "chat": {"route_picker": "", "models": {}},
            "agent": {"route_picker": "", "models": {}}
        },
        "local": {
            "name": "Local Models",
            "active": True,
            "chat_config": {"active": True, "priority": 2},
            "agent_config": {"active": True, "priority": 2},
            "models": {}
        }
    }
    
    # Track first chat model for auto-routing default
    first_chat_model = ""
    
    for provider_id, model_ids in defaults.items():
        if provider_id not in suggested:
            continue
            
        prov_info = suggested[provider_id]
        
        # Build provider entry in registry
        registry["providers"][provider_id] = {
            "name": prov_info.get("name", provider_id.title()),
            "api_key_env": prov_info.get("api_key_env", ""),
            "active": True,
            "chat_config": {"active": True, "priority": 1},
            "agent_config": {"active": True if provider_id == "google_ai" else False, "priority": 1},
            "models": {}
        }
        
        # Add the specific models
        for m_id in model_ids:
            # Find the model object in suggested list
            m_obj = next((m for m in prov_info.get("models", []) if m["id"] == m_id), None)
            if not m_obj:
                continue
                
            # Convert m_obj (suggested format) to registry format
            reg_m_obj = {
                "input_cost_per_1m_tokens": m_obj.get("input_cost", 0),
                "output_cost_per_1m_tokens": m_obj.get("output_cost", 0),
                "capabilities": m_obj.get("capabilities", ["CHAT"]),
                "description": m_obj.get("description", "")
            }
            if "image_config" in m_obj:
                reg_m_obj["image_config"] = m_obj["image_config"]
            if "audio_config" in m_obj:
                reg_m_obj["audio_config"] = m_obj["audio_config"]
                
            registry["providers"][provider_id]["models"][m_id] = reg_m_obj
            
            if not first_chat_model and "CHAT" in [c.upper() for c in reg_m_obj["capabilities"]]:
                first_chat_model = m_id
                
    # Finalize auto-routing and profiles
    if first_chat_model:
        registry["auto_routing"]["chat"]["route_picker"] = first_chat_model
        registry["auto_routing"]["agent"]["route_picker"] = first_chat_model
        
        # Populate auto_routing model pools with default enabled true
        for p_id, p_config in registry["providers"].items():
            for m_id, m_config in p_config["models"].items():
                if "CHAT" in [c.upper() for c in m_config["capabilities"]]:
                    registry["auto_routing"]["chat"]["models"][m_id] = {"enabled": True}
                    registry["auto_routing"]["agent"]["models"][m_id] = {"enabled": True}

    return registry

def get_suggested_models_not_in_registry(current_registry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Find all models in suggested/ that are NOT yet in the provided registry.
    Returns a list of model objects with provider_id attached.
    """
    suggested = load_suggested_models()
    existing_models = {} # provider_id -> [model_ids]
    
    for p_id, p_config in current_registry.get("providers", {}).items():
        existing_models[p_id] = list(p_config.get("models", {}).keys())
        
    available = []
    for p_id, prov_info in suggested.items():
        existing = existing_models.get(p_id, [])
        for m_obj in prov_info.get("models", []):
            if m_obj["id"] not in existing:
                # Attach provider info for context
                m_with_ctx = m_obj.copy()
                m_with_ctx["provider_id"] = p_id
                m_with_ctx["provider_name"] = prov_info.get("name", p_id)
                available.append(m_with_ctx)
                
    return available

def merge_model_into_registry(registry: Dict[str, Any], provider_id: str, model_id: str) -> bool:
    """
    Copies a full model definition from suggested files into an existing registry.
    """
    suggested = load_suggested_models()
    if provider_id not in suggested:
        return False
        
    prov_info = suggested[provider_id]
    m_obj = next((m for m in prov_info.get("models", []) if m["id"] == model_id), None)
    if not m_obj:
        return False
        
    # Ensure provider exists in registry
    if provider_id not in registry.get("providers", {}):
        registry.setdefault("providers", {})[provider_id] = {
            "name": prov_info.get("name", provider_id.title()),
            "api_key_env": prov_info.get("api_key_env", ""),
            "active": True,
            "chat_config": {"active": True, "priority": 1},
            "agent_config": {"active": False, "priority": 1},
            "models": {}
        }
    
    # Map to registry format
    reg_m_obj = {
        "input_cost_per_1m_tokens": m_obj.get("input_cost", 0),
        "output_cost_per_1m_tokens": m_obj.get("output_cost", 0),
        "capabilities": m_obj.get("capabilities", ["CHAT"]),
        "description": m_obj.get("description", "")
    }
    if "image_config" in m_obj:
        reg_m_obj["image_config"] = m_obj["image_config"]
    if "audio_config" in m_obj:
        reg_m_obj["audio_config"] = m_obj["audio_config"]
        
    registry["providers"][provider_id]["models"][model_id] = reg_m_obj
    return True
