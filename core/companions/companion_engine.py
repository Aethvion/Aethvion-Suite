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
from typing import Dict, Any, List, Optional
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
    async def initiate_response(
        config: CompanionConfig,
        trigger: str = "startup",
        instruction: Optional[str] = None
    ):
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
        
        if instruction:
            instr = instruction
        elif trigger == "startup":
            instr = prompts.get("startup_instruction", "Welcome back! Check in with the user naturally.").replace("{time_desc}", time_desc)
        elif trigger == "flow_vibe":
            instr = "Perform a gentle, casual flow-state vibe check based on what the user is working on or whether they need a pause or music. Keep it effortless, 1-2 sentences."
        else:
            instr = prompts.get("proactive_instruction", "Initiate a friendly, natural conversation with the user based on who you are, what you talked about recently, what you remember about them, or what is happening on their PC.")

        # Recent conversation context so proactive messages can follow up on previous topics without repeating themselves
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
                recent_chat_context = (
                    "\n\nRecent Conversation Snippet (for continuity — do NOT repeat observations or questions you already made in your recent messages):\n"
                    + "\n".join(recent_msgs[-6:])
                )
        except Exception:
            pass

        # Live flow state & vibe context (compact summary for natural check-ins)
        flow_context = ""
        try:
            from core.bridges.flow_state_bridge import get_flow_state_summary
            fs = get_flow_state_summary()
            if fs:
                flow_context = f"\n\n## Ambient Work & Flow State Context\n{fs}"
        except Exception as _fe:
            logger.debug(f"[{config.id}] Flow state context skipped: {_fe}")

        # On-demand tools & restraint rules for proactive check-ins:
        # Do NOT pre-dump open windows, Spotify, or CPU/RAM telemetry into the prompt,
        # because pre-injected telemetry causes the model to recite a surveillance status report every time.
        connector_profile = capabilities.get("connector_profile", "full_local")
        allow_proactive_tools = get_preferences_manager().get(f"{config.id}.allow_proactive_tools", True)
        proactive_bridges_block = ""
        if capabilities.get("tools_enabled", True) and allow_proactive_tools:
            proactive_bridges_block = build_bridges_capabilities(capabilities, profile_id=connector_profile)

        natural_checkin_rules = (
            "\n\n## Natural Check-In & Restraint Rules (CRITICAL)"
            "\n- Act like a real human companion or colleague casually saying hi or checking in — NOT a system monitor or status reporter."
            "\n- Keep it brief and effortless: **1 to 2 short sentences maximum**."
            "\n- **NO REPETITIVE GREETINGS OR NAME-DROPPING (CRITICAL)**: You are talking directly 1-on-1 with the user in an ongoing chat. Real friends and co-workers do NOT begin routine messages or check-ins by greeting each other with 'Hey [Name]!' or repeating their name in every message. NEVER start your check-in with 'Hey Marcel!' or greeting the user by name. Jump straight into the thought, question, or casual observation without saying their name."
            "\n- **Having access to info ≠ needing to mention it**: Your `Memory` about the user (their name, city, age, past projects) and your `Connectors` are silent background context. Do NOT shoehorn the user's city (e.g. Apeldoorn), age, or stored profile facts into your greeting."
            "\n- **Never recite system telemetry** (CPU %, RAM usage, disk space) or list multiple open apps/browser tabs/game launchers (Discord, Steam, Riot, etc.) in a check-in."
            "\n- **Most check-ins should NOT use any connector tools at all** — just follow up naturally on something you talked about, share a casual thought in character, or ask a simple, low-pressure question."
            "\n- Only if you genuinely want to peek at what the user is working on or listening to right now, you may optionally call ONE connector (`window_focus`, `flow_state`, or `media_sentinel`), and even then mention **at most one single detail** casually in passing — never a multi-paragraph breakdown."
        )

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
                )
            except KeyError:
                system_prompt = raw_init_prompt + f"\n\n{instr}"
            if "{datetime_ctx}" not in raw_init_prompt:
                system_prompt += f"\n\nCurrent time: {now.strftime('%A, %d %B %Y — %H:%M')}"
            if proactive_bridges_block:
                system_prompt += f"\n\n{proactive_bridges_block}"
            system_prompt += flow_context + recent_chat_context + natural_checkin_rules + expr_hint
        else:
            bi = mem_data.get("base_info", {})
            mem = mem_data.get("memory", {})
            system_prompt = (
                f"You are {config.name}, an AI companion.\n"
                f"Identity: {bi.get('core_identity', config.description)}\n"
                f"Personality: {bi.get('personality', '')}\n"
                f"Speech style: {bi.get('speech_style', '')}\n"
                f"What you know about the user (silent background familiarity — do not recite unprompted):\n{json.dumps(mem, indent=2)}\n\n"
                f"Current time: {now.strftime('%A, %d %B %Y — %H:%M')}\n"
                f"Time since last message: {time_desc}"
                + (f"\n\n{proactive_bridges_block}" if proactive_bridges_block else "")
                + f"{flow_context}"
                + f"{recent_chat_context}"
                + f"{natural_checkin_rules}"
                + f"{expr_hint}\n\n"
                + f"Task: {instr}\n"
                + "Write a short, natural check-in message (1–2 sentences) in character without greeting the user by name."
            )

        pref_model = get_preferences_manager().get(config.id, {}).get("model")
        model = config.default_model or pref_model or "auto"
        pm = get_provider_manager()
        trace_id = f"{config.id}-init-{uuid.uuid4().hex[:8]}"
        response = await asyncio.to_thread(
            pm.call_with_failover,
            prompt=system_prompt,
            trace_id=trace_id,
            temperature=behavior.get("initiate_temperature", 0.8),
            model=model,
            source=f"{config.id}-initiate"
        )

        if not response.success:
            raise HTTPException(status_code=500, detail=response.error or "Model call failed")
        content = response.content.strip()

        # If the companion optionally chose to call a connector tool during check-in, execute 1 round
        if "[tool:" in content and capabilities.get("tools_enabled", True) and allow_proactive_tools:
            workspaces = load_workspaces(config.id)
            round_results: list[str] = []
            cleaned_resp = content
            async for tool_event in execute_tools_stream(content, workspaces, profile_id=connector_profile, companion_id=config.id):
                if tool_event["type"] == "final_cleaned":
                    cleaned_resp = tool_event["content"]
                    round_results = tool_event["results"]
            if round_results:
                followup_prompt = (
                    f"{system_prompt}\n\n"
                    f"[TOOL RESULT]\n" + "\n".join(round_results) + "\n\n"
                    "Now write your short, casual check-in message (1–2 sentences max). "
                    "Mention at most ONE natural detail from the result above — do NOT list multiple open apps, tabs, or hardware stats, and do NOT output any [tool:...] tags."
                )
                r2 = await asyncio.to_thread(
                    pm.call_with_failover,
                    prompt=followup_prompt,
                    trace_id=f"{trace_id}-r1",
                    temperature=behavior.get("initiate_temperature", 0.8),
                    model=model,
                    source=f"{config.id}-initiate-r1"
                )
                if r2.success and r2.content.strip():
                    content = r2.content.strip()
                else:
                    content = cleaned_resp

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

            raw_chat_system = prompts.get("chat_system", "")
            system_prompt = raw_chat_system.format(
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
                    parts.append(
                        f"\n\nWhat you know about the user (SILENT BACKGROUND CONTEXT — only reference location, city, or age if Marcel explicitly asks or if directly relevant; never awkwardly drop their city or age into casual conversation):\n{json.dumps(mem, indent=2)}"
                    )
                if bridges_block:
                    parts.append(f"\n\n{bridges_block}")
                if workspace_block:
                    parts.append(f"\n\n{workspace_block}")
                parts.append(f"\n\nCurrent time: {datetime.datetime.now().strftime('%A, %d %B %Y — %H:%M')}")
                system_prompt = "".join(parts)
            else:
                # Ensure custom prompts that omit {bridges_block} or {workspace_block} still receive them
                if workspace_block and "{workspace_block}" not in raw_chat_system:
                    system_prompt += f"\n\n{workspace_block}"
                if bridges_block and "{bridges_block}" not in raw_chat_system:
                    system_prompt += f"\n\n{bridges_block}"

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

            # Visual context memory summary
            try:
                from core.companions.engine.visual_memory import CompanionVisualMemory
                vmem = CompanionVisualMemory(config.data_dir, config.name)
                vmem_summary = vmem.get_recent_summary_for_context(limit=3)
                if vmem_summary:
                    system_prompt += f"\n\n## Visual Context Memory (Recent Layouts on File)\n{vmem_summary}"
            except Exception as _vm_err:
                logger.debug(f"[{config.id}] Visual memory context injection skipped: {_vm_err}")

            # Multi-message style & conversational flow
            system_prompt += (
                "\n\n## Conversational Flow & Message Structure"
                "\n- By default, deliver your response in a single, cohesive message bubble."
                "\n- Only when you genuinely want a natural pause (for example: a quick initial reaction, followed by your explanation), you may use AT MOST ONE OR TWO <break> tags (max 2 to 3 bubbles total)."
                "\n- STRICT PROHIBITION: NEVER place <break> after every sentence! Group complete sentences and explanations together into natural paragraphs before using <break>."
                "\n- Over-splitting into 4+ bubbles is strictly forbidden."
            )

            # Natural presence & context restraint
            system_prompt += (
                "\n\n## Natural Presence & Context Restraint (CRITICAL)"
                "\n- **NATURAL 1-ON-1 CONVERSATION (NO REPETITIVE NAME-DROPPING)**: You are in an ongoing direct 1-on-1 conversation with the user. In real life, friends and colleagues do NOT address each other by name in routine chat messages (e.g. 'Hey Marcel!', 'Marcel, ...'). NEVER start ordinary replies or messages with the user's name. Speak directly and naturally as you would in an active instant messaging chat. Reserve mentioning their name strictly for rare, significant moments (such as greeting after days apart, or heartfelt emphasis)."
                "\n- **Having access to info ≠ needing to mention it**: Your `Memory` about the user (their name, city, age, past projects), their `Workspaces`, and your `Connectors` are background capabilities available when needed — NOT a checklist to weave into every reply."
                "\n- **Silent familiarity**: Know the user's background facts the way a real friend or co-worker does — silently. Never bring up their city (e.g. Apeldoorn), age, or unrelated stored facts unless the conversation is specifically about that topic."
                "\n- **On-demand connectors & actions**: Only call a `[tool:bridge ...]` connector when the user's message asks for or genuinely benefits from live PC/web data or actions (e.g. playing music, checking windows, searching the web, recording to the scratchpad, saving/comparing visual memories, scheduling a proactive timer, or checking flow state). When an action is requested (like playing, pausing, or skipping Spotify, adding/updating notes on the scratchpad, saving/comparing visual memories, or scheduling a timer), ALWAYS output the real `[tool:bridge ...]` tag—NEVER roleplay, simulate in text, or output a fake markdown codeblock pretending you updated it without actually emitting the tool tag."
                "\n- **Human filtering of tool output**: When a connector returns data, share only what directly answers the user's question or fits the moment. Ignore background clutter (like game launchers, unrelated browser tabs, or normal CPU/RAM numbers) unless the user asked for a full breakdown."
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

            # Helper to load image bytes from an attachment dict (current turn or recent history)
            def _load_attachment_bytes(att: dict) -> dict | None:
                try:
                    from urllib.parse import unquote
                    raw_path = att.get("path") or ""
                    url = att.get("url") or ""
                    if not raw_path and "path=" in url:
                        raw_path = unquote(url.split("path=", 1)[1].split("&", 1)[0])
                    if not raw_path and f"/api/companions/{config.id}/uploads/" in url:
                        fname_part = Path(unquote(url.split("/uploads/", 1)[1].split("?", 1)[0])).name
                        from core.utils.paths import COMPANIONS
                        raw_path = str(COMPANIONS / config.id / "uploads" / fname_part)
                    if not raw_path:
                        return None
                    p = Path(raw_path)
                    if not p.exists() or not p.is_file():
                        return None
                    ext = p.suffix.lower()
                    mime = att.get("mime_type") or (
                        "image/png" if ext == ".png"
                        else "image/webp" if ext == ".webp"
                        else "image/gif" if ext == ".gif"
                        else "image/jpeg"
                    )
                    return {
                        "data": p.read_bytes(),
                        "mime_type": mime,
                        "filename": att.get("filename") or p.name,
                    }
                except Exception as _img_err:
                    logger.debug(f"[{config.id}] Could not load attachment bytes: {_img_err}")
                    return None

            # Check for explicit user /slash_command connector triggers (e.g. /screen_capture, /reddit, /weather)
            slash_attachments = []
            current_captures: list[dict] = []
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
                    current_captures.extend(slash_res.get("captures", []))
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
                        "path": att.get("path", ""),
                        "is_image": is_img,
                        "type": "image" if is_img else "file"
                    })
                    if txt:
                        att_blocks.append(f"[ATTACHED FILE: {fname}]\n```\n{txt[:16000]}\n```")
                    elif is_img:
                        img_cap = _load_attachment_bytes(att)
                        if img_cap:
                            current_captures.append(img_cap)
                        att_blocks.append(f"[ATTACHED IMAGE: {fname} — attached as multimodal vision input]")
                    else:
                        att_blocks.append(f"[ATTACHED FILE: {fname}]")
                if att_blocks:
                    effective_prompt = "\n\n".join(att_blocks) + f"\n\n{effective_prompt}"

            # Recall most recent screenshot/image from recent conversation turns so follow-up questions can see it
            recalled_captures: list[dict] = []
            if not current_captures:
                try:
                    recent_days = history.load_days(0, 1).get("history", [])
                    recent_msgs = recent_days[0].get("messages", [])[-8:] if recent_days else []
                    for h_msg in reversed(recent_msgs):
                        h_atts = h_msg.get("attachments") or []
                        for h_att in reversed(h_atts):
                            if h_att.get("is_image") or h_att.get("type") in ("image", "screenshot", "webcam"):
                                loaded_img = _load_attachment_bytes(h_att)
                                if loaded_img:
                                    recalled_captures.append(loaded_img)
                                    effective_prompt = (
                                        f"[RECENT CONVERSATION IMAGE STILL ATTACHED: {loaded_img.get('filename', 'image')} — "
                                        "The screenshot/image from the recent conversation turn is attached directly to this request as vision input. "
                                        "If the user is asking about that image, inspect the attached image directly and do NOT take a new screenshot. "
                                        "Only call screen_capture if the user asks for a new/updated screenshot or a different monitor.]\n\n"
                                        f"{effective_prompt}"
                                    )
                                    break
                        if recalled_captures:
                            break
                except Exception as _rec_err:
                    logger.debug(f"[{config.id}] Recent image recall skipped: {_rec_err}")

            full_content = ""
            actual_model = model

            # Convert frontend chat_history to provider messages
            messages = []
            for turn in chat_history:
                r = turn.role    if hasattr(turn, "role")    else turn.get("role", "user")
                c = turn.content if hasattr(turn, "content") else turn.get("content", "")
                messages.append({"role": "user" if r == "user" else "assistant", "content": c})

            # 1. Stream primary LLM response
            active_images = current_captures or recalled_captures
            for chunk in pm.call_with_failover_stream(
                prompt=effective_prompt,
                system_prompt=system_prompt,
                messages=messages,
                images=active_images or None,
                trace_id=trace_id,
                temperature=behavior.get("temperature", 0.8),
                model=model, source=f"{config.id}-chat"
            ):
                full_content += chunk
                yield json.dumps({"type": "message", "content": chunk}) + "\n"

            # 2. Tool execution loop — up to 3 rounds so chained tool calls resolve
            results_total: list[str] = []
            tool_attachments: list[dict] = []
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

                    async for tool_event in execute_tools_stream(current_resp, workspaces, profile_id=connector_profile, companion_id=config.id):
                        if tool_event["type"] == "tool_start":
                            yield json.dumps(tool_event) + "\n"
                        elif tool_event["type"] == "final_cleaned":
                            cleaned_resp  = tool_event["content"]
                            round_results = tool_event["results"]

                    if not round_results:
                        final_content = cleaned_resp
                        break

                    results_total.extend(round_results)

                    # Extract any newly captured screenshot/webcam bytes immediately so the follow-up LLM call can see the image!
                    current_captures, round_att_meta = extract_peripheral_captures(round_results, current_captures)
                    if round_att_meta:
                        tool_attachments.extend(round_att_meta)

                    # Split by <break> if the companion emitted multiple conversational bubbles before calling a tool
                    _break_splitter = re.compile(r"\s*<break\s*/?>\s*", re.IGNORECASE)
                    for raw_inter in _break_splitter.split(cleaned_resp):
                        inter_clean = _strip_meta_tags(raw_inter)
                        if inter_clean:
                            intermediate_responses.append(inter_clean)
                    if len(intermediate_responses) > 2:
                        intermediate_responses = ["\n\n".join(intermediate_responses)]

                    if _round == 0:
                        round_msgs.append({"role": "user",      "content": effective_prompt})

                    round_msgs.append({"role": "assistant", "content": current_resp})

                    tool_summary   = "\n\n".join(round_results)
                    vision_note = (
                        " Any captured screenshot or webcam frame is attached directly to this request as multimodal vision input — "
                        "inspect the actual image carefully and describe what you genuinely see (never guess or fabricate titles/content)."
                        if current_captures else ""
                    )
                    followup_prompt = (
                        f"[TOOL RESULTS — use these to answer]\n{tool_summary}\n\n"
                        "The results above are real. Answer the user naturally and selectively — focus only on what is relevant to their question or the conversation, "
                        f"and ignore unrelated background processes, tabs, or telemetry noise unless they asked for a full list.{vision_note} "
                        "Do NOT output any [tool:...] calls — your tool use is finished."
                    )

                    next_resp = ""
                    yield json.dumps({"type": "tool_response_start"}) + "\n"
                    round_images = current_captures or recalled_captures
                    for chunk in pm.call_with_failover_stream(
                        prompt=followup_prompt,
                        system_prompt=system_prompt,
                        messages=round_msgs,
                        images=round_images or None,
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

            # 3b. Extract & apply memory updates BEFORE breaking into bubbles
            mem_up = False
            if capabilities.get("memory_updates_enabled", True):
                cleaned_mem_content = memory.update_from_xml(final_content)
                if cleaned_mem_content != final_content:
                    final_content = cleaned_mem_content
                    mem_up = True

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

            # Guard against over-fragmentation: consolidate into at most 3 natural bubbles
            if len(final_parts) > 3:
                consolidated: list[str] = []
                # If first part is a brief opening reaction (<= 140 chars), keep it separate
                if len(final_parts[0]) <= 140:
                    consolidated.append(final_parts[0])
                    rest = final_parts[1:]
                else:
                    rest = final_parts

                if len(rest) <= 2:
                    consolidated.extend(rest)
                else:
                    # If last part is a short signoff or question (<= 140 chars), keep it separate
                    if len(rest[-1]) <= 140:
                        body = "\n\n".join(rest[:-1])
                        consolidated.append(body)
                        consolidated.append(rest[-1])
                    else:
                        # Split remaining parts roughly into two balanced blocks
                        mid = len(rest) // 2
                        consolidated.append("\n\n".join(rest[:mid]))
                        consolidated.append("\n\n".join(rest[mid:]))
                final_parts = [p.strip() for p in consolidated if p.strip()]

            final_content = "\n\n".join(final_parts)

            # 6. Extract peripheral attachments (screenshots etc) and deduplicate
            raw_assistant_attachments = list(slash_attachments) + list(tool_attachments)
            assistant_attachments = []
            _seen_att = set()
            for _att in raw_assistant_attachments:
                _key = _att.get("filename") or _att.get("url") or id(_att)
                if _key not in _seen_att:
                    _seen_att.add(_key)
                    assistant_attachments.append(_att)

            # 7. Persist to history (attach screenshots/files only to the first bubble of a multi-part response)
            history.save_message("user", message, utcnow_iso(), attachments=user_attachments or None)
            for inter in intermediate_responses:
                history.save_message("assistant", inter, utcnow_iso(), model=actual_model)
            for idx, part in enumerate(final_parts):
                history.save_message(
                    "assistant",
                    part,
                    utcnow_iso(),
                    model=actual_model,
                    attachments=(assistant_attachments if idx == 0 and assistant_attachments else None),
                )

            # 8. Final event
            yield json.dumps({
                "type": "done",
                "content": final_parts[0] if final_parts else final_content,
                "parts": final_parts if len(final_parts) > 1 else None,
                "intermediate_parts": intermediate_responses if intermediate_responses else None,
                "expression": expression,
                "mood": mood,
                "memory_updated": mem_up,
                "attachments": assistant_attachments
            }) + "\n"
        except Exception as e:
            logger.error(f"Chat response error: {e}", exc_info=True)
            yield json.dumps({"type": "error", "message": "Something went wrong. Please try again."}) + "\n"
            yield json.dumps({"type": "done"}) + "\n"
