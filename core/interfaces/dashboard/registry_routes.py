"""
Misaka Cipher - Registry Routes
API endpoints for managing the Model Registry (config/model_registry.json)
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Request

from core.utils import get_logger
from core.utils.model_downloader import ModelDownloader
from core.utils.paths import MODEL_REGISTRY, SUGGESTED_API_MODELS, SUGGESTED_LOCAL_MODELS, LOCAL_MODELS_GGUF

logger = get_logger(__name__)

router = APIRouter(prefix="/api/registry", tags=["registry"])

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
REGISTRY_PATH        = MODEL_REGISTRY
SUGGESTED_API_PATH   = SUGGESTED_API_MODELS
SUGGESTED_LOCAL_PATH = SUGGESTED_LOCAL_MODELS
GGUF_DIR             = LOCAL_MODELS_GGUF
ENV_PATH = PROJECT_ROOT / ".env"
ENV_EXAMPLE_PATH = PROJECT_ROOT / ".env.example"


# ===== .env Management =====

@router.get("/env/status")
async def get_env_status():
    """Check if .env exists and return masked key info."""
    try:
        exists = ENV_PATH.exists()
        keys = []

        if exists:
            content = ENV_PATH.read_text(encoding="utf-8")
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    name, _, value = line.partition("=")
                    name = name.strip()
                    value = value.strip()
                    has_value = bool(value) and not value.startswith("your_")
                    masked = (value[:4] + "****") if has_value and len(value) > 4 else ("****" if has_value else "")
                    keys.append({"name": name, "has_value": has_value, "masked_value": masked})
        else:
            # Show expected keys from .env.example
            if ENV_EXAMPLE_PATH.exists():
                content = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        name, _, _ = line.partition("=")
                        keys.append({"name": name.strip(), "has_value": False, "masked_value": ""})

        return {"exists": exists, "keys": keys}
    except Exception as e:
        logger.error(f"Failed to get env status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/env/create")
async def create_env():
    """Create .env from .env.example if it doesn't exist."""
    try:
        if ENV_PATH.exists():
            return {"status": "exists", "message": ".env already exists"}

        if not ENV_EXAMPLE_PATH.exists():
            raise HTTPException(status_code=404, detail=".env.example not found")

        # Copy .env.example to .env
        content = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")
        ENV_PATH.write_text(content, encoding="utf-8")
        logger.info("Created .env from .env.example")
        return {"status": "created"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create .env: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/env/update")
async def update_env_key(data: Dict[str, Any]):
    """Update a specific key in .env."""
    try:
        key_name = data.get("key")
        key_value = data.get("value", "")

        if not key_name:
            raise HTTPException(status_code=400, detail="'key' is required")

        if not ENV_PATH.exists():
            raise HTTPException(status_code=404, detail=".env file not found. Create it first.")

        content = ENV_PATH.read_text(encoding="utf-8")
        lines = content.splitlines()

        # Find and update the key, or append it
        found = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "=" in stripped:
                name, _, _ = stripped.partition("=")
                if name.strip() == key_name:
                    lines[i] = f"{key_name}={key_value}"
                    found = True
                    break

        if not found:
            lines.append(f"\n{key_name}={key_value}")

        ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.info(f"Updated .env key: {key_name}")

        # Reload into current process environment
        os.environ[key_name] = key_value

        return {"status": "success", "key": key_name}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update .env key: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== Suggested Models =====

@router.get("/suggested")
async def get_all_suggested_models():
    """Get all suggested models for all providers (API + local GGUF combined)."""
    try:
        result = {}
        if SUGGESTED_API_PATH.exists():
            result = json.loads(SUGGESTED_API_PATH.read_text(encoding="utf-8"))
        if SUGGESTED_LOCAL_PATH.exists():
            local_models = json.loads(SUGGESTED_LOCAL_PATH.read_text(encoding="utf-8"))
            # local_models is a flat list; wrap it under "local" key for the registry modal
            result["local"] = local_models if isinstance(local_models, list) else local_models.get("local", [])
        return result
    except Exception as e:
        logger.error(f"Error loading suggested models: {e}")
        return {}



def _load_registry() -> Dict[str, Any]:
    """Load model registry from disk."""
    try:
        if REGISTRY_PATH.exists():
            with open(REGISTRY_PATH, 'r') as f:
                data = json.load(f)
                # Ensure basic structure
                if "providers" not in data: data["providers"] = {}
                if "profiles" not in data: data["profiles"] = {"chat_profiles": {}, "agent_profiles": {}}
                if "auto_routing" not in data: 
                    data["auto_routing"] = {
                        "chat": {"route_picker": "gemini-3-flash-preview", "models": {}},
                        "agent": {"route_picker": "gemini-3-flash-preview", "models": {}}
                    }
                return data
        
        # Return default structure if file doesn't exist
        return {
            "providers": {}, 
            "profiles": {
                "chat_profiles": {"default": []}, 
                "agent_profiles": {"default": []}
            },
            "auto_routing": {
                "chat": {"route_picker": "gemini-3-flash-preview", "models": {}},
                "agent": {"route_picker": "gemini-3-flash-preview", "models": {}}
            }
        }
    except Exception as e:
        logger.error(f"Failed to load model registry: {e}")
        return {
            "providers": {}, 
            "profiles": {"chat_profiles": {}, "agent_profiles": {}},
            "auto_routing": {"chat": {}, "agent": {}}
        }


def _save_registry(data: Dict[str, Any]) -> None:
    """Save model registry to disk."""
    # Fail-safe: Strip redundant 'id' and 'key' fields from model objects before saving
    if "providers" in data:
        for provider in data["providers"].values():
            if "models" in provider:
                cleaned_models = {}
                for model_key, model_info in provider["models"].items():
                    if isinstance(model_info, dict):
                        # Clean the model info object
                        cleaned_info = {k: v for k, v in model_info.items() if k not in ["id", "key"]}
                        cleaned_models[model_key] = cleaned_info
                    else:
                        cleaned_models[model_key] = model_info
                provider["models"] = cleaned_models

    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_PATH, 'w') as f:
        json.dump(data, f, indent=4)
    logger.info("Model registry saved to disk (cleaned)")


@router.get("")
async def get_registry():
    """Get the full model registry."""
    try:
        registry = _load_registry()
        return registry
    except Exception as e:
        logger.error(f"Failed to get registry: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def update_registry(updates: Dict[str, Any], request: Request):
    """Update the model registry (full replace)."""
    try:
        _save_registry(updates)
        if hasattr(request.app.state, 'nexus'):
            request.app.state.nexus.reload_config()
        return {"status": "success", "registry": updates}
    except Exception as e:
        logger.error(f"Failed to update registry: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/available_types")
async def get_available_types():
    """Get list of supported provider types."""
    return ["google_ai", "openai", "grok", "anthropic", "local"]


@router.post("/providers")
async def add_provider(provider_data: Dict[str, Any], request: Request):
    """Add a new supported provider to the registry by type."""
    try:
        provider_type = provider_data.get("type")
        if not provider_type:
            raise HTTPException(status_code=400, detail="Provider 'type' is required")
        
        supported_types = ["google_ai", "openai", "grok", "anthropic", "local"]
        if provider_type not in supported_types:
            raise HTTPException(status_code=400, detail=f"Unsupported provider type: {provider_type}")
            
        registry = _load_registry()
        providers = registry.get("providers", {})
        
        if provider_type in providers:
            raise HTTPException(status_code=409, detail=f"Provider '{provider_type}' already exists")
            
        # Default templates
        defaults = {
            "google_ai": {
                "name": "Google AI",
                "api_key_env": "GOOGLE_AI_API_KEY",
                "active": True,
                "chat_config": {"active": True, "priority": 1},
                "agent_config": {"active": True, "priority": 1},
                "models": {}
            },
            "openai": {
                "name": "OpenAI",
                "api_key_env": "OPENAI_API_KEY",
                "active": True,
                "chat_config": {"active": True, "priority": 1},
                "agent_config": {"active": False, "priority": 1},
                "models": {}
            },
            "grok": {
                "name": "xAI Grok",
                "api_key_env": "GROK_API_KEY",
                "active": True,
                "chat_config": {"active": True, "priority": 1},
                "agent_config": {"active": False, "priority": 1},
                "models": {}
            },
            "anthropic": {
                "name": "Anthropic",
                "api_key_env": "ANTHROPIC_API_KEY",
                "active": True,
                "chat_config": {"active": True, "priority": 1},
                "agent_config": {"active": False, "priority": 1},
                "models": {}
            },
            "local": {
                "name": "Local AI",
                "api_key_env": "",
                "active": False,
                "chat_config": {"active": False, "priority": 1},
                "agent_config": {"active": False, "priority": 1},
                "models": {}
            }
        }
        
        providers[provider_type] = defaults[provider_type]
        registry["providers"] = providers
        _save_registry(registry)
        
        if hasattr(request.app.state, 'nexus'):
            request.app.state.nexus.reload_config()
            
        logger.info(f"Added provider type '{provider_type}' to registry")
        return {"status": "success", "provider": providers[provider_type]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add provider: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/provider/{provider_name}")
async def update_provider(provider_name: str, updates: Dict[str, Any], request: Request):
    """Update a single provider's settings."""
    try:
        registry = _load_registry()
        providers = registry.get("providers", {})
        
        if provider_name not in providers:
            raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")
        
        # Update only the fields provided
        for key, value in updates.items():
            providers[provider_name][key] = value
        
        registry["providers"] = providers
        _save_registry(registry)
        
        if hasattr(request.app.state, 'nexus'):
            request.app.state.nexus.reload_config()
            
        return {"status": "success", "provider": provider_name, "config": providers[provider_name]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update provider {provider_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== Model CRUD =====

@router.post("/provider/{provider_name}/models")
async def add_model(provider_name: str, model_data: Dict[str, Any], request: Request):
    """Add a model to a provider."""
    try:
        registry = _load_registry()
        providers = registry.get("providers", {})

        if provider_name not in providers:
            raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")

        model_key = model_data.get("key")
        if not model_key:
            raise HTTPException(status_code=400, detail="Model 'key' is required")

        models = providers[provider_name].setdefault("models", {})
        if model_key in models:
            raise HTTPException(status_code=409, detail=f"Model '{model_key}' already exists")

        # Build model entry (strip the key field, it's used as the dict key)
        entry = {k: v for k, v in model_data.items() if k != "key"}
        models[model_key] = entry

        _save_registry(registry)
        if hasattr(request.app.state, 'nexus'):
            request.app.state.nexus.reload_config()
            
        logger.info(f"Added model '{model_key}' to provider '{provider_name}'")
        return {"status": "success", "provider": provider_name, "model_key": model_key, "model": entry}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/provider/{provider_name}/models/{model_key}")
async def update_model(provider_name: str, model_key: str, model_data: Dict[str, Any], request: Request):
    """Update a model within a provider."""
    try:
        registry = _load_registry()
        providers = registry.get("providers", {})

        if provider_name not in providers:
            raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")

        models = providers[provider_name].get("models", {})
        if model_key not in models:
            raise HTTPException(status_code=404, detail=f"Model '{model_key}' not found")

        # Merge updates into existing model
        for k, v in model_data.items():
            models[model_key][k] = v

        _save_registry(registry)
        if hasattr(request.app.state, 'nexus'):
            request.app.state.nexus.reload_config()
            
        logger.info(f"Updated model '{model_key}' for provider '{provider_name}'")
        return {"status": "success", "provider": provider_name, "model_key": model_key, "model": models[model_key]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/provider/{provider_name}/models/{model_key}")
async def delete_model(provider_name: str, model_key: str, request: Request):
    """Remove a model from a provider."""
    try:
        registry = _load_registry()
        providers = registry.get("providers", {})

        if provider_name not in providers:
            raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")

        models = providers[provider_name].get("models", {})
        if model_key not in models:
            raise HTTPException(status_code=404, detail=f"Model '{model_key}' not found")

        del models[model_key]
        _save_registry(registry)
        if hasattr(request.app.state, 'nexus'):
            request.app.state.nexus.reload_config()
            
        logger.info(f"Deleted model '{model_key}' from provider '{provider_name}'")
        return {"status": "success", "provider": provider_name, "model_key": model_key}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/chat")
async def get_chat_models():
    """Get flat list of all chat-capable models for the dropdown."""
    try:
        registry = _load_registry()
        chat_models = []

        for provider_name, config in registry.get("providers", {}).items():
            models = config.get("models", {})
            for model_id, model_info in models.items():
                if isinstance(model_info, str):
                    continue

                capabilities = model_info.get("capabilities", [])
                # Normalize capabilities to lowercase for internal checks
                caps_lower = [c.lower() for c in capabilities]
                # Only include models that explicitly have 'chat' capability
                if "chat" not in caps_lower:
                    continue

                chat_models.append({
                    "id": model_id,
                    "provider": provider_name,
                    "capabilities": capabilities,
                    "input_cost_per_1m_tokens": model_info.get("input_cost_per_1m_tokens", 0),
                    "output_cost_per_1m_tokens": model_info.get("output_cost_per_1m_tokens", 0),
                    "description": model_info.get("description", model_info.get("notes", "")),
                })

        # Add profile groups
        profiles = registry.get("profiles", {})
        chat_profiles = profiles.get("chat_profiles", {})
        agent_profiles = profiles.get("agent_profiles", {})

        # Sort by model ID
        chat_models.sort(key=lambda m: m["id"])
        
        return {
            "models": chat_models, 
            "chat_profiles": chat_profiles,
            "agent_profiles": agent_profiles
        }
    except Exception as e:
        logger.error(f"Failed to get chat models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== Auto Routing Configuration =====

def _get_chat_model_ids(registry: Dict[str, Any]) -> Dict[str, Dict]:
    """Return all models with 'chat' capability: {model_id: {description, provider}}."""
    result = {}
    for provider_name, config in registry.get("providers", {}).items():
        for model_id, model_info in config.get("models", {}).items():
            if not isinstance(model_info, dict):
                continue
            caps = model_info.get("capabilities", [])
            caps_lower = [c.lower() for c in caps]
            if "chat" in caps_lower:
                result[model_id] = {
                    "description": model_info.get("description", ""),
                    "provider": provider_name,
                }
    return result


def _seed_auto_routing(registry: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure auto_routing contains all chat models. Missing entries are added (enabled=True).
    Models that lose their 'chat' capability are NOT auto-removed (user may re-add it)."""
    chat_models = _get_chat_model_ids(registry)
    auto = registry.setdefault("auto_routing", {})

    for profile_type in ("chat", "agent"):
        profile = auto.setdefault(profile_type, {})
        profile.setdefault("route_picker", next(iter(chat_models), ""))
        pool = profile.setdefault("models", {})
        for model_id in chat_models:
            if model_id not in pool:
                pool[model_id] = {"enabled": True}

    return registry


@router.get("/auto-routing")
async def get_auto_routing():
    """Get the auto routing config, seeding any new chat-capable models that are missing."""
    try:
        registry = _load_registry()
        registry = _seed_auto_routing(registry)
        # Persist any newly seeded models
        _save_registry(registry)

        # Enrich response with descriptions from provider models
        chat_models = _get_chat_model_ids(registry)
        auto = registry.get("auto_routing", {})

        enriched = {}
        for profile_type in ("chat", "agent"):
            profile = auto.get(profile_type, {})
            pool = profile.get("models", {})
            enriched_pool = {}
            for model_id, cfg in pool.items():
                enriched_pool[model_id] = {
                    **cfg,
                    "description": chat_models.get(model_id, {}).get("description", ""),
                    "provider": chat_models.get(model_id, {}).get("provider", ""),
                }
            enriched[profile_type] = {
                "route_picker": profile.get("route_picker", ""),
                "models": enriched_pool,
            }

        return {"auto_routing": enriched, "all_chat_models": list(chat_models.keys())}
    except Exception as e:
        logger.error(f"Failed to get auto routing config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auto-routing")
async def save_auto_routing(data: Dict[str, Any], request: Request):
    """Save auto routing config (route_picker + model toggles per profile type)."""
    try:
        registry = _load_registry()
        registry["auto_routing"] = data.get("auto_routing", registry.get("auto_routing", {}))
        _save_registry(registry)
        if hasattr(request.app.state, 'nexus'):
            request.app.state.nexus.reload_config()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Failed to save auto routing config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== Local Model Management =====

@router.get("/local/models/status")
async def get_local_models_status():
    """Check which local models are downloaded."""
    try:
        local_dir = GGUF_DIR
        if not local_dir.exists():
            return {"models": {}}
        
        status = {}
        # Get all .gguf files
        for f in local_dir.glob("*.gguf"):
            status[f.name] = {
                "exists": True,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                "path": str(f)
            }
        return {"models": status}
    except Exception as e:
        logger.error(f"Failed to get local models status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/local/suggested")
async def get_suggested_local_models():
    """Get list of recommended GGUF local models."""
    try:
        if not SUGGESTED_LOCAL_PATH.exists():
            return {"suggested": []}
        data = json.loads(SUGGESTED_LOCAL_PATH.read_text(encoding="utf-8"))
        models = data if isinstance(data, list) else data.get("local", [])
        return {"suggested": models}
    except Exception as e:
        logger.error(f"Error loading local suggested models: {e}")
        return {"suggested": []}


@router.post("/local/models/download")
async def download_local_model(data: Dict[str, Any]):
    """Initiate a model download from Hugging Face."""
    try:
        repo_id = data.get("repo_id")
        filename = data.get("filename")
        
        if not repo_id or not filename:
            raise HTTPException(status_code=400, detail="repo_id and filename are required")
            
        downloader = ModelDownloader()
        # This will be synchronous for now, might need background task if it takes too long
        # but for a 1B model it should be okay-ish if the user waits
        path = downloader.download_model(repo_id, filename)
        
        return {
            "status": "success",
            "message": f"Model {filename} downloaded successfully",
            "path": str(path)
        }
    except Exception as e:
        logger.error(f"Model download failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/local/models/delete")
async def delete_local_model(data: Dict[str, Any]):
    """Delete a local model file."""
    try:
        filename = data.get("filename")
        if not filename:
            raise HTTPException(status_code=400, detail="filename is required")
            
        local_dir = GGUF_DIR
        model_path = local_dir / filename
        
        if not model_path.exists():
            raise HTTPException(status_code=404, detail="Model file not found")
            
        if not str(model_path).startswith(str(local_dir)):
            raise HTTPException(status_code=400, detail="Invalid path")
            
        # 1. Unregister if it exists in registry
        try:
            registry = _load_registry()
            if "local" in registry.get("providers", {}):
                models = registry["providers"]["local"].get("models", {})
                if filename in models:
                    del models[filename]
                    
                    # Also remove from auto_routing
                    auto_routing = registry.get("auto_routing", {})
                    for category in ["chat", "agent"]:
                        if category in auto_routing:
                            cat_models = auto_routing[category].get("models", {})
                            if filename in cat_models:
                                del cat_models[filename]
                    
                    _save_registry(registry)
                    logger.info(f"Unregistered model {filename} during deletion")
        except Exception as reg_err:
            logger.error(f"Failed to unregister model {filename} during deletion: {reg_err}")
            # Continue with file deletion anyway
            
        # 2. Delete the file
        model_path.unlink()
        return {"status": "success", "message": f"Model {filename} deleted and unregistered"}
    except Exception as e:
        logger.error(f"Failed to delete model: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@router.post("/local/models/register")
async def register_local_model(data: Dict[str, Any], request: Request):
    """Register a local GGUF model in the registry."""
    try:
        filename = data.get("filename")
        if not filename:
            raise HTTPException(status_code=400, detail="filename is required")
            
        # 1. Load registry with default structure safety
        registry = _load_registry()
            
        # 2. Ensure local provider exists and is active
        providers = registry.get("providers", {})
        if "local" not in providers:
            providers["local"] = {
                "name": "Local Models",
                "active": True,
                "chat_config": {"active": True, "priority": 2},
                "agent_config": {"active": True, "priority": 2},
                "models": {}
            }
        else:
            # Ensure it's active even if it existed
            providers["local"]["active"] = True
            if "chat_config" in providers["local"]:
                providers["local"]["chat_config"]["active"] = True
            if "agent_config" in providers["local"]:
                providers["local"]["agent_config"]["active"] = True
                
        # 3. Add model if not exists
        local_models = providers["local"].setdefault("models", {})
        if filename not in local_models:
            local_models[filename] = {
                "input_cost_per_1m_tokens": 0,
                "output_cost_per_1m_tokens": 0,
                "capabilities": ["CHAT"],
                "description": f"Local model: {filename}",
                "local_path": filename
            }
            
        # 4. Sync with auto_routing using our seed helper
        registry = _seed_auto_routing(registry)
                    
        # 5. Save registry
        _save_registry(registry)
            
        # 6. Reload config
        if hasattr(request.app.state, 'nexus'):
            request.app.state.nexus.reload_config()
            
        return {"status": "success", "message": f"Model {filename} registered successfully"}
        
    except Exception as e:
        logger.error(f"Failed to register local model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reload")
async def reload_registry_config(request: Request):
    """Force reload of model registry and providers config."""
    try:
        if hasattr(request.app.state, 'nexus'):
            request.app.state.nexus.reload_config()
        return {"status": "success", "message": "Configuration reloaded"}
    except Exception as e:
        logger.error(f"Failed to reload config: {e}")
        raise HTTPException(status_code=500, detail=str(e))
