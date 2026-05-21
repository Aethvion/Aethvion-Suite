"""
core/companions/companion_engine.py
═══════════════════════════════════
Unified, data-driven engine for all Aethvion companions.
Handles LLM logic, tool execution, and dynamic personality evolution.
"""

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
from core.providers.provider_manager import ProviderManager
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
        try:
            raw = config._raw_config
            behavior = raw.get("behavior", {})
            capabilities = raw.get("capabilities", {})
            prompts = raw.get("prompts", {})
            memory = CompanionMemory(config.data_dir, raw.get("personality_defaults", {}))
            history = CompanionHistory(config.history_dir, config.name,
                                       lambda s: format_time_diff(s, raw.get("time_context", {})))

            memory.initialize()
            mem_data = memory.load()
            bridges_block = build_bridges_capabilities(capabilities) if capabilities.get("tools_enabled") else ""

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

            # ── Fallback system prompt for companions without one ──────────────
            # Custom companions created via the UI typically have no chat_system set.
            # Build a sensible prompt from their stored base_info so they know who they are.
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
                parts.append(f"\n\nCurrent time: {datetime.datetime.now().strftime('%A, %d %B %Y — %H:%M')}")
                system_prompt = "".join(parts)

            # ── Expression awareness ──────────────────────────────────────────
            # Always tell the companion what expressions it has and how to signal them.
            # The engine strips <expression>...</expression> tags from the final content
            # and uses them to update the portrait image shown in the UI.
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

            # ── Multi-message style ───────────────────────────────────────────
            # Companions can split responses into separate chat bubbles using <break>.
            # This is a personality feature — use it to feel more natural and human.
            system_prompt += (
                "\n\n## Multi-Message Style"
                "\nYou can split your response into separate messages using <break> between them."
                "\nThis feels more natural — like texting, where people send multiple short messages"
                "\ninstead of one long wall of text."
                "\nUse it for: reactions before details, dramatic pauses, separating distinct thoughts."
                "\nExample: 'Oh wow, really?! <break> Let me check that for you... <break> Here's what I found!'"
                "\nKeep each part focused. Don't use more than 3 breaks per response."
                "\nFor short or simple answers, a single message is fine."
            )

            model = get_preferences_manager().get(config.id, {}).get("model", config.default_model)
            pm = ProviderManager()
            trace_id = f"{config.id}-chat-{uuid.uuid4().hex[:8]}"

            full_content = ""
            actual_model = model

            # Convert frontend chat_history to provider messages
            # Handles both Pydantic model objects (attr access) and plain dicts (.get)
            messages = []
            for turn in chat_history:
                r = turn.role    if hasattr(turn, "role")    else turn.get("role", "user")
                c = turn.content if hasattr(turn, "content") else turn.get("content", "")
                messages.append({"role": "user" if r == "user" else "assistant", "content": c})

            # 1. Stream primary LLM response
            for chunk in pm.call_with_failover_stream(
                prompt=message,
                system_prompt=system_prompt,
                messages=messages,
                trace_id=trace_id,
                temperature=behavior.get("temperature", 0.8),
                model=model, source=f"{config.id}-chat"
            ):
                full_content += chunk
                yield json.dumps({"type": "message", "content": chunk}) + "\n"

            # 2. Tool execution loop — up to 3 rounds so chained tool calls resolve
            #    Round 0: execute tools in the first LLM response
            #    Round 1+: LLM may still emit tools; keep going until clean or exhausted
            results_total: list[str] = []
            intermediate_responses: list[str] = []  # cleaned first-response(s) before tool results
            final_content  = full_content
            current_resp   = full_content
            round_msgs     = list(messages)   # grows as rounds progress

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

                    async for tool_event in execute_tools_stream(current_resp, workspaces):
                        if tool_event["type"] == "tool_start":
                            yield json.dumps(tool_event) + "\n"
                        elif tool_event["type"] == "final_cleaned":
                            cleaned_resp  = tool_event["content"]
                            round_results = tool_event["results"]

                    if not round_results:
                        # No tool calls in this response — done
                        final_content = cleaned_resp
                        break

                    results_total.extend(round_results)

                    # Save the cleaned intermediate response (e.g. "I'll check that for you!")
                    inter_clean = _strip_meta_tags(cleaned_resp)
                    if inter_clean:
                        intermediate_responses.append(inter_clean)

                    # Build growing message context for next LLM call
                    if _round == 0:
                        # First round: the original user turn comes before the assistant
                        round_msgs.append({"role": "user",      "content": message})
                    # else: the previous followup_prompt was already appended below

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

                    # Save the followup prompt so the next round can build on it
                    round_msgs.append({"role": "user", "content": followup_prompt})
                    current_resp = next_resp

                else:
                    # Exhausted all rounds — keep whatever the last response was
                    final_content = current_resp

            results = results_total

            # 3. Extract Expression & Mood — prefer final response, fall back to first
            scan_content = final_content if results_total else full_content
            expression = behavior.get("default_expression", "default")
            mood = behavior.get("default_mood", "calm")
            exp_match = re.search(r"<expression>(.*?)</expression>", scan_content, re.IGNORECASE)
            if exp_match:
                expression = exp_match.group(1).strip().lower()
            mood_match = re.search(r"<mood>(.*?)</mood>", scan_content, re.IGNORECASE)
            if mood_match:
                mood = mood_match.group(1).strip().lower()

            # 4. Clean meta-tags from final_content (expression, mood, break)
            final_content = _strip_meta_tags(
                re.sub(r"<(?:expression|mood)>.*?</(?:expression|mood)>", "", final_content,
                       flags=re.DOTALL | re.IGNORECASE)
            )

            # 5. Handle Memory Updates (using memory-aware XML logic)
            mem_up = False
            if capabilities.get("memory_updates_enabled", True):
                cleaned_mem_content = memory.update_from_xml(final_content)
                if cleaned_mem_content != final_content:
                    final_content = cleaned_mem_content
                    mem_up = True

            # 6. Extract peripheral attachments (screenshots etc)
            attachments = []
            if results:
                _, attachments = extract_peripheral_captures(results, [])

            # 6b. Split final_content by <break> into separate companion messages
            _break_re = re.compile(r"\s*<break\s*/?>\s*", re.IGNORECASE)
            final_parts = [p.strip() for p in _break_re.split(final_content) if p.strip()]
            if not final_parts:
                final_parts = [final_content] if final_content.strip() else []

            # 7. Persist to history — save EVERY companion message the user sees
            history.save_message("user", message, utcnow_iso())
            # Intermediate tool-call responses (e.g. "I'll check that for you!")
            for inter in intermediate_responses:
                history.save_message("assistant", inter, utcnow_iso(), model=actual_model)
            # Final response parts (split by <break>)
            for part in final_parts:
                history.save_message("assistant", part, utcnow_iso(),
                                     model=actual_model, attachments=attachments)

            # 8. Final event — include parts list so the frontend can render each as its own bubble
            yield json.dumps({
                "type": "done",
                "content": final_parts[0] if final_parts else final_content,
                "parts": final_parts if len(final_parts) > 1 else None,
                "expression": expression,
                "mood": mood,
                "memory_updated": mem_up,
                "attachments": attachments
            }) + "\n"
        except Exception as e:
            logger.error(f"Chat response error: {e}", exc_info=True)
            yield json.dumps({"type": "error", "message": "Something went wrong. Please try again."}) + "\n"
            yield json.dumps({"type": "done"}) + "\n"
