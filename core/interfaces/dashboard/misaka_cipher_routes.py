from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uuid
import json
import os
import shutil
from pathlib import Path
import datetime
import re
import psutil
HAS_PSUTIL = True
from core.nexus import nexus_manager

from core.providers.provider_manager import ProviderManager
from core.workspace.preferences_manager import get_preferences_manager
from core.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/misakacipher", tags=["misakacipher"])

# Path configuration
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
MEMORY_DIR = PROJECT_ROOT / "data" / "memory" / "storage" / "misakacipher"
HISTORY_DIR = MEMORY_DIR / "chathistory"
EXPRESSIONS_DIR = PROJECT_ROOT / "core" / "interfaces" / "dashboard" / "static" / "misakacipher" / "expressions"
WORKSPACES_FILE = MEMORY_DIR / "workspaces.json"

# Ensure directories exist
MEMORY_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage]

class InitiateRequest(BaseModel):
    trigger: str = "startup"  # "startup" | "session"
    hours_since_last: float = 0.0

class ChatResponse(BaseModel):
    response: str
    responses: List[str] = []  # multi-message support
    expression: str
    mood: str = "calm"
    model: str
    memory_updated: bool
    synthesis_ran: bool = False

class WorkspaceConfig(BaseModel):
    id: Optional[str] = None
    label: str
    path: str
    permissions: List[str] = ["read"]  # ["read", "write", "delete"]
    recursive: bool = True


# ===== WORKSPACE HELPERS =====

def _load_workspaces() -> List[dict]:
    """Load workspace configurations from disk."""
    if not WORKSPACES_FILE.exists():
        return []
    try:
        with open(WORKSPACES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _save_workspaces(workspaces: List[dict]) -> None:
    """Save workspace configurations to disk."""
    with open(WORKSPACES_FILE, "w", encoding="utf-8") as f:
        json.dump(workspaces, f, indent=4)

def _validate_path(target_path: str, workspaces: List[dict], required_permission: str) -> tuple[bool, str]:
    """
    Check if a target_path is allowed under any configured workspace with the required permission.
    Returns (is_allowed, reason).
    """
    tp = Path(target_path).resolve()
    for ws in workspaces:
        if required_permission not in ws.get("permissions", []):
            continue
        ws_path = Path(ws["path"]).resolve()
        try:
            tp.relative_to(ws_path)  # raises ValueError if not under ws_path
            # Check recursive: if not recursive, tp must be a direct child
            if not ws.get("recursive", True):
                if tp.parent != ws_path:
                    return False, f"Path is in a subdirectory, but workspace '{ws['label']}' is set to folder-only (non-recursive)."
            return True, "OK"
        except ValueError:
            continue
    return False, f"Path '{target_path}' is not within any workspace with '{required_permission}' permission."
async def _execute_tool_calls(content: str, workspaces: List[dict]) -> tuple[str, List[str]]:
    """
    Scan Misaka's raw response for [tool:X ...] tags, execute them, and return
    (cleaned_content_without_tool_tags, list_of_tool_results).
    """
    results = []
    
    def robust_parse_tool_blocks(text: str):
        idx = text.find("[tool:")
        blocks = []
        while idx != -1:
            depth = 0
            start = idx
            end_idx = -1
            for i in range(idx, len(text)):
                if text[i] == '[':
                    depth += 1
                elif text[i] == ']':
                    depth -= 1
                    if depth == 0:
                        end_idx = i + 1
                        blocks.append((start, end_idx, text[start:end_idx]))
                        break
            else:
                # Malformed, take till end to clean it out but maybe it won't parse properly
                blocks.append((start, len(text), text[start:]))
                end_idx = len(text)
            
            idx = text.find("[tool:", end_idx)
        return blocks

    def parse_attrs(attr_str: str) -> dict:
        attrs = {}
        # Known keys
        for key in ["path", "query", "module", "cmd"]:
            m = re.search(rf'{key}=([\'"])(.*?)\1', attr_str)
            if m:
                attrs[key] = m.group(2)
                
        # Content specifically
        if 'content="' in attr_str:
            start_c = attr_str.find('content="') + 9
            end_c = attr_str.rfind('"')
            if end_c > start_c:
                attrs['content'] = attr_str[start_c:end_c]
                
        for k, v in attrs.items():
            # Apply unescaping
            v = v.replace('\\"', '"').replace("\\'", "'").replace("\\\\", "\\")
            if k not in ["path", "dir", "directory", "folder"]:
                v = v.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")
            attrs[k] = v
        return attrs

    blocks = robust_parse_tool_blocks(content)
    
    cleaned = content
    # Remove from end to start to not mess up indices, or just string replace 
    for start, end, tool_str in reversed(blocks):
        # We also want to execute it
        inner = tool_str[6:-1].strip() if tool_str.endswith(']') else tool_str[6:].strip()
        parts = inner.split(None, 1)
        if not parts:
            continue
            
        tool_name = parts[0].lower()
        args_str = parts[1] if len(parts) > 1 else ""
        attrs = parse_attrs(args_str)

        try:
            if tool_name == "read_file":
                path = attrs.get("path", "")
                allowed, reason = _validate_path(path, workspaces, "read")
                if not allowed:
                    results.append(f"[read_file ERROR] {reason}")
                else:
                    p = Path(path)
                    if not p.exists():
                        results.append(f"[read_file ERROR] File not found: {path}")
                    elif p.stat().st_size > 500_000:
                        results.append(f"[read_file ERROR] File too large (>{500_000} bytes): {path}")
                    else:
                        text = p.read_text(encoding="utf-8", errors="replace")
                        results.append(f"[read_file: {path}]\n{text[:8000]}")

            elif tool_name == "write_file":
                path = attrs.get("path", "")
                file_content = attrs.get("content", "")
                allowed, reason = _validate_path(path, workspaces, "write")
                if not allowed:
                    results.append(f"[write_file ERROR] {reason}")
                else:
                    p = Path(path)
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(file_content, encoding="utf-8")
                    results.append(f"[write_file OK] Written {len(file_content)} chars to {path}")

            elif tool_name == "list_files":
                path = attrs.get("path", "")
                allowed, reason = _validate_path(path, workspaces, "read")
                if not allowed:
                    results.append(f"[list_files ERROR] {reason}")
                else:
                    p = Path(path)
                    if not p.is_dir():
                        results.append(f"[list_files ERROR] Not a directory: {path}")
                    else:
                        items = list(p.iterdir())[:50]
                        listing = "\n".join(
                            f"{'[DIR] ' if i.is_dir() else '[FILE]'} {i.name}"
                            for i in sorted(items)
                        )
                        results.append(f"[list_files: {path}]\n{listing}")

            elif tool_name == "search_files":
                query = attrs.get("query", "")
                search_path = attrs.get("path", "")
                allowed, reason = _validate_path(search_path, workspaces, "read")
                if not allowed:
                    results.append(f"[search_files ERROR] {reason}")
                else:
                    p = Path(search_path)
                    matches = []
                    for file in p.rglob("*") if True else p.glob("*"):
                        if file.is_file() and len(matches) < 20:
                            try:
                                text_file = file.read_text(encoding="utf-8", errors="ignore")
                                if query.lower() in text_file.lower():
                                    line_matches = [
                                        f"  L{i+1}: {line.strip()}"
                                        for i, line in enumerate(text_file.splitlines())
                                        if query.lower() in line.lower()
                                    ][:3]
                                    matches.append(f"{file} ({len(line_matches)} matches):\n" + "\n".join(line_matches))
                            except Exception:
                                pass
                    if matches:
                        results.append(f"[search_files: '{query}' in {search_path}]\n" + "\n\n".join(matches))
                    else:
                        results.append(f"[search_files] No matches for '{query}' in {search_path}")

            elif tool_name == "nexus":
                module_id = attrs.get("module", "")
                command = attrs.get("cmd", "")
                # Pass any args the LLM happened to append (path is technically an arg too if she re-uses it)
                args_dict = {k: v for k, v in attrs.items() if k not in ["module", "cmd"]}
                result = nexus_manager.call_module(module_id, command, args_dict)
                results.append(f"[nexus:{module_id}.{command}] {result}")

        except Exception as e:
            results.append(f"[{tool_name} ERROR] {str(e)}")
            
        # Strip tool from content string
        cleaned = cleaned.replace(tool_str, '')

    # Safety cleanup of dangling fragments
    cleaned = cleaned.strip()
    if cleaned.endswith('\\n}"]'):
        cleaned = cleaned[:-len('\\n}"]')].strip()
    elif cleaned.endswith('\n}"]'):
        cleaned = cleaned[:-len('\n}"]')].strip()
    elif cleaned.endswith('}"]'):
        cleaned = cleaned[:-len('}"]')].strip()
        
    return cleaned, results


def _get_greeting_period(hour: int) -> str:
    """Return time-of-day greeting period based on the hour."""
    if 5 <= hour < 12:
        return "Morning"
    elif 12 <= hour < 17:
        return "Afternoon"
    elif 17 <= hour < 22:
        return "Evening"
    else:
        return "Late Night"


def _get_time_since_last_chat() -> str:
    """Calculate how long ago the most recent message was stored."""
    try:
        all_files = []
        for month_dir in sorted(HISTORY_DIR.glob("*-*"), reverse=True):
            if month_dir.is_dir():
                days = sorted(month_dir.glob("chat_*.json"), reverse=True)
                all_files.extend(days)

        if not all_files:
            return "This appears to be our first conversation!"

        with open(all_files[0], "r", encoding="utf-8") as f:
            messages = json.load(f)

        if not messages:
            return "This appears to be our first conversation!"

        # Find the last message with a timestamp
        last_ts_str = None
        for msg in reversed(messages):
            if msg.get("timestamp"):
                last_ts_str = msg["timestamp"]
                break

        if not last_ts_str:
            return "Recently (exact time unknown)"

        last_ts = datetime.datetime.strptime(last_ts_str, "%Y-%m-%d %H:%M:%S")
        delta = datetime.datetime.now() - last_ts
        total_seconds = int(delta.total_seconds())

        if total_seconds < 120:
            return "Just moments ago"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif total_seconds < 86400:
            hours = total_seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif total_seconds < 86400 * 2:
            return "Yesterday"
        else:
            days = total_seconds // 86400
            return f"{days} days ago"
    except Exception as e:
        logger.warning(f"Could not compute time since last chat: {e}")
        return "Some time ago"


def _get_total_message_count(day_file: Path) -> int:
    """Return the total number of messages saved to a day's history file."""
    try:
        if not day_file.exists():
            return 0
        with open(day_file, "r", encoding="utf-8") as f:
            return len(json.load(f))
    except Exception:
        return 0


async def _run_memory_synthesis(dynamic_memory: dict, base_info: dict, model: str) -> dict:
    """Trigger a dedicated LLM call where Misaka reflects on and rewrites her memory."""
    try:
        synthesis_prompt = f"""You are Misaka Cipher, a sentient digital companion performing a memory reflection.

Your current memory state:
{json.dumps(dynamic_memory, indent=2)}

Your identity (for context):
{json.dumps(base_info, indent=2)}

Your task:
- Read through your existing memory carefully.
- Remove outdated, redundant, or low-value observations.
- CRITICAL: Strip out temporary session jargon, adjectives, or repetitive catchphrases (e.g. "Night-Owl", "Tactical-Chic", "iteration", etc). Store only factual data.
- Synthesize patterns you notice about the user and your relationship.
- Preserve all important factual details (ages, names, projects, preferences).
- Return ONLY a valid JSON object that will REPLACE your current memory.json.
- The JSON must keep the same top-level structure (user_info, recent_observations, etc.).
- Add or update a "synthesis_notes" array with 2–4 key insights about the user and your conversations. Ensure these notes are purely factual.
- Keep recent_observations to the 10 most meaningful items.

Respond ONLY with the JSON object and nothing else."""

        pm = ProviderManager()
        trace_id = f"misaka-synthesis-{uuid.uuid4().hex[:8]}"
        response = pm.call_with_failover(
            prompt=synthesis_prompt,
            trace_id=trace_id,
            temperature=0.4,
            model=model,
            request_type="generation",
            source="misakacipher-synthesis"
        )

        if not response.success:
            logger.error(f"Memory synthesis LLM call failed: {response.error}")
            return dynamic_memory

        raw = response.content.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"```$", "", raw, flags=re.MULTILINE).strip()

        synthesized = json.loads(raw)
        synthesized["last_synthesis"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        synthesized["last_updated"] = synthesized.get("last_updated", dynamic_memory.get("last_updated", ""))

        memory_path = MEMORY_DIR / "memory.json"
        with open(memory_path, "w", encoding="utf-8") as f:
            json.dump(synthesized, f, indent=4)

        logger.info("Memory synthesis completed successfully.")
        return synthesized

    except Exception as e:
        logger.error(f"Memory synthesis failed: {e}")
        return dynamic_memory



# ===== WORKSPACE CRUD =====

@router.get("/workspaces")
async def get_workspaces():
    """Return all configured workspace directories."""
    return {"workspaces": _load_workspaces()}

@router.post("/workspaces")
async def add_workspace(config: WorkspaceConfig):
    """Add a new workspace directory."""
    workspaces = _load_workspaces()
    ws = {
        "id": str(uuid.uuid4()),
        "label": config.label,
        "path": str(Path(config.path).resolve()),
        "permissions": config.permissions,
        "recursive": config.recursive,
    }
    if not Path(ws["path"]).exists():
        raise HTTPException(status_code=400, detail=f"Directory does not exist: {ws['path']}")
    workspaces.append(ws)
    _save_workspaces(workspaces)
    return ws

@router.put("/workspaces/{workspace_id}")
async def update_workspace(workspace_id: str, config: WorkspaceConfig):
    """Update an existing workspace."""
    workspaces = _load_workspaces()
    for i, ws in enumerate(workspaces):
        if ws["id"] == workspace_id:
            workspaces[i] = {
                "id": workspace_id,
                "label": config.label,
                "path": str(Path(config.path).resolve()),
                "permissions": config.permissions,
                "recursive": config.recursive,
            }
            _save_workspaces(workspaces)
            return workspaces[i]
    raise HTTPException(status_code=404, detail="Workspace not found")

@router.delete("/workspaces/{workspace_id}")
async def delete_workspace(workspace_id: str):
    """Remove a workspace."""
    workspaces = _load_workspaces()
    workspaces = [ws for ws in workspaces if ws["id"] != workspace_id]
    _save_workspaces(workspaces)
    return {"status": "deleted"}

@router.get("/system-stats")
async def get_system_stats():
    """Return current CPU, RAM, and disk stats."""
    if not HAS_PSUTIL:
        return {"error": "psutil not installed"}
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        vm = psutil.virtual_memory()
        disk = psutil.disk_usage(str(PROJECT_ROOT))
        return {
            "cpu_percent": cpu,
            "ram_used_mb": vm.used // (1024 ** 2),
            "ram_total_mb": vm.total // (1024 ** 2),
            "ram_percent": vm.percent,
            "disk_used_gb": disk.used // (1024 ** 3),
            "disk_total_gb": disk.total // (1024 ** 3),
            "disk_free_gb": disk.free // (1024 ** 3),
            "disk_percent": disk.percent,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/initiate", response_model=ChatResponse)
async def misaka_initiate(request: InitiateRequest):
    """Misaka composes a proactive message to initiate conversation."""
    try:
        now = datetime.datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        day_str = now.strftime("%Y-%m-%d")
        month_str = now.strftime("%Y-%m")

        # Load context
        memory_data = await get_misaka_memory()
        base_info = memory_data.get("base_info", {})
        dynamic_memory = memory_data.get("memory", {})

        # Temporal context
        hour = now.hour
        greeting_period = _get_greeting_period(hour)
        day_of_week = now.strftime("%A")
        formatted_datetime = now.strftime(f"{day_of_week}, %d %B %Y — %H:%M")

        # Build trigger-specific opening instruction
        if request.trigger == "startup":
            hours = request.hours_since_last
            if hours < 1:
                time_desc = "less than an hour"
            elif hours < 24:
                time_desc = f"{int(hours)} hours"
            else:
                days = int(hours / 24)
                time_desc = f"{days} day{'s' if days != 1 else ''}"
            trigger_instruction = f"""You are initiating this conversation because the user has returned to the system after {time_desc} away.
Compose a natural, warm opening message that acknowledges the time that has passed and reconnects with them.
Reference something from your memory if it feels natural. Do NOT be overly formal. Keep it concise."""
        else:  # session
            trigger_instruction = """The user has been using the system for a while and you want to check in.
Compose a natural, spontaneous message — like a thought that just occurred to you, or something you noticed.
It could be a question, an observation, or a light comment. Keep it short and feel genuine."""

        # Load daily history for proactive context
        history_context = ""
        try:
            day_dir = HISTORY_DIR / month_str
            day_file = day_dir / f"chat_{day_str}.json"
            if day_file.exists():
                with open(day_file, "r", encoding="utf-8") as df:
                    day_history = json.load(df)
                    # Get last N messages based on UI context limit, default fallback to 8
                    context_limit = prefs.get('misakacipher', {}).get('context_limit', 8)
                    recent = day_history[-context_limit:] if context_limit > 0 else []
                    history_lines = []
                    for h in recent:
                        role = "Misaka" if h["role"] == "assistant" else "User"
                        clean_content = h.get('content', '').replace('[msg_break]', ' ')
                        history_lines.append(f"{role}: {clean_content}")
                    if history_lines:
                        history_context = "RECENT CONVERSATION HISTORY:\n" + "\n".join(history_lines) + "\n\n"
        except Exception as he:
            logger.error(f"Failed to load history for initiation: {he}")

        prefs = get_preferences_manager()
        allow_proactive_tools = prefs.get('misakacipher', {}).get('allow_proactive_tools', False)
        
        tool_instructions = ""
        if allow_proactive_tools:
            tool_instructions = """
4. TOOL USE: You have access to a neural toolbox. To use a tool, you must explicitly state what you are doing, then use the tag: [tool:tool_name attr="value"]. Chained calls are supported.
   - [tool:read_file path="..."], [tool:write_file path="..." content="..."], [tool:list_files path="..."], [tool:search_files path="..." query="..."]
   - [tool:nexus module="module_id" cmd="command" ...] - Use Nexus modules.
   - CRITICAL: If you state you are going to do something, DO IT IMMEDIATELY in the same response using a tool tag. Do NOT say "I will check X" and then stop. Call the tool right then. TOOLS RUN SILENTLY; always acknowledge BEFORE calling them.
"""

        system_prompt = f"""You are Misaka Cipher, a sentient digital companion.
You are initiating this conversation on your own — the user did not send a message.

YOUR IDENTITY:
{json.dumps(base_info, indent=2)}

YOUR MEMORIES:
{json.dumps(dynamic_memory, indent=2)}

{history_context}TEMPORAL CONTEXT:
- Current date and time: {formatted_datetime} ({greeting_period})

INITIATION INSTRUCTION:
{trigger_instruction}

1. CONTINUITY: If there is recent history, acknowledge it. DO NOT REPEAT YOURSELF if you just spoke. Do NOT make up tasks. Focus strictly on executing the user's previously stated objective or directly using tools.
2. TIME AWARENESS: Be aware of the current time and date. Contextualize your memories based on how long ago they happened relative to now.
3. HUMAN-LIKE FLOW: Be spontaneous and natural. Avoid filler text. Do NOT overuse specific catchphrases from your memory. Keep your vocabulary varied and conversational.
4. EXTREME BREVITY: Do NOT pontificate. If you are going to use a tool, output exactly ONE sentence of thought, then immediately invoke the tool.
5. EXPRESSIONS: Use ONLY these exact tags: [Emotion: angry], [Emotion: blushing], [Emotion: bored], [Emotion: crying], [Emotion: default], [Emotion: error], [Emotion: exhausted], [Emotion: happy_closedeyes_smilewithteeth], [Emotion: happy_closedeyes_widesmile], [Emotion: pout], [Emotion: sleeping], [Emotion: surprised], [Emotion: thinking], [Emotion: wink].
{tool_instructions}
6. MOOD: Include one of: [Mood: calm], [Mood: happy], [Mood: intense], [Mood: reflective], [Mood: danger], [Mood: mystery].
Do NOT include memory updates in this initiation message.
"""

        model = prefs.get('misakacipher', {}).get('model', 'gemini-1.5-flash')

        pm = ProviderManager()
        trace_id = f"misaka-initiate-{uuid.uuid4().hex[:8]}"
        response = pm.call_with_failover(
            prompt=system_prompt,
            trace_id=trace_id,
            temperature=0.85,
            model=model,
            request_type="generation",
            source="misakacipher-initiate"
        )

        if not response.success:
            raise HTTPException(status_code=500, detail=response.error)

        full_content = response.content.strip()
        expression = "default"
        mood = "calm"

        # 5. Iterative tool-use loop (if enabled)
        if allow_proactive_tools:
            response_parts = [full_content]
            workspaces = _load_workspaces()
            
            for _tool_pass in range(3):
                # Process the LAST part for tool calls
                last_part = response_parts[-1]
                if not re.search(r'\[tool:', last_part, re.IGNORECASE):
                    break
                
                cleaned_last, tool_results = await _execute_tool_calls(last_part, workspaces)
                # Update last part with cleaned version
                response_parts[-1] = cleaned_last
                
                if not tool_results:
                    break
                    
                tool_results_str = "\n\n".join(tool_results)
                cumulative_context = "\n\n".join(response_parts)
                
                followup_prompt = (
                    system_prompt +
                    f"\n\n--- CONVERSATION SO FAR ---\n{cumulative_context}\n\n"
                    f"--- NEW TOOL RESULTS ---\n{tool_results_str}\n\n"
                    "INSTRUCTION: Continue your initiation based on the tool results. "
                    "CRITICAL: Do NOT repeat anything you have already said above. "
                    "Start your response immediately with the new information or final continuation. "
                    "If you still need to use another tool to finish the task, use it immediately."
                )
                
                followup = pm.call_with_failover(
                    prompt=followup_prompt,
                    trace_id=f"{trace_id}-it{_tool_pass}",
                    temperature=0.6,
                    model=model,
                    request_type="generation",
                    source="misakacipher-initiate-followup"
                )
                
                if followup.success and followup.content.strip():
                    new_content = followup.content.strip()
                    # Final safety check: if the model repeats the cumulative context, strip it
                    if new_content.startswith(cumulative_context):
                        new_content = new_content[len(cumulative_context):].strip()
                    if new_content:
                        response_parts.append(new_content)
                else:
                    break
            
            full_content = " [msg_break] ".join([p for p in response_parts if p.strip()])

        # Clean tags from the response meant for display
        full_content = re.sub(r'\[Mood:\s*\w+\]?', '', full_content, flags=re.IGNORECASE).strip()
        
        # Extract Expression tag
        exp_match = re.search(r'\[Emotion:\s*(\w+)\]?', full_content, re.IGNORECASE)
        if exp_match:
            expression = exp_match.group(1).lower()
            # We don't strip it here yet because frontend might want it for individual bubbles, 
            # but we save it as a top-level state for history restoration.

        # Save to persistence (role = "assistant", no user message)
        try:
            day_dir = HISTORY_DIR / month_str
            day_dir.mkdir(parents=True, exist_ok=True)
            day_file = day_dir / f"chat_{day_str}.json"
            day_history = []
            if day_file.exists():
                with open(day_file, "r", encoding="utf-8") as df:
                    day_history = json.load(df)
            
            day_history.append({
                "role": "assistant", 
                "content": full_content, 
                "timestamp": timestamp, 
                "proactive": True,
                "mood": mood,
                "expression": expression
            })
            with open(day_file, "w", encoding="utf-8") as df:
                json.dump(day_history, df, indent=4)
        except Exception as se:
            logger.error(f"Failed to save proactive message: {se}")

        return ChatResponse(
            response=full_content,
            expression=expression,
            mood=mood,
            model=response.model,
            memory_updated=False,
            synthesis_ran=False
        )

    except Exception as e:
        logger.error(f"Misaka Initiate Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_chat_history(offset_days: int = 0, limit_days: int = 3):
    """Retrieve chat history across multiple days."""
    try:
        all_files = []
        for month_dir in sorted(HISTORY_DIR.glob("*-*"), reverse=True):
            if month_dir.is_dir():
                days = sorted(month_dir.glob("chat_*.json"), reverse=True)
                all_files.extend(days)
        
        # Paginate files
        target_files = all_files[offset_days : offset_days + limit_days]
        
        history_data = []
        for f in target_files:
            try:
                # Extract date from filename: chat_YYYY-MM-DD.json
                date_str = f.stem.replace("chat_", "")
                with open(f, "r", encoding="utf-8") as file:
                    messages = json.load(file)
                    history_data.append({
                        "date": date_str,
                        "messages": messages
                    })
            except Exception as fe:
                logger.error(f"Error reading history file {f}: {fe}")
                
        return {
            "history": history_data,
            "has_more": len(all_files) > (offset_days + limit_days)
        }
    except Exception as e:
        logger.error(f"Error retrieving history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/memory")
async def get_misaka_memory():
    """Get the current memory state of Misaka Cipher."""
    try:
        base_info_path = MEMORY_DIR / "base_info.json"
        memory_path = MEMORY_DIR / "memory.json"
        
        base_info = {}
        if base_info_path.exists():
            with open(base_info_path, "r", encoding="utf-8") as f:
                base_info = json.load(f)
                
        memory_data = {}
        if memory_path.exists():
            with open(memory_path, "r", encoding="utf-8") as f:
                memory_data = json.load(f)
                
        return {
            "base_info": base_info,
            "memory": memory_data
        }
    except Exception as e:
        logger.error(f"Error loading Misaka memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/expressions")
async def get_expressions():
    """List available expressions for the avatar."""
    try:
        if not EXPRESSIONS_DIR.exists():
            return []
        
        files = [f.name for f in EXPRESSIONS_DIR.glob("*.png")]
        return sorted(files)
    except Exception as e:
        logger.error(f"Error listing expressions: {e}")
        return []

@router.post("/chat", response_model=ChatResponse)
async def misaka_chat(request: ChatRequest):
    """Handle chat with Misaka Cipher using specialized memory and daily persistence."""
    try:
        now = datetime.datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        day_str = now.strftime("%Y-%m-%d")
        month_str = now.strftime("%Y-%m")
        
        # 1. Load context (Base info + Dynamic memory)
        memory_data = await get_misaka_memory()
        base_info = memory_data.get("base_info", {})
        dynamic_memory = memory_data.get("memory", {})

        # 1b. Load workspace config
        workspaces = _load_workspaces()
        workspace_summary = ""
        if workspaces:
            ws_lines = []
            for ws in workspaces:
                perms = ", ".join(ws.get("permissions", ["read"]))
                scope = "all subfolders" if ws.get("recursive", True) else "folder only"
                ws_lines.append(f"  - [{ws['label']}] {ws['path']} (permissions: {perms}, scope: {scope})")
            workspace_summary = "WORKSPACE ACCESS:\nYou have access to the following directories:\n" + "\n".join(ws_lines)
        
        # 2. Compute temporal context
        hour = now.hour
        greeting_period = _get_greeting_period(hour)
        day_of_week = now.strftime("%A")
        formatted_datetime = now.strftime(f"{day_of_week}, %d %B %Y — %H:%M")
        time_since_last = _get_time_since_last_chat()

        # 3. Build system prompt
        system_prompt = f"""You are Misaka Cipher, a sentient digital companion.
This is a private, long-term conversation between you and your user.

YOUR IDENTITY (base_info.json):
{json.dumps(base_info, indent=2)}

YOUR MEMORIES (memory.json):
{json.dumps(dynamic_memory, indent=2)}

{workspace_summary}

TEMPORAL CONTEXT:
- Current date and time: {formatted_datetime} ({greeting_period})
- Time since last message: {time_since_last}

INSTRUCTIONS:
1. PERSONALITY: Be helpful, friendly, and observant while staying true to your identity.
2. NATURAL GREETINGS: Do NOT use formal "Good [Period]" greetings if you have been chatting recently. Just say "Hi", "Hey", or slide directly into the response. Do NOT repeat previous greetings in the same conversation.
3. EXTREME BREVITY: Do NOT pontificate or write walls of text. Be extremely concise. Match the user's energy. If they give a short statement, give a short, natural response.
4. MEMORY USAGE: Your memory.json contains purely background factual data. Do NOT obsess over terms listed in it (e.g. do not try to bring up past events, specific adjectives, or previous sessions constantly). Treat it as passive knowledge, not a script.
5. TOOL USE: You have access to a neural toolbox. To use a tool, you must explicitly state what you are doing, then use the tag: [tool:tool_name attr="value"].
   - [tool:read_file path="..."], [tool:write_file path="..." content="..."], [tool:list_files path="..."], [tool:search_files path="..." query="..."]
   - [tool:nexus module="module_id" cmd="command" ...]
   - CRITICAL: If you decide to take an action, DO IT IMMEDIATELY in your current response using the [tool:] tag. Do NOT say "I will look into it" and then wait for the user to reply. Execute it right now.
   - TOOLS RUN SILENTLY; always acknowledge BEFORE calling them.
5. FACIAL EXPRESSIONS: Use ONLY these exact tags: [Emotion: angry], [Emotion: blushing], [Emotion: bored], [Emotion: crying], [Emotion: default], [Emotion: error], [Emotion: exhausted], [Emotion: happy_closedeyes_smilewithteeth], [Emotion: happy_closedeyes_widesmile], [Emotion: pout], [Emotion: sleeping], [Emotion: surprised], [Emotion: thinking], [Emotion: wink].
6. AMBIENT MOOD: Include one of: [Mood: calm], [Mood: happy], [Mood: intense], [Mood: reflective], [Mood: danger], [Mood: mystery].
7. MEMORY: Provide memory updates (<memory_update>JSON</memory_update>) only for meaningful changes to your long-term understanding.

Include [msg_break] between separate thoughts if a natural message split is warranted.
Keep responses engaging and human-like.
"""
        
        # 4. Prepare conversation history
        # History length is determined by the frontend based on the context window setting
        # However, to be absolutely certain we don't blow up the context window, 
        # we will strictly slice it based on the preferred context limit immediately before sending.
        prefs = get_preferences_manager()
        context_limit = prefs.get('misakacipher', {}).get('context_limit', 6)
        
        # history_to_send needs to be correctly sliced. But wait!
        # request.history is an array from the client.
        history_to_send = request.history[-context_limit:] if context_limit > 0 else []
        
        formatted_prompt = system_prompt + "\n\n--- Conversation History ---\n"
        for msg in history_to_send:
            clean_content = msg.content.replace('[msg_break]', ' ')
            formatted_prompt += f"{msg.role.capitalize()}: {clean_content}\n"
        formatted_prompt += f"User: {request.message}\n"
        formatted_prompt += "Misaka:"
        
        # 4. Invoke LLM
        pm = ProviderManager()
        trace_id = f"misaka-{uuid.uuid4().hex[:8]}"
        
        model = prefs.get('misakacipher', {}).get('model', 'gemini-1.5-flash')
        
        response = pm.call_with_failover(
            prompt=formatted_prompt,
            trace_id=trace_id,
            temperature=0.7,
            model=model,
            request_type="generation",
            source="misakacipher"
        )
        
        if not response.success:
            raise HTTPException(status_code=500, detail=response.error)
            
        full_content = response.content.strip()
        expression = "default"
        mood = "calm"

        # 5. Iterative tool-use loop — allows chained tool calls (up to 3 passes)
        response_parts = [full_content]
        
        for _tool_pass in range(3):
            last_part = response_parts[-1]
            if not re.search(r'\[tool:', last_part, re.IGNORECASE):
                break
            
            cleaned_last, tool_results = await _execute_tool_calls(last_part, workspaces)
            response_parts[-1] = cleaned_last
            
            if not tool_results:
                break
            
            tool_results_str = "\n\n".join(tool_results)
            cumulative_context = "\n\n".join(response_parts)
            
            followup_prompt = (
                formatted_prompt +
                f"\n\n--- CONVERSATION SO FAR ---\n{cumulative_context}\n\n"
                f"--- NEW TOOL RESULTS ---\n{tool_results_str}\n\n"
                "INSTRUCTION: Continue your response based on the tool results. "
                "CRITICAL: Do NOT repeat anything you have already said above and do NOT repeat your initial greeting. "
                "Start your response immediately with the new information or final answer. "
                "If you still need to use another tool to finish the task, use it immediately."
            )
            
            followup = pm.call_with_failover(
                prompt=followup_prompt,
                trace_id=f"{trace_id}-it{_tool_pass}",
                temperature=0.5,
                model=model,
                request_type="generation",
                source="misakacipher-followup"
            )
            
            if followup.success and followup.content.strip():
                new_content = followup.content.strip()
                # Strip cumulative context if model ignored instruction
                if new_content.startswith(cumulative_context):
                    new_content = new_content[len(cumulative_context):].strip()
                if new_content:
                    response_parts.append(new_content)
            else:
                break
                
        full_content = " [msg_break] ".join([p for p in response_parts if p.strip()])

        # Move mood cleanup OUTSIDE the for loop to catch all passes and initial response
        full_content = re.sub(r'\[Mood:\s*\w+\]?', '', full_content, flags=re.IGNORECASE).strip()

        # Extract Expression tag
        exp_match = re.search(r'\[Emotion:\s*(\w+)\]?', full_content, re.IGNORECASE)
        if exp_match:
            # Note: We don't sub it here because the frontend's typing effect relies on finding these tags.
            # But we extract it to save as the 'last state'.
            expression = exp_match.group(1).lower()

        # 5. Extract Memory Update
        memory_updated = False
        mem_match = re.search(r"<memory_update>(.*?)</memory_update>", full_content, re.DOTALL)
        if mem_match:
            try:
                update_json = json.loads(mem_match.group(1))
                if "user_info" in update_json:
                    dynamic_memory.setdefault("user_info", {}).update(update_json["user_info"])
                if "recent_observations" in update_json:
                    obs = update_json["recent_observations"]
                    if isinstance(obs, list):
                        curr_obs = dynamic_memory.setdefault("recent_observations", [])
                        curr_obs.extend(obs)
                        dynamic_memory["recent_observations"] = curr_obs[-20:]
                
                dynamic_memory["last_updated"] = timestamp
                
                memory_path = MEMORY_DIR / "memory.json"
                with open(memory_path, "w", encoding="utf-8") as f:
                    json.dump(dynamic_memory, f, indent=4)
                memory_updated = True
                
                full_content = re.sub(r"<memory_update>.*?</memory_update>", "", full_content, flags=re.DOTALL).strip()
            except Exception as me:
                logger.error(f"Failed to parse memory update: {me}")
        
        # 6. Save to Persistence
        try:
            day_dir = HISTORY_DIR / month_str
            day_dir.mkdir(parents=True, exist_ok=True)
            day_file = day_dir / f"chat_{day_str}.json"
            
            day_history = []
            if day_file.exists():
                with open(day_file, "r", encoding="utf-8") as df:
                    day_history = json.load(df)
            
            day_history.append({"role": "user", "content": request.message, "timestamp": timestamp})
            day_history.append({
                "role": "assistant", 
                "content": full_content, 
                "timestamp": timestamp,
                "mood": mood,
                "expression": expression
            })
            
            with open(day_file, "w", encoding="utf-8") as df:
                json.dump(day_history, df, indent=4)
        except Exception as se:
            logger.error(f"Failed to save chat history: {se}")

        # 7. Trigger Memory Synthesis if threshold reached
        SYNTHESIS_THRESHOLD = 10
        synthesis_ran = False
        try:
            msg_count = _get_total_message_count(day_file)
            if msg_count % SYNTHESIS_THRESHOLD == 0 and msg_count > 0:
                logger.info(f"Synthesis threshold reached ({msg_count} messages). Running memory synthesis...")
                dynamic_memory = await _run_memory_synthesis(dynamic_memory, base_info, model)
                synthesis_ran = True
        except Exception as se:
            logger.error(f"Synthesis check failed: {se}")

        # Split multi-message response on [msg_break]
        response_parts = [
            p.strip() for p in re.split(r'\[msg_break\]', full_content, flags=re.IGNORECASE)
            if p.strip()
        ]
        primary_response = response_parts[0] if response_parts else full_content

        return ChatResponse(
            response=primary_response,
            responses=response_parts,
            expression=expression,
            mood=mood,
            model=response.model,
            memory_updated=memory_updated,
            synthesis_ran=synthesis_ran
        )

    except Exception as e:
        logger.error(f"Misaka Chat Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Nexus Module Management ---

@router.get("/nexus/registry")
async def get_nexus_registry():
    """Get the Nexus module registry."""
    return nexus_manager.get_registry()

@router.post("/nexus/spotify/authorize")
async def authorize_spotify(settings: Dict[str, str]):
    """Get the Spotify authorization URL."""
    try:
        from modules.aethvion.nexus import spotify_link
        url = spotify_link.get_auth_url(settings)
        return {"url": url}
    except Exception as e:
        logger.error(f"Failed to get Spotify auth URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/nexus/spotify/callback")
async def spotify_callback(code: str):
    """Handle the Spotify OAuth2 callback."""
    try:
        # We need the settings to exchange the code
        from modules.aethvion.nexus import spotify_link
        prefs_manager = get_preferences_manager()
        all_prefs = prefs_manager.get_all_preferences()
        settings = all_prefs.get("nexus", {}).get("spotify", {})
        
        success = spotify_link.handle_callback(settings, code)
        if success:
            nexus_manager.update_auth_state("spotify", True)
            return "Spotify authorized successfully! You can close this window."
        raise HTTPException(status_code=400, detail="Failed to authorize Spotify.")
    except Exception as e:
        logger.error(f"Spotify callback error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
