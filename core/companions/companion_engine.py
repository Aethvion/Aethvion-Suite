"""
core/companions/companion_engine.py
Unified, data-driven engine for all Aethvion companions.
Handles LLM logic, tool execution, and dynamic personality evolution.
"""

import asyncio
import datetime
import json
import uuid
import re
from typing import Dict, Any, List
from fastapi import HTTPException

from core.companions.registry import CompanionConfig
from core.companions.engine.memory import CompanionMemory
from core.companions.engine.history import CompanionHistory
from core.companions.engine.streaming import build_bridges_capabilities
from core.companions.engine.tools import execute_tools_stream, extract_peripheral_captures
from core.providers.provider_manager import get_provider_manager
from core.workspace.preferences_manager import get_preferences_manager
from core.workspace.workspace_utils import load_workspaces, build_workspace_block
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
        capabilities = raw.get("capabilities", {})
        prompts = raw.get("prompts", {})
        memory = CompanionMemory(config.data_dir, raw.get("personality_defaults", {}))
        history = CompanionHistory(config.history_dir, config.name, 
                                   lambda s: format_time_diff(s, raw.get("time_context", {})))
        
        memory.initialize()
        now = datetime.datetime.now()
        mem_data = memory.load()
        time_desc = history.time_since_last()
        
        if trigger == "startup":
            instr = prompts.get("startup_instruction", "Welcome back! Check in with the user naturally.").replace("{time_desc}", time_desc)
        else:
            instr = prompts.get("proactive_instruction", "Initiate a friendly, natural conversation with the user based on who you are, what you talked about recently, what you remember about them, or what is happening on their PC.")

        # Recent conversation context so proactive messages can follow up on previous topics
        recent_chat_context = ""
        try:
            recent_days = history.load_days(0, 2).get("history", [])
            recent_msgs = []
            for day_block in reversed(recent_days):
                for m in day_block.get("messages", []):
                    role_lbl = "User" if m.get("role") == "user" else config.name
                    txt = (m.get("content") or "").strip()
                    if txt:
                        recent_msgs.append(f"{role_lbl}: {txt[:240]}")
            if recent_msgs:
                recent_chat_context = "\n\nRecent Conversation Snippet (for continuity — follow up naturally or bring up something new):\n" + "\n".join(recent_msgs[-6:])
        except Exception:
            pass

        # Ambient PC / Media context for check-ins if permitted by connector_profile
        ambient_context = ""
        connector_profile = capabilities.get("connector_profile", "full_local")
        allow_proactive_tools = get_preferences_manager().get(f"{config.id}.allow_proactive_tools", True)
        if capabilities.get("tools_enabled", True) or allow_proactive_tools:
            try:
                from core.bridges import bridge_manager
                ambient_parts = []
                ok_win, _ = bridge_manager.is_module_allowed("window_focus", connector_profile)
                if ok_win:
                    win_info = await asyncio.to_thread(
                        bridge_manager.call_module, "window_focus", "get_active_window", {"max_windows": 6}, connector_profile
                    )
                    if win_info and not win_info.startswith("Bridge"):
                        ambient_parts.append(win_info)
                ok_media, _ = bridge_manager.is_module_allowed("media_sentinel", connector_profile)
                if ok_media:
                    media_info = await asyncio.to_thread(
                        bridge_manager.call_module, "media_sentinel", "get_media_info", {}, connector_profile
                    )
                    if media_info and "No active media" not in media_info and not media_info.startswith("Bridge"):
                        ambient_parts.append(f"Currently playing on PC: {media_info}")
                ok_sys, _ = bridge_manager.is_module_allowed("system_link", connector_profile)
                if ok_sys:
                    sys_info = await asyncio.to_thread(
                        bridge_manager.call_module, "system_link", "get_hardware_telemetry", {}, connector_profile
                    )
                    if sys_info and not sys_info.startswith("Bridge"):
                        ambient_parts.append(f"System telemetry: {sys_info}")
                ok_tasks, _ = bridge_manager.is_module_allowed("companion_tasks", connector_profile)
                if ok_tasks:
                    tasks_info = await asyncio.to_thread(
                        bridge_manager.call_module, "companion_tasks", "list_tasks", {}, connector_profile
                    )
                    if tasks_info and "No active tasks" not in tasks_info and not tasks_info.startswith("Bridge"):
                        ambient_parts.append(tasks_info)
                if ambient_parts:
                    ambient_context = "\n\nLive PC & Co-Working Context (optional — mention naturally only if relevant):\n" + "\n".join(ambient_parts)
            except Exception:
                pass

        expr_hint = ""
        if config.expressions:
            expr_hint = (
                f"\nAvailable expressions: {', '.join(config.expressions)}. "
                "Embed <expression>name</expression> and <mood>mood</mood> once in your reply."
            )

        raw_init_prompt = prompts.get("initiate_system", "").strip()
        if raw_init_prompt:
            try:
                system_prompt = raw_init_prompt.format(
                    base_info=json.dumps(mem_data["base_info"], indent=2),
                    memory=json.dumps(mem_data["memory"], indent=2),
                    datetime_ctx=now.strftime("%A, %d %B %Y — %H:%M"),
                    trigger_instruction=instr
                ) + recent_chat_context + ambient_context + expr_hint
            except KeyError:
                system_prompt = raw_init_prompt + f"\n\n{instr}" + recent_chat_context + ambient_context + expr_hint
        else:
            bi = mem_data.get("base_info", {})
            mem = mem_data.get("memory", {})
            system_prompt = (
                f"You are {config.name}, an AI companion.\n"
                f"Identity: {bi.get('core_identity', config.description)}\n"
                f"Personality: {bi.get('personality', '')}\n"
                f"Speech style: {bi.get('speech_style', '')}\n"
                f"What you know about the user:\n{json.dumps(mem, indent=2)}\n\n"
                f"Current time: {now.strftime('%A, %d %B %Y — %H:%M')}\n"
                f"Time since last message: {time_desc}"
                f"{recent_chat_context}"
                f"{ambient_context}"
                f"{expr_hint}\n\n"
                f"Task: {instr}\n"
                f"Write a short, natural check-in message (1-3 sentences) in character."
            )

        pref_model = get_preferences_manager().get(config.id, {}).get("model")
        model = config.default_model or pref_model or "auto"
        pm = get_provider_manager()
        response = await asyncio.to_thread(
            pm.call_with_failover,
            prompt=system_prompt,
            trace_id=f"{config.id}-init-{uuid.uuid4().hex[:8]}",
            temperature=behavior.get("initiate_temperature", 0.8),
            model=model,
            source=f"{config.id}-initiate"
        )

        if not response.success:
            raise HTTPException(status_code=500, detail=response.error or "Model call failed")
        content = response.content.strip()

        expression = raw.get("default_expression") or behavior.get("default_expression", "default")
        mood = behavior.get("default_mood", "calm")
        exp_match = re.search(r"<expression>(.*?)</expression>", content, re.IGNORECASE)
        if exp_match:
            expression = exp_match.group(1).strip().lower()
        mood_match = re.search(r"<mood>(.*?)</mood>", content, re.IGNORECASE)
        if mood_match:
            mood = mood_match.group(1).strip().lower()

        content = re.sub(
            r"<(?:expression|mood|break)[^>]*>.*?</(?:expression|mood|break)>|<break\s*/?>",
            " ", content, flags=re.DOTALL | re.IGNORECASE
        ).strip()

        history.save_message("assistant", content, utcnow_iso(),
                             mood=mood,
                             expression=expression, proactive=True)
        return {
            "companion_id": config.id,
            "name": config.name,
            "accent_color": raw.get("accent_color", "#6366f1"),
            "avatar_symbol": raw.get("avatar_symbol", "✦"),
            "has_icon": bool(raw.get("has_icon")),
            "icon_mode": bool(raw.get("icon_mode")),
            "expression_images": raw.get("expression_images", {}),
            "voice": raw.get("voice", {}),
            "response": content,
            "expression": expression,
            "mood": mood,
            "model": response.model,
            "memory_updated": False
        }

    @staticmethod
    async def chat_response(
        config: CompanionConfig,
        message: str,
        chat_history: List[Any],
        attachments: List[Dict[str, Any]] | None = None
    ):
        try:
            raw = config._raw_config
            behavior = raw.get("behavior", {})
            capabilities = raw.get("capabilities", {})
            connector_profile = capabilities.get("connector_profile", "full_local")
            prompts = raw.get("prompts", {})
            memory = CompanionMemory(config.data_dir, raw.get("personality_defaults", {}))
            history = CompanionHistory(config.history_dir, config.name,
                                       lambda s: format_time_diff(s, raw.get("time_context", {})))

            memory.initialize()
            mem_data = memory.load()
            bridges_block = (
                build_bridges_capabilities(capabilities, profile_id=connector_profile)
                if capabilities.get("tools_enabled", True)
                else ""
            )

            workspace_block = ""
            if capabilities.get("workspace_access"):
                workspaces = load_workspaces(config.id)
                workspace_block = build_workspace_block(workspaces)

            system_prompt = prompts.get("chat_system", "").format(
                base_info=json.dumps(mem_data["base_info"], indent=2),
                memory=json.dumps(mem_data["memory"], indent=2),
                datetime_ctx=datetime.datetime.now().strftime("%A, %d %B %Y — %H:%M"),
                time_since=history.time_since_last(),
                workspace_block=workspace_block,
                bridges_block=bridges_block
            )

            # Fallback system prompt for companions without one
            if not system_prompt.strip():
                bi  = mem_data.get("base_info", {})
                mem = mem_data.get("memory", {})
                parts = [f"You are {config.name}, an AI companion."]
                if bi.get("core_identity"):
                    parts.append(f"\n\nIdentity: {bi['core_identity']}")
                if bi.get("personality"):
                    parts.append(f"\n\nPersonality: {bi['personality']}")
                if bi.get("speech_style"):
                    parts.append(f"\n\nSpeech style: {bi['speech_style']}")
                if bi.get("quirks"):
                    parts.append(f"\n\nQuirks: {'; '.join(bi['quirks'])}")
                if mem:
                    parts.append(f"\n\nWhat you know about the user:\n{json.dumps(mem, indent=2)}")
                if bridges_block:
                    parts.append(f"\n\n{bridges_block}")
                if workspace_block:
                    parts.append(f"\n\n{workspace_block}")
                parts.append(f"\n\nCurrent time: {datetime.datetime.now().strftime('%A, %d %B %Y — %H:%M')}")
                system_prompt = "".join(parts)

            # Expression awareness
            expressions = config.expressions or []
            if expressions:
                expr_list   = ", ".join(expressions)
                default_exp = raw.get("default_expression", expressions[0])
                system_prompt += (
                    f"\n\n## Visual Expressions"
                    f"\nYou have a visual portrait that changes based on your expression."
                    f"\nAvailable expressions: {expr_list}"
                    f"\nDefault expression: {default_exp}"
                    f"\nTo change your expression, embed the tag <expression>name</expression> anywhere in your response."
                    f"\nExample: 'Let me think... <expression>thinking</expression> Here is my answer.'"
                    f"\nOnly use expression names from the list above. Use at most one per response."
                    f"\nChoose the expression that best matches your current emotional state or the tone of your reply."
                )

            # Persistent memory instructions
            if capabilities.get("memory_updates_enabled", True):
                system_prompt += (
                    "\n\n## Persistent Memory"
                    "\nYou have a memory system that persists between conversations."
                    "\nWhenever you learn something meaningful about the user — their name, age, location,"
                    " job, preferences, goals, important events — save it immediately by embedding this"
                    " exact structure anywhere in your response:"
                    "\n"
                    "\n<memory_update>"
                    "\n{"
                    "\n  \"user_info\": { \"descriptive_key\": \"value\" },"
                    "\n  \"recent_observations\": [\"One short factual sentence.\"]"
                    "\n}"
                    "\n</memory_update>"
                    "\n"
                    "\nRules:"
                    "\n  - The block is completely invisible to the user — it is stripped before display"
                    "\n  - Only include fields you are actually updating (omit unchanged fields)"
                    "\n  - user_info keys should be descriptive: \"name\", \"age\", \"city\", \"hobby\", \"job\""
                    "\n  - Observations must be concise and factual (e.g. \"User lives in Apeldoorn, Netherlands\")"
                    "\n  - Emit the block whenever new information is shared — do not wait to be asked"
                    "\n  - Never mention the memory_update tags in your visible response"
                    "\n  - Do not emit the block just to confirm something you already knew"
                )

            # Multi-message style
            system_prompt += (
                "\n\n## Multi-Message Style — USE THIS ACTIVELY"
                "\nYou send messages like a real person texting — multiple short messages, not one big wall of text."
                "\nUse the literal tag <break> to split your response into separate chat bubbles."
                "\nThe <break> tag is invisible to the user; it only creates a new message bubble."
                "\nIMPORTANT: You must output the exact characters: <break>"
                "\n"
                "\nExamples of how to write your responses:"
                "\n  'Oh wow, really?! <break> Let me think about that for a second... <break> Okay, here is what I found!'"
                "\n  'Haha yes! <break> I completely agree with you on that one.'"
                "\n  'Hmm. <break> That is actually a really good question. <break> Here is my take:'"
                "\n"
                "\nGuidelines:"
                "\n  - Use <break> whenever a natural pause or shift in thought occurs"
                "\n  - Each part after a <break> should be a complete thought"
                "\n  - Aim for 2-4 parts for most responses; a single message is fine for very short answers"
                "\n  - Do NOT write the word break in plain text — always output the tag: <break>"
            )

            pref_model = get_preferences_manager().get(config.id, {}).get("model")
            model = config.default_model or pref_model
            pm = get_provider_manager()

            # Pre-flight validation: catch missing model / API key early
            if not model:
                err_msg = (
                    f"No model selected for {config.name}. "
                    "Please go to Settings → Default Model and choose a model."
                )
                yield json.dumps({
                    "type": "error",
                    "message": err_msg,
                    "content": err_msg,
                }) + "\n"
                return

            _target_provider = pm.model_to_provider_map.get(model)
            if not _target_provider and (model.endswith(".gguf") or model.startswith("local:")):
                _target_provider = "local"
            elif not _target_provider and (model.startswith("ollama:") or model.startswith("ollama/")):
                _target_provider = "ollama"

            if _target_provider:
                from core.providers.provider_manager import ProviderStatus
                _prov = pm.providers.get(_target_provider)
                if _prov and _prov.status == ProviderStatus.OFFLINE:
                    err_msg = (
                        f"The {_target_provider} provider is offline — "
                        "its API key may be missing or invalid. "
                        "Go to Settings → API Keys to configure it."
                    )
                    yield json.dumps({
                        "type": "error",
                        "message": err_msg,
                        "content": err_msg,
                    }) + "\n"
                    return
            elif "/" not in model and model != "auto" and not model.startswith("profile:"):
                err_msg = (
                    f"Model '{model}' is not available. "
                    "It may belong to a provider with no API key configured, or the local file is missing. "
                    "Select an active model in Companion Settings."
                )
                yield json.dumps({
                    "type": "error",
                    "message": err_msg,
                    "content": err_msg,
                }) + "\n"
                return
            # end validation

            trace_id = f"{config.id}-chat-{uuid.uuid4().hex[:8]}"

            # Check for explicit user /slash_command connector triggers (e.g. /screen_capture, /reddit, /weather)
            slash_attachments = []
            effective_prompt = message
            if "/" in message:
                from core.bridges import bridge_manager
                slash_res = await asyncio.to_thread(
                    bridge_manager.parse_and_execute_slash_commands,
                    message,
                    connector_profile
                )
                if slash_res.get("triggered"):
                    for sr in slash_res.get("results", []):
                        yield json.dumps({
                            "type": "tool_start",
                            "tool": sr.get("module_id", "connector"),
                            "args": {"command": sr.get("command", "")}
                        }) + "\n"
                    slash_attachments = slash_res.get("attachments", [])
                    ctx_blocks = [
                        f"[CONNECTOR RESULT — {sr['name']} ({sr['module_id']}.{sr['command']})]\n{sr['output']}"
                        for sr in slash_res.get("results", [])
                    ]
                    effective_prompt = (
                        "\n\n".join(ctx_blocks)
                        + f"\n\nUser message: {slash_res.get('cleaned_message', message)}\n"
                        "Use the real connector output above to answer naturally."
                    )

            # Inject user-uploaded file/image context into effective_prompt
            user_attachments = []
            if attachments:
                att_blocks = []
                for att in attachments:
                    fname = att.get("filename") or "attachment"
                    url = att.get("url") or ""
                    is_img = bool(att.get("is_image"))
                    txt = (att.get("text_content") or "").strip()
                    user_attachments.append({
                        "filename": fname,
                        "url": url,
                        "is_image": is_img,
                        "type": "image" if is_img else "file"
                    })
                    if txt:
                        att_blocks.append(f"[ATTACHED FILE: {fname}]\n```\n{txt[:16000]}\n```")
                    elif is_img:
                        att_blocks.append(f"[ATTACHED IMAGE: {fname} (path: {att.get('path', url)})]")
                    else:
                        att_blocks.append(f"[ATTACHED FILE: {fname}]")
                if att_blocks:
                    effective_prompt = "\n\n".join(att_blocks) + f"\n\n{effective_prompt}"

            full_content = ""
            actual_model = model

            # Convert frontend chat_history to provider messages
            messages = []
            for turn in chat_history:
                r = turn.role    if hasattr(turn, "role")    else turn.get("role", "user")
                c = turn.content if hasattr(turn, "content") else turn.get("content", "")
                messages.append({"role": "user" if r == "user" else "assistant", "content": c})

            # 1. Stream primary LLM response
            for chunk in pm.call_with_failover_stream(
                prompt=effective_prompt,
                system_prompt=system_prompt,
                messages=messages,
                trace_id=trace_id,
                temperature=behavior.get("temperature", 0.8),
                model=model, source=f"{config.id}-chat"
            ):
                full_content += chunk
                yield json.dumps({"type": "message", "content": chunk}) + "\n"

            # 2. Tool execution loop — up to 3 rounds so chained tool calls resolve
            results_total: list[str] = []
            intermediate_responses: list[str] = []
            final_content  = full_content
            current_resp   = full_content
            round_msgs     = list(messages)

            def _strip_meta_tags(text: str) -> str:
                """Strip expression/mood/break tags and tidy whitespace."""
                return re.sub(
                    r"<(?:expression|mood|break)[^>]*>.*?</(?:expression|mood|break)>|<break\s*/?>",
                    "", text, flags=re.DOTALL | re.IGNORECASE
                ).strip()

            if capabilities.get("tools_enabled", True):
                workspaces = load_workspaces(config.id)

                for _round in range(3):
                    round_results: list[str] = []
                    cleaned_resp  = current_resp

                    async for tool_event in execute_tools_stream(current_resp, workspaces, profile_id=connector_profile):
                        if tool_event["type"] == "tool_start":
                            yield json.dumps(tool_event) + "\n"
                        elif tool_event["type"] == "final_cleaned":
                            cleaned_resp  = tool_event["content"]
                            round_results = tool_event["results"]

                    if not round_results:
                        final_content = cleaned_resp
                        break

                    results_total.extend(round_results)

                    inter_clean = _strip_meta_tags(cleaned_resp)
                    if inter_clean:
                        intermediate_responses.append(inter_clean)

                    if _round == 0:
                        round_msgs.append({"role": "user",      "content": effective_prompt})

                    round_msgs.append({"role": "assistant", "content": current_resp})

                    tool_summary   = "\n\n".join(round_results)
                    followup_prompt = (
                        f"[TOOL RESULTS — use these to answer]\n{tool_summary}\n\n"
                        "The results above are real. Answer the user naturally using them. "
                        "Do NOT output any [tool:...] calls — your tool use is finished."
                    )

                    next_resp = ""
                    yield json.dumps({"type": "tool_response_start"}) + "\n"
                    for chunk in pm.call_with_failover_stream(
                        prompt=followup_prompt,
                        system_prompt=system_prompt,
                        messages=round_msgs,
                        trace_id=f"{trace_id}-r{_round + 1}",
                        temperature=behavior.get("temperature", 0.8),
                        model=model,
                        source=f"{config.id}-chat-r{_round + 1}",
                    ):
                        next_resp += chunk
                        yield json.dumps({"type": "message", "content": chunk}) + "\n"

                    round_msgs.append({"role": "user", "content": followup_prompt})
                    current_resp = next_resp

                else:
                    final_content = current_resp

            results = results_total

            # 3. Extract Expression & Mood
            scan_content = final_content if results_total else full_content
            expression = behavior.get("default_expression", "default")
            mood = behavior.get("default_mood", "calm")
            exp_match = re.search(r"<expression>(.*?)</expression>", scan_content, re.IGNORECASE)
            if exp_match:
                expression = exp_match.group(1).strip().lower()
            mood_match = re.search(r"<mood>(.*?)</mood>", scan_content, re.IGNORECASE)
            if mood_match:
                mood = mood_match.group(1).strip().lower()

            # 4. Strip expression/mood content tags — but PRESERVE <break> for splitting below.
            final_content = re.sub(
                r"<(?:expression|mood)>.*?</(?:expression|mood)>", "",
                final_content, flags=re.DOTALL | re.IGNORECASE
            ).strip()

            # 4b. Split by <break>
            _break_re = re.compile(r"\s*<break\s*/?>\s*", re.IGNORECASE)
            final_parts: list[str] = []
            for raw_part in _break_re.split(final_content):
                cleaned_part = re.sub(
                    r"<(?:expression|mood|break)[^>]*>.*?</(?:expression|mood|break)>|<(?:expression|mood|break)[^>]*>",
                    "", raw_part, flags=re.DOTALL | re.IGNORECASE
                ).strip()
                if cleaned_part:
                    final_parts.append(cleaned_part)
            if not final_parts:
                final_parts = [final_content] if final_content.strip() else []

            final_content = "\n\n".join(final_parts)

            # 5. Handle Memory Updates
            mem_up = False
            if capabilities.get("memory_updates_enabled", True):
                cleaned_mem_content = memory.update_from_xml(final_content)
                if cleaned_mem_content != final_content:
                    final_content = cleaned_mem_content
                    final_parts = [p.strip() for p in final_content.split("\n\n") if p.strip()] or [final_content]
                    mem_up = True

            # 6. Extract peripheral attachments (screenshots etc)
            assistant_attachments = list(slash_attachments)
            if results:
                _, tool_attachments = extract_peripheral_captures(results, [])
                assistant_attachments.extend(tool_attachments)

            # 7. Persist to history
            history.save_message("user", message, utcnow_iso(), attachments=user_attachments or None)
            for inter in intermediate_responses:
                history.save_message("assistant", inter, utcnow_iso(), model=actual_model)
            for part in final_parts:
                history.save_message("assistant", part, utcnow_iso(),
                                     model=actual_model, attachments=assistant_attachments or None)

            # 8. Final event
            yield json.dumps({
                "type": "done",
                "content": final_parts[0] if final_parts else final_content,
                "parts": final_parts if len(final_parts) > 1 else None,
                "expression": expression,
                "mood": mood,
                "memory_updated": mem_up,
                "attachments": assistant_attachments
            }) + "\n"
        except Exception as e:
            logger.error(f"Chat response error: {e}", exc_info=True)
            yield json.dumps({"type": "error", "message": "Something went wrong. Please try again."}) + "\n"
            yield json.dumps({"type": "done"}) + "\n"
