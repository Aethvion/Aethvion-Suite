"""
Aethvion Suite - Registry Routes
API endpoints for managing the Model Registry (config/model_registry.json)
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Any

# Windows window suppression
CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
from fastapi import APIRouter, HTTPException, Request

from core.utils import get_logger
from core.utils.model_downloader import ModelDownloader
from core.utils.paths import MODEL_REGISTRY, SUGGESTED_API_MODELS, SUGGESTED_LOCAL_MODELS, LOCAL_MODELS_GGUF, SYSTEM_SPECS

logger = get_logger(__name__)

router = APIRouter(prefix="/api/registry", tags=["registry"])

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
REGISTRY_PATH        = MODEL_REGISTRY
SUGGESTED_API_PATH   = SUGGESTED_API_MODELS
SUGGESTED_LOCAL_PATH = SUGGESTED_LOCAL_MODELS
GGUF_DIR             = LOCAL_MODELS_GGUF
ENV_PATH = PROJECT_ROOT / ".env"
ENV_EXAMPLE_PATH = PROJECT_ROOT / ".env.example"
SYSTEM_SPECS_PATH = SYSTEM_SPECS


# ===== .env Management =====

@router.get("/env/status")
async def get_env_status():
    """Check if .env exists and return masked key info, merged with .env.example."""
    try:
        exists = ENV_PATH.exists()
        keys_dict = {}  # name -> entry (ordered)

        # Load expected keys from .env.example first (defines canonical order)
        if ENV_EXAMPLE_PATH.exists():
            for line in ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    name, _, _ = line.partition("=")
                    name = name.strip()
                    if name:
                        keys_dict[name] = {"name": name, "has_value": False, "masked_value": ""}

        # Overlay actual values from .env if it exists
        if exists:
            for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    name, _, value = line.partition("=")
                    name = name.strip()
                    value = value.strip()
                    if not name:
                        continue
                    has_value = bool(value) and not value.startswith("your_")
                    masked = (value[:4] + "****") if has_value and len(value) > 4 else ("****" if has_value else "")
                    keys_dict[name] = {"name": name, "has_value": has_value, "masked_value": masked}

        # Filter out non-key entries like PORT
        skip = {"PORT"}
        keys = [v for k, v in keys_dict.items() if k not in skip]

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
    return ["google_ai", "openai", "anthropic", "grok", "groq", "mistral", "openrouter", "local"]



@router.post("/providers")
async def add_provider(provider_data: Dict[str, Any], request: Request):
    """Add a new supported provider to the registry by type."""
    try:
        provider_type = provider_data.get("type")
        if not provider_type:
            raise HTTPException(status_code=400, detail="Provider 'type' is required")
        
        supported_types = ["google_ai", "openai", "anthropic", "grok", "groq", "mistral", "openrouter", "local"]
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
            "groq": {
                "name": "Groq",
                "api_key_env": "GROQ_API_KEY",
                "active": True,
                "chat_config": {"active": True, "priority": 1},
                "agent_config": {"active": False, "priority": 1},
                "models": {}
            },
            "mistral": {
                "name": "Mistral AI",
                "api_key_env": "MISTRAL_API_KEY",
                "active": True,
                "chat_config": {"active": True, "priority": 1},
                "agent_config": {"active": False, "priority": 1},
                "models": {}
            },
            "openrouter": {
                "name": "OpenRouter",
                "api_key_env": "OPENROUTER_API_KEY",
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
    """Ensure auto_routing.chat contains all chat-capable models. Missing entries are added (enabled=True)."""
    chat_models = _get_chat_model_ids(registry)
    auto = registry.setdefault("auto_routing", {})

    profile = auto.setdefault("chat", {})
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

        chat_profile = auto.get("chat", {})
        pool = chat_profile.get("models", {})
        enriched_pool = {}
        for model_id, cfg in pool.items():
            enriched_pool[model_id] = {
                **cfg,
                "description": chat_models.get(model_id, {}).get("description", ""),
                "provider": chat_models.get(model_id, {}).get("provider", ""),
            }

        enriched = {
            "chat": {
                "route_picker": chat_profile.get("route_picker", ""),
                "models": enriched_pool,
            }
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
        registry = _load_registry()
        registry_changed = False

        # Ensure "local" provider exists in the registry
        if "local" not in registry:
            registry["local"] = {
                "name": "Local Models",
                "active": True,
                "chat_config": {"active": True, "priority": 2},
                "agent_config": {"active": True, "priority": 2},
                "models": {}
            }
            registry_changed = True

        local_models = registry["local"].setdefault("models", {})

        # Get all .gguf files
        for f in local_dir.glob("*.gguf"):
            status[f.name] = {
                "exists": True,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                "path": str(f)
            }

            # Auto-register if not already in the registry
            if f.name not in local_models:
                local_models[f.name] = {
                    "input_cost_per_1m_tokens": 0,
                    "output_cost_per_1m_tokens": 0,
                    "capabilities": ["CHAT"],
                    "description": f"Local model: {f.name}",
                    "local_path": f.name
                }
                logger.info(f"Auto-registered local model: {f.name}")
                registry_changed = True

        if registry_changed:
            _save_registry(registry)

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


@router.post("/local/models/download/stream")
async def download_local_model_stream(request: Request):
    """Download a GGUF from HuggingFace with SSE byte-level progress."""
    import asyncio
    import threading
    from fastapi.responses import StreamingResponse

    data = await request.json()
    repo_id  = (data.get("repo_id")  or "").strip()
    filename = (data.get("filename") or "").strip()

    if not repo_id or not filename:
        raise HTTPException(400, "repo_id and filename are required")

    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()

    def _download():
        try:
            import requests
            from huggingface_hub import hf_hub_url

            url  = hf_hub_url(repo_id=repo_id, filename=filename)
            dest = GGUF_DIR / filename
            GGUF_DIR.mkdir(parents=True, exist_ok=True)
            tmp  = dest.with_suffix(dest.suffix + ".part")

            with requests.get(url, stream=True, timeout=60, allow_redirects=True) as r:
                r.raise_for_status()
                total      = int(r.headers.get("content-length", 0))
                downloaded = 0
                last_pct   = -1

                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total > 0:
                                pct = min(99, round(downloaded / total * 100, 1))
                                if pct != last_pct:
                                    last_pct = pct
                                    loop.call_soon_threadsafe(q.put_nowait, {
                                        "pct": pct,
                                        "downloaded_mb": round(downloaded / 1024 / 1024, 1),
                                        "total_mb":      round(total      / 1024 / 1024, 1),
                                    })

            tmp.rename(dest)
            loop.call_soon_threadsafe(q.put_nowait, {
                "done": True, "success": True, "pct": 100, "filename": filename,
            })
        except Exception as exc:
            loop.call_soon_threadsafe(q.put_nowait, {
                "done": True, "success": False, "error": str(exc),
            })

    threading.Thread(target=_download, daemon=True).start()

    async def _generate():
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=30.0)
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'heartbeat': True})}\n\n"
                continue
            yield f"data: {json.dumps(msg)}\n\n"
            if msg.get("done"):
                break

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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


# ── Local inference config (n_gpu_layers, n_ctx, n_threads) ──────────────────

from core.utils.paths import LOCAL_INFERENCE_CONFIG as _INFERENCE_CFG_PATH
from core.ai.call_contexts import CallSource

def _load_icfg() -> dict:
    if _INFERENCE_CFG_PATH.exists():
        try:
            return json.loads(_INFERENCE_CFG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"n_gpu_layers": -1, "n_ctx": 4096, "n_threads": -1}


def _save_icfg(cfg: dict):
    _INFERENCE_CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _INFERENCE_CFG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


@router.get("/local/inference-config")
async def get_inference_config():
    return _load_icfg()


@router.post("/local/inference-config")
async def save_inference_config(request: Request):
    data = await request.json()
    cfg  = _load_icfg()
    for key in ("n_gpu_layers", "n_ctx", "n_threads"):
        if key in data:
            cfg[key] = int(data[key])
    _save_icfg(cfg)
    return {"success": True, **cfg}


@router.get("/local/gpu-status")
async def get_gpu_status():
    """Report GPU availability for local inference."""
    result = {
        "llama_cuda": False,
        "cuda_available": False,
        "gpu_name": None,
        "vram_gb": None,
    }

    # 1 — Register CUDA DLL dirs so llama_cpp can load on Windows
    try:
        from core.providers.local_provider import _register_cuda_dll_dirs
        _register_cuda_dll_dirs()
    except Exception:
        pass

    # 2 — Check if CUDA llama-cpp build is active
    try:
        import llama_cpp
        result["llama_cuda"] = bool(
            getattr(llama_cpp, "llama_supports_gpu_offload", lambda: False)()
        )
    except Exception:
        pass

    # 2 — Detect GPU via nvidia-smi (works on Windows without torch)
    try:
        proc = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
            creationflags=CREATE_NO_WINDOW
        )
        if proc.returncode == 0 and proc.stdout.strip():
            parts = [p.strip() for p in proc.stdout.strip().split(",")]
            result["cuda_available"] = True
            result["gpu_name"]       = parts[0]
            result["vram_gb"]        = round(int(parts[1]) / 1024, 1)
    except Exception:
        pass

    # 3 — Fallback: torch (if nvidia-smi wasn't found / failed)
    if not result["cuda_available"]:
        try:
            import torch
            result["cuda_available"] = torch.cuda.is_available()
            if result["cuda_available"]:
                result["gpu_name"] = torch.cuda.get_device_name(0)
                result["vram_gb"]  = round(
                    torch.cuda.get_device_properties(0).total_memory / 1e9, 1
                )
        except Exception:
            pass

    return result


from core.utils.paths import SYSTEM_SPECS
SYSTEM_SPECS_PATH = SYSTEM_SPECS


@router.get("/local/system-specs")
async def get_system_specs():
    """Detect and cache system hardware specs (CPU, GPU, RAM) to data/system_specs.json."""
    import datetime
    import platform as _platform

    specs: dict = {
        "cpu_name": "Unknown",
        "cpu_cores": 0,
        "cpu_threads": 0,
        "ram_total_gb": 0.0,
        "ram_available_gb": 0.0,
        "gpu_name": None,
        "vram_gb": 0.0,
        "cuda_available": False,
        "last_updated": datetime.datetime.now().isoformat(),
    }

    # ── CPU & RAM via psutil ─────────────────────────────────────────────────
    try:
        import psutil
        specs["cpu_cores"]   = psutil.cpu_count(logical=False) or 0
        specs["cpu_threads"] = psutil.cpu_count(logical=True)  or 0
        vm = psutil.virtual_memory()
        specs["ram_total_gb"]     = round(vm.total     / (1024 ** 3), 1)
        specs["ram_available_gb"] = round(vm.available / (1024 ** 3), 1)
    except Exception:
        pass

    # ── CPU name ─────────────────────────────────────────────────────────────
    try:
        cpu_name = _platform.processor()
        if not cpu_name and os.name == "nt":
            proc = subprocess.run(
                ["wmic", "cpu", "get", "name"],
                capture_output=True, text=True, timeout=5,
                creationflags=CREATE_NO_WINDOW,
            )
            lines = [
                ln.strip() for ln in proc.stdout.strip().splitlines()
                if ln.strip() and ln.strip().lower() != "name"
            ]
            if lines:
                cpu_name = lines[0]
        specs["cpu_name"] = cpu_name or "Unknown"
    except Exception:
        pass

    # ── GPU via nvidia-smi ───────────────────────────────────────────────────
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
            creationflags=CREATE_NO_WINDOW,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            parts = [p.strip() for p in proc.stdout.strip().split(",")]
            specs["cuda_available"] = True
            specs["gpu_name"]       = parts[0]
            specs["vram_gb"]        = round(int(parts[1]) / 1024, 1)
    except Exception:
        pass

    # ── Torch fallback ───────────────────────────────────────────────────────
    if not specs["cuda_available"]:
        try:
            import torch
            specs["cuda_available"] = torch.cuda.is_available()
            if specs["cuda_available"]:
                specs["gpu_name"] = torch.cuda.get_device_name(0)
                specs["vram_gb"]  = round(
                    torch.cuda.get_device_properties(0).total_memory / 1e9, 1
                )
        except Exception:
            pass

    # ── Save to data/system_specs.json ───────────────────────────────────────
    try:
        SYSTEM_SPECS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SYSTEM_SPECS_PATH.write_text(json.dumps(specs, indent=2))
    except Exception as exc:
        logger.warning(f"Could not save system specs: {exc}")

    return specs


class ModelInfoQuery:
    def __init__(self, **data):
        self.model_name        = data.get('model_name', '')
        self.model_size        = data.get('model_size', '')
        self.model_description = data.get('model_description', '')
        self.model_tags        = data.get('model_tags', [])
        self.specs             = data.get('specs', {})


@router.post("/local/model-info-query")
async def query_model_info(request: Request):
    """Ask the configured Info Assistant AI if a model is compatible with user's hardware."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    model_name  = body.get('model_name', 'Unknown')
    model_size  = body.get('model_size', '')
    model_desc  = body.get('model_description', '')
    model_tags  = body.get('model_tags', [])
    specs       = body.get('specs', {})

    vram    = specs.get('vram_gb', 0)
    ram     = specs.get('ram_total_gb', 0)
    gpu     = specs.get('gpu_name') or 'No CUDA GPU detected'
    cpu     = specs.get('cpu_name', 'Unknown CPU')
    cores   = specs.get('cpu_cores', 0)

    # Read configured info model from preferences
    try:
        from core.workspace.preferences_manager import get_preferences_manager
        prefs = get_preferences_manager()
        info_model = prefs.get('system.info_model', 'flash')
    except Exception:
        info_model = 'flash'

    tags_str = ', '.join(model_tags) if model_tags else 'general'
    specs_block = f"""- CPU: {cpu} ({cores} cores)
- GPU: {gpu}
- VRAM: {vram} GB
- System RAM: {ram} GB"""

    prompt = f"""You are a concise AI hardware compatibility advisor. The user wants to know if they can run a specific AI model.

User's Hardware:
{specs_block}

Model to evaluate:
- Name: {model_name}
- File size: {model_size}
- Description: {model_desc}
- Tags: {tags_str}

In 3-5 sentences: Can this user run this model? Will it run on GPU or CPU? Estimate VRAM usage. Mention any caveats. Be direct and practical."""

    try:
        from core.providers.provider_manager import ProviderManager
        import uuid
        pm = ProviderManager()
        response = pm.call_with_failover(
            prompt=prompt,
            trace_id=f"model-info-{uuid.uuid4().hex[:8]}",
            temperature=0.3,
            model=info_model,
            request_type="generation",
            source=CallSource.MODEL_INFO,
        )
        if not response.success:
            raise HTTPException(status_code=500, detail=response.error or "Info query failed")
        return {"response": response.content}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/local/install-cuda-llama")
async def install_cuda_llama():
    """Reinstall llama-cpp-python with CUDA support, streaming pip output as SSE."""
    import asyncio, os, sys
    from fastapi.responses import StreamingResponse

    env = os.environ.copy()
    env["CMAKE_ARGS"] = "-DGGML_CUDA=on"

    async def _generate():
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "pip", "install",
            "llama-cpp-python", "--force-reinstall", "--no-cache-dir",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
            creationflags=CREATE_NO_WINDOW
        )
        async for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").rstrip()
            yield f"data: {json.dumps({'line': line})}\n\n"
        await proc.wait()
        rc = proc.returncode
        yield f"data: {json.dumps({'done': True, 'success': rc == 0, 'returncode': rc})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
