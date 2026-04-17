"""
core/companions/companion_engine.py
═══════════════════════════════════
Unified, data-driven engine for all Aethvion companions.
Handles LLM logic, tool execution, and dynamic personality evolution.
"""

import datetime
import json
import uuid
from typing import Dict, Any, List, Optional
from fastapi import HTTPException

from core.companions.registry import CompanionConfig
from core.companions.engine.memory import CompanionMemory
from core.companions.engine.history import CompanionHistory
from core.companions.engine.streaming import clean_memory_tags, build_nexus_capabilities, get_greeting_period
from core.providers.provider_manager import ProviderManager
from core.workspace.preferences_manager import get_preferences_manager
from core.utils.logger import get_logger
from core.utils import utcnow_iso

logger = get_logger(__name__)

def format_time_diff(total_seconds: int, time_context: Dict[str, Any]) -> str:
    fmt = time_context.get("format", {})
    rules = sorted([(m_val, data.get("text", "")) for k, data in fmt.items() if (m_val := data.get("max")) is not None])
    
    for max_val, text in rules:
        if total_seconds < max_val:
            m = total_seconds // 60
            h = total_seconds // 3600
            s = 's' if (m != 1) else ''
            return text.format(m=m, h=h, s=s)
            
    for key, data in fmt.items():
        if data.get("max") is None:
            return data["text"].format(d=total_seconds // 86400)
    return f"{total_seconds} seconds ago"

class CompanionEngine:
    @staticmethod
    async def initiate_response(config: CompanionConfig, trigger: str = "startup"):
        raw = config._raw_config
        behavior = raw.get("behavior", {})
        prompts = raw.get("prompts", {})
        memory = CompanionMemory(config.data_dir, raw.get("personality_defaults", {}))
        history = CompanionHistory(config.history_dir, config.name, 
                                   lambda s: format_time_diff(s, raw.get("time_context", {})))
        
        memory.initialize()
        now = datetime.datetime.now()
        mem_data = memory.load()
        
        if trigger == "startup":
            time_desc = history.time_since_last()
            instr = prompts.get("startup_instruction", "Welcome back.").replace("{time_desc}", time_desc)
        else:
            instr = prompts.get("proactive_instruction", "Hello.")

        system_prompt = prompts.get("initiate_system", "").format(
            base_info=json.dumps(mem_data["base_info"], indent=2),
            memory=json.dumps(mem_data["memory"], indent=2),
            datetime_ctx=now.strftime("%A, %d %B %Y"),
            trigger_instruction=instr
        )

        model = get_preferences_manager().get(config.id, {}).get("model", config.default_model)
        pm = ProviderManager()
        response = pm.call_with_failover(
            prompt=system_prompt,
            trace_id=f"{config.id}-init-{uuid.uuid4().hex[:8]}",
            temperature=behavior.get("initiate_temperature", 0.8),
            model=model,
            source=f"{config.id}-initiate"
        )
        
        if not response.success: raise HTTPException(status_code=500, detail=response.error)
        content = response.content.strip()
        history.save_message("assistant", content, utcnow_iso(), 
                             mood=behavior.get("default_mood", "calm"), 
                             expression=behavior.get("default_expression", "default"), proactive=True)
        return {
            "response": content,
            "expression": behavior.get("default_expression", "default"),
            "mood": behavior.get("default_mood", "calm"),
            "model": response.model,
            "memory_updated": False
        }

    @staticmethod
    async def chat_response(config: CompanionConfig, message: str, chat_history: List[Any]):
        raw = config._raw_config
        behavior = raw.get("behavior", {})
        capabilities = raw.get("capabilities", {})
        prompts = raw.get("prompts", {})
        memory = CompanionMemory(config.data_dir, raw.get("personality_defaults", {}))
        history = CompanionHistory(config.history_dir, config.name, 
                                   lambda s: format_time_diff(s, raw.get("time_context", {})))
        
        memory.initialize()
        mem_data = memory.load()
        nexus_block = build_nexus_capabilities() if capabilities.get("tools_enabled") else ""
        system_prompt = prompts.get("chat_system", "").format(
            base_info=json.dumps(mem_data["base_info"], indent=2),
            memory=json.dumps(mem_data["memory"], indent=2),
            datetime_ctx=datetime.datetime.now().strftime("%A, %d %B %Y — %H:%M"),
            time_since=history.time_since_last(),
            workspace_block="", nexus_block=nexus_block
        )

        model = get_preferences_manager().get(config.id, {}).get("model", config.default_model)
        pm = ProviderManager()
        response = pm.call_with_failover(
            prompt=system_prompt,
            user_message=message,
            trace_id=f"{config.id}-chat-{uuid.uuid4().hex[:8]}",
            temperature=behavior.get("temperature", 0.8),
            model=model, source=f"{config.id}-chat"
        )
        if not response.success: raise HTTPException(status_code=500, detail=response.error)
        content = response.content.strip()
        
        mem_up = False
        if capabilities.get("memory_updates_enabled", True):
            if (new_mem := clean_memory_tags(content)):
                memory.update(new_mem); mem_up = True
        
        history.save_message("user", message, utcnow_iso())
        history.save_message("assistant", content, utcnow_iso(), model=response.model)
        return {
            "response": content,
            "expression": behavior.get("default_expression", "default"),
            "mood": behavior.get("default_mood", "calm"),
            "model": response.model,
            "memory_updated": mem_up
        }
