"""
Aethvion Suite - Assistant Routes
REST API endpoints for the floating Misaka Cipher assistant.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uuid
import json

from core.providers.provider_manager import ProviderManager
from core.workspace.preferences_manager import get_preferences_manager
from core.utils.logger import get_logger
from core.ai.call_contexts import CallSource, build_companion_prompt, validate_call_context

logger = get_logger(__name__)
router = APIRouter(prefix="/api/assistant", tags=["assistant"])

class AssistantMessage(BaseModel):
    role: str
    content: str

class UIContext(BaseModel):
    active_tab_id: Optional[str] = None
    active_tab_name: Optional[str] = None

class AssistantChatRequest(BaseModel):
    messages: List[AssistantMessage]
    ui_context: Optional[UIContext] = None
    
class AssistantChatResponse(BaseModel):
    response: str
    model_id: str
    
def _build_assistant_context(include_web_context: bool = False, allow_dashboard_control: bool = False) -> str:
    """
    Build the Misaka companion system prompt.

    Delegates to core.ai.call_contexts.build_companion_prompt() — the canonical
    implementation.  This wrapper exists so existing call sites inside this file
    continue to work without change.

    See core/ai/call_contexts.py for the full documentation of what context
    CallSource.COMPANION is allowed to receive.
    """
    return build_companion_prompt(
        include_web_context=include_web_context,
        allow_dashboard_control=allow_dashboard_control,
    )

import re
def _clean_assistant_response(text: str) -> str:
    text = re.sub(r'\[tool:.*?\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<memory_update>.*?</memory_update>', '', text, flags=re.IGNORECASE | re.DOTALL)
    # Don't strip [Emotion] or [SwitchTab] as the frontend JS handles those
    return text.strip()

@router.post("/chat", response_model=AssistantChatResponse)
async def assistant_chat(request: AssistantChatRequest):
    """Handle chat requests for the floating Misaka Cipher assistant with simple tool fallback."""
    prefs = get_preferences_manager()
    assistant_config = prefs.get('assistant', {})
    
    if not assistant_config.get('enabled', True):
        raise HTTPException(status_code=403, detail="Assistant is disabled in settings.")
        
    target_model = assistant_config.get('model', 'flash')
    include_web = assistant_config.get('include_web_context', False)
    allow_dash_control = assistant_config.get('allow_dashboard_control', False)

    pm = ProviderManager()
    trace_id = f"assistant-{uuid.uuid4().hex[:8]}"

    system_prompt = _build_assistant_context(include_web_context=include_web, allow_dashboard_control=allow_dash_control)
    validate_call_context(CallSource.COMPANION, system_prompt, trace_id)

    # Simple manual tool routing for specific usage queries to save tokens/increase accuracy
    user_msg = request.messages[-1].content.lower() if request.messages else ""
    if any(k in user_msg for k in ["how many", "file count", "files are in", "project size", "how big"]):
        # Add a hint about using tools
        system_prompt += "\nHint: You should use your 'get_file_counts' or 'get_project_size' tools for this."

    # Format history
    formatted_prompt = system_prompt + "\n\n--- Conversation History ---\n"
    for msg in request.messages:
        formatted_prompt += f"{msg.role.capitalize()}: {msg.content}\n"
    formatted_prompt += "Misaka:"
    
    try:
        # 1. Initial Call with tool support
        from core.system_retrieval import ASSISTANT_TOOLS, ASSISTANT_TOOL_MAP
        
        response = pm.call_with_failover(
            prompt=formatted_prompt,
            trace_id=trace_id,
            temperature=0.7,
            model=target_model,
            request_type="generation",
            source=CallSource.COMPANION,
            tools=ASSISTANT_TOOLS
        )
        
        if not response.success:
            raise HTTPException(status_code=500, detail=response.error)
            
        # Check for tool calls in metadata (if supported by provider)
        # Note: This implementation assumes the provider returns 'tool_calls' in metadata
        tool_calls = response.metadata.get('tool_calls', []) if response.metadata else []
        
        if tool_calls:
            # Execute tool(s)
            tool_results = []
            for call in tool_calls:
                func_name = call.get('name')
                args = call.get('arguments', {})
                if isinstance(args, str):
                    try: args = json.loads(args)
                    except (json.JSONDecodeError, ValueError): args = {}
                
                if func_name in ASSISTANT_TOOL_MAP:
                    logger.info(f"[{trace_id}] Assistant executing tool: {func_name} with {args}")
                    result = ASSISTANT_TOOL_MAP[func_name](**args)
                    tool_results.append(f"TOOL_RESULT ({func_name}): {result}")
            
            # Second call with results
            if tool_results:
                final_prompt = formatted_prompt + "\n\n" + "\n".join(tool_results) + "\n\nMisaka:"
                response = pm.call_with_failover(
                    prompt=final_prompt,
                    trace_id=trace_id,
                    temperature=0.7,
                    model=target_model,
                    request_type="generation",
                    source=CallSource.COMPANION
                )

        return AssistantChatResponse(
            response=_clean_assistant_response(response.content),
            model_id=response.model
        )
        
    except Exception as e:
        logger.error(f"Assistant Chat Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
