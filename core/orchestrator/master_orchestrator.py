"""
Aethvion Suite - Master Orchestrator
Autonomous coordinator for Factory, Forge, and Memory Tier
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime

import re
import json
import asyncio
from pathlib import Path
from core.tools.standard.file_ops import WORKSPACE_ROOT

from core.aether_core import AetherCore, Request, Response
from core.factory import AgentFactory, AgentSpec
from core.memory import get_episodic_memory, get_knowledge_graph
from core.memory.memory_spec import EpisodicMemory, generate_memory_id
from core.utils import get_logger, generate_trace_id, utcnow_iso

from .intent_analyzer import IntentAnalyzer, IntentAnalysis, IntentType
from core.memory.identity_manager import IdentityManager
from core.memory.history_manager import HistoryManager
from core.orchestrator.persona_manager import PersonaManager
from core.ai.call_contexts import CallSource, PERSONA_SOURCES

logger = get_logger(__name__)


@dataclass
class ActionPlan:
    """Plan for executing user request."""
    trace_id: str
    intent: IntentAnalysis
    actions: List[str]  # Sequence of actions to take
    requires_factory: bool = False
    agent_spec: Optional[AgentSpec] = None
    requires_memory: bool = False
    memory_query: Optional[str] = None
    direct_response: Optional[str] = None
    model_used: Optional[str] = None
    images: Optional[List[Dict[str, Any]]] = None


@dataclass
class ExecutionResult:
    """Result of orchestrator execution."""
    trace_id: str
    success: bool
    response: str
    actions_taken: List[str]
    agents_spawned: List[str]
    memories_queried: int
    execution_time: float
    error: Optional[str] = None
    model_id: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None
    media_paths: Optional[List[str]] = None


class MasterOrchestrator:
    """
    Master Orchestrator - Autonomous coordinator for Aethvion Suite.
    
    Analyzes user intents and autonomously decides when to:
    - Spawn specialized agents (Factory)
    - Generate missing tools (Forge)
    - Query knowledge base (Memory Tier)
    - Provide direct responses (Aether Core)
    
    Acts as a Supervisor Agent that coordinates subsystems without
    requiring explicit user menu selection.
    """
    
    def __init__(self, aether: AetherCore, factory: AgentFactory):
        """
        Initialize Master Orchestrator.
        
        Args:
            aether: AetherCore instance for AI routing
            factory: AgentFactory for spawning agents
        """
        self.aether = aether
        self.factory = factory
        self.intent_analyzer = IntentAnalyzer(aether)
        
        # Memory tier (lazy loaded)
        self.episodic_memory = get_episodic_memory()
        self.knowledge_graph = get_knowledge_graph()
        
        # Execution tracking
        self.current_trace_id: Optional[str] = None
        self.execution_history: List[ExecutionResult] = []
        self.step_callback: Optional[Callable[[Dict], None]] = None
        
        logger.info("Master Orchestrator initialized")
        
    def set_step_callback(self, callback: Callable[[Dict], None]):
        """Set callback for real-time step monitoring."""
        self.step_callback = callback
    
    async def process_message(self, user_message: str, system_prompt: Optional[str] = None, mode: str = "auto", trace_id: Optional[str] = None, model_id: Optional[str] = None, images: Optional[List[Dict[str, Any]]] = None, source: str = "unknown", security_context: str = "", allow_tools: bool = True, internet_search: bool = False, companion_id: Optional[str] = None) -> ExecutionResult:
        """
        Process user message end-to-end (Asynchronous).
        """
        start_time = datetime.now()
        if not trace_id:
            trace_id = generate_trace_id()
        self.current_trace_id = trace_id
        
        # Infer companion identity
        if not companion_id:
            if source in ["misakacipher", "axiom", "lyra"]:
                companion_id = source
            else:
                companion_id = "misakacipher"

        logger.info(f"[{trace_id}] Processing message (companion={companion_id}): {user_message[:50]}...")
        
        try:
            use_persona = (source in PERSONA_SOURCES) or (companion_id in ["axiom", "lyra", "misakacipher"])
            
            if use_persona:
                # When agents are disabled (chat_only mode), disable tool usage
                effective_allow_tools = allow_tools and (mode != "chat_only")
                
                result = await self._execute_persona_chat(
                    user_message, 
                    trace_id, 
                    model_id, 
                    images, 
                    source, 
                    system_prompt, 
                    security_context, 
                    effective_allow_tools, 
                    internet_search=internet_search,
                    companion_id=companion_id
                )
                
                result.response = IdentityManager.extract_and_update(result.response, companion_id=companion_id)
            elif source == "chat" and internet_search:
                result = await self._execute_neutral_tool_chat(
                    user_message,
                    trace_id,
                    model_id,
                    images,
                    system_prompt,
                    allow_tools=allow_tools,
                    internet_search=True
                )
            else:
                force_chat = (mode == "chat_only")
                intent = self.intent_analyzer.analyze(user_message, trace_id, force_chat=force_chat, source=source)
                plan = self.decide_action(intent, trace_id, model_id=model_id, images=images, system_prompt=system_prompt)
                result = self.execute_plan(plan)
                result.response = IdentityManager.extract_and_update(result.response, companion_id=companion_id)
            
            execution_time = (datetime.now() - start_time).total_seconds()
            result.execution_time = execution_time
            self.execution_history.append(result)
            
            # --- MEMORY STORAGE ---
            try:
                if use_persona:
                    intent_type_val = "chat"
                    intent_prompt = user_message
                    intent_domain = "General"
                else:
                    intent_type_val = intent.intent_type.value if hasattr(intent.intent_type, 'value') else str(intent.intent_type)
                    intent_prompt = intent.prompt
                    intent_domain = intent.domain or "General"
                
                summary_text = f"[{intent_type_val}] {intent_prompt}"
                if len(summary_text) > 200:
                    summary_text = summary_text[:197] + "..."
                
                memory = EpisodicMemory(
                    memory_id=generate_memory_id(),
                    trace_id=trace_id,
                    timestamp=utcnow_iso(),
                    event_type=intent_type_val,
                    domain=intent_domain,
                    summary=summary_text,
                    content=f"User: {user_message}\n\nAssistant:\n{result.response}",
                    metadata={
                        'success': result.success,
                        'execution_time': execution_time,
                        'agents_spawned': result.agents_spawned,
                        'model_id': result.model_id or model_id,
                        'companion_id': companion_id
                    }
                )
                
                self.episodic_memory.store(memory)

                # Mirror to Unified History
                if source in ["discord", "misakacipher", "axiom", "lyra"]:
                    HistoryManager.log_message(
                        role="assistant",
                        content=result.response,
                        platform=source,
                        metadata={
                            "trace_id": trace_id,
                            "model_id": result.model_id or model_id,
                            "companion_id": companion_id
                        }
                    )
            except Exception as mem_err:
                logger.error(f"[{trace_id}] Failed to store memory: {mem_err}")
            # ----------------------
            
            return result
            
        except Exception as e:
            logger.error(f"[{trace_id}] Orchestrator error: {str(e)}", exc_info=True)
            return ExecutionResult(
                trace_id=trace_id,
                success=False,
                response=f"Orchestrator error: {str(e)}",
                actions_taken=["error"],
                agents_spawned=[],
                memories_queried=0,
                execution_time=(datetime.now() - start_time).total_seconds(),
                error=str(e)
            )

    async def _execute_persona_chat(self, user_message: str, trace_id: str, model_id: Optional[str], images: Optional[List[Dict[str, Any]]], source: str, system_prompt: Optional[str] = None, security_context: str = "", allow_tools: bool = True, internet_search: bool = False, companion_id: str = "misakacipher") -> ExecutionResult:
        """Handle persona-based chat with iterative tool execution."""
        # 1. Build Persona System Prompt
        persona_system_prompt = PersonaManager.build_system_prompt(companion_id=companion_id, source=source, security_context=security_context, allow_tools=allow_tools, internet_search=internet_search)
        
        final_system_prompt = persona_system_prompt
        if system_prompt:
            final_system_prompt = f"{system_prompt}\n\n{persona_system_prompt}"
        
        # 2. Get history
        history_context = ""
        try:
            recent_msgs = HistoryManager.get_recent_history(limit=10, companion_id=companion_id)
            if recent_msgs:
                lines = []
                for m in recent_msgs:
                    role = "Assistant" if m["role"] == "assistant" else "User"
                    lines.append(f"{role}: {m['content']}")
                history_context = "\n".join(lines) + "\n\n"
        except Exception as e:
            logger.warning(f"[{trace_id}] Failed to load history for persona: {e}")

        conv_context = f"--- RECENT CONVERSATION history ---\n{history_context}User: {user_message}\nAssistant:"
        
        current_response = ""
        actions_taken = ["persona_chat"]
        media_paths = []
        tool_results_str = ""
        
        for i in range(3): # Max 3 tool iterations
            request = Request(
                prompt=conv_context if i == 0 else f"{conv_context}\n\n{current_response}\n\n--- NEW TOOL RESULTS ---\n{tool_results_str}",
                system_prompt=final_system_prompt,
                request_type="generation",
                trace_id=trace_id,
                metadata={"source": source, "companion_id": companion_id},
                model=model_id,
                images=images
            )
            
            response = self.aether.route_request(request)
            if not response.success:
                return ExecutionResult(trace_id, False, f"LLM Error: {response.error}", actions_taken, [], [], 0, 0)
            
            content = response.content.strip()
            current_response = content
            
            if allow_tools:
                cleaned_content, tool_results = await PersonaManager.execute_tools(content)
            else:
                import re
                cleaned_content = re.sub(r'\[tool:.*?\]', '', content).strip()
                tool_results = []
            
            if not tool_results:
                return ExecutionResult(
                    trace_id=trace_id,
                    success=True,
                    response=cleaned_content,
                    actions_taken=actions_taken,
                    agents_spawned=[],
                    memories_queried=0,
                    execution_time=0,
                    model_id=response.model if hasattr(response, 'model') else model_id,
                    media_paths=media_paths
                )
            
            tool_results_str = "\n".join(tool_results)
            actions_taken.append(f"tools_executed_{len(tool_results)}")
            
            if i == 0:
                conv_context = f"{conv_context}\n{cleaned_content}"
            else:
                conv_context = f"{conv_context}\n\n{current_response}\n\n--- NEW TOOL RESULTS ---\n{tool_results_str}"

        return ExecutionResult(trace_id, True, current_response, actions_taken, [], [], 0, 0, model_id=model_id, media_paths=media_paths)


    async def _execute_neutral_tool_chat(self, user_message: str, trace_id: str, model_id: Optional[str] = None, images: Optional[List[Dict[str, Any]]] = None, system_prompt: Optional[str] = None, allow_tools: bool = True, internet_search: bool = False) -> ExecutionResult:
        """Handle neutral chat — with optional pre-fetched web search context (no persona/identity).

        Architecture:
        ─────────────
        When internet_search=True, web search is executed BEFORE the LLM call and
        the results are injected directly into the prompt context.  This is more
        reliable than asking the model to emit [tool:web_search ...] tags because
        some models return an empty response when their sole output is a tool tag.

        Nexus / custom [tool:...] tags are still supported for any other
        capabilities registered in the Nexus module registry.
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        time_context = f"Current date/time: {now_str}"
        neutral_base = (
            "Answer the user's question directly and concisely. "
            "Do not introduce yourself or mention any AI product name."
        )

        # ── Step 1: Pre-execute web search (if enabled) ───────────────────────
        pre_search_context = ""
        if internet_search and allow_tools:
            try:
                # Extract the actual user query from a potentially history-wrapped message
                search_query = user_message
                if "\nCurrent Message:\n" in user_message:
                    search_query = user_message.split("\nCurrent Message:\n")[-1].strip()
                # Clamp to a sensible search query length
                search_query = search_query[:300]

                logger.info(f"[{trace_id}] Pre-executing web search for: {search_query[:80]!r}")
                if self.step_callback:
                    self.step_callback({
                        "type": "agent_step",
                        "title": "Internet Search",
                        "content": "Searching the web for real-time information...",
                        "trace_id": trace_id,
                        "status": "running",
                    })

                search_result = await asyncio.to_thread(
                    PersonaManager.execute_tool_sync, "web_search", {"query": search_query}
                )

                if search_result and "[web_search ERROR]" not in search_result:
                    pre_search_context = (
                        f"\n\n[LIVE WEB SEARCH RESULTS — retrieved just now]\n"
                        f"{search_result}\n"
                        f"[END SEARCH RESULTS]\n"
                    )
                    logger.info(f"[{trace_id}] Web search complete ({len(search_result)} chars)")
                    if self.step_callback:
                        self.step_callback({
                            "type": "agent_step",
                            "title": "Search Complete",
                            "content": "Retrieved real-time search results.",
                            "trace_id": trace_id,
                            "status": "completed",
                        })
                else:
                    logger.warning(f"[{trace_id}] Web search returned no usable results: {str(search_result)[:120]}")
            except Exception as _search_err:
                logger.warning(f"[{trace_id}] Web search pre-execution failed: {_search_err}")

        # ── Step 2: Build system prompt ────────────────────────────────────────
        aether_caps = PersonaManager._build_bridges_capabilities() if allow_tools else ""

        prompt_parts = [neutral_base, time_context]

        if aether_caps:
            prompt_parts.append(f"BRIDGE CAPABILITIES (use [tool:bridge ...] syntax):\n{aether_caps}")

        if internet_search:
            if pre_search_context:
                prompt_parts.append(
                    "SEARCH CONTEXT: Live web search results are included in the user message context. "
                    "Use them to answer questions about current events, dates, or real-time facts. "
                    "Cite sources where helpful."
                )
            else:
                # Search failed — tell the model it can still try via tag syntax
                prompt_parts.append(
                    "SEARCH: If you need real-time information use: "
                    "[tool:web_search query=\"<your query>\"]"
                )

        base_instructions = "\n".join(prompt_parts)

        if system_prompt:
            final_system_prompt = f"{system_prompt}\n\n{base_instructions}"
        else:
            final_system_prompt = base_instructions

        # ── Step 3: Build conversation prompt (search results injected inline) ─
        full_history = f"{user_message}{pre_search_context}\n\nAssistant:"

        # ── Step 4: LLM call loop (handles any remaining [tool:...] tags) ─────
        accumulated_text = ""
        actions_taken = ["neutral_tool_chat"]
        if pre_search_context:
            actions_taken.append("web_search_pre_executed")
        media_paths = []

        for i in range(3):  # Max 3 iterations for any follow-up nexus tool calls
            logger.info(f"[{trace_id}] Neutral chat LLM iteration {i}")

            request = Request(
                prompt=full_history,
                system_prompt=final_system_prompt,
                request_type="generation",
                trace_id=trace_id,
                metadata={"source": CallSource.CHAT},
                model=model_id,
                images=images,
            )

            response = self.aether.route_request(request)
            if not response.success:
                return ExecutionResult(trace_id, False, f"LLM Error: {response.error}", actions_taken, [], [], 0, 0)

            content = response.content.strip()

            if not content:
                finish_reason = (response.metadata or {}).get("finish_reason", "unknown")
                logger.warning(
                    f"[{trace_id}] Empty response from model on iteration {i} "
                    f"(finish_reason={finish_reason!r}). "
                    f"Provider: {getattr(response, 'provider', 'unknown')}"
                )
                break

            # Execute any [tool:...] tags the model may have emitted
            cleaned_content = content
            tool_results = []

            if allow_tools and "[tool:" in content:
                if self.step_callback:
                    self.step_callback({
                        "type": "agent_step",
                        "title": "Executing Tools",
                        "content": "AI is using tools to fulfil your request...",
                        "trace_id": trace_id,
                        "status": "running",
                    })

                cleaned_content, tool_results = await PersonaManager.execute_tools(content)

                if tool_results and self.step_callback:
                    self.step_callback({
                        "type": "agent_step",
                        "title": "Tools Complete",
                        "content": f"Executed {len(tool_results)} tool(s).",
                        "trace_id": trace_id,
                        "status": "completed",
                    })

            # Accumulate — avoid re-adding text that is already present
            if cleaned_content:
                if not accumulated_text:
                    accumulated_text = cleaned_content
                elif cleaned_content not in accumulated_text:
                    accumulated_text = (
                        cleaned_content
                        if accumulated_text in cleaned_content
                        else accumulated_text + "\n" + cleaned_content
                    )

            if not tool_results:
                break

            # Prepare next iteration with tool results
            tool_results_str = "\n".join(tool_results)
            actions_taken.append(f"tools_executed_{len(tool_results)}")
            full_history += f" {content}\n\n--- TOOL RESULTS ---\n{tool_results_str}\n\nAssistant:"

        # ── Step 5: Return ─────────────────────────────────────────────────────
        final_text = accumulated_text.strip()
        if not final_text:
            if len(actions_taken) > 1:
                final_text = "Retrieved results but the model did not produce a summary. Please try again."
            else:
                final_text = (
                    "The AI returned an empty response. "
                    "This can happen if the prompt was flagged by a safety filter."
                )

        return ExecutionResult(
            trace_id=trace_id,
            success=True,
            response=final_text,
            actions_taken=actions_taken,
            agents_spawned=[],
            memories_queried=0,
            execution_time=0,
            model_id=model_id,
            media_paths=media_paths,
        )

    def decide_action(self, intent: IntentAnalysis, trace_id: str, model_id: Optional[str] = None, images: Optional[List[Dict[str, Any]]] = None, system_prompt: Optional[str] = None) -> ActionPlan:
        """
        Decide what actions to take based on intent.
        
        Args:
            intent: Analyzed user intent
            trace_id: Trace ID for this execution
            model_id: Optional specific model to use
            system_prompt: Optional model-level instructions
            
        Returns:
            ActionPlan with sequence of actions
        """
        actions = []
        plan = ActionPlan(
            trace_id=trace_id,
            intent=intent,
            actions=actions,
            images=images
        )
        
        # Route based on intent type
        if intent.intent_type == IntentType.CHAT:
            actions.append("direct_response")
            resp_obj = self._generate_chat_response(intent, system_prompt=system_prompt, model_id=model_id, trace_id=trace_id, images=images)
            plan.direct_response = resp_obj.content
            if resp_obj.metadata and 'model' in resp_obj.metadata:
                plan.model_used = resp_obj.metadata['model']
        
        elif intent.intent_type == IntentType.SYSTEM:
            actions.append("system_status")
            plan.direct_response = self._get_system_status()
        
        elif intent.intent_type == IntentType.QUERY:
            actions.append("query_memory")
            plan.requires_memory = True
            plan.memory_query = intent.prompt
        
        elif intent.intent_type == IntentType.CREATE:
            # CREATE intent is now handled as an agent spawn request
            actions.append("spawn_agent")
            plan.requires_factory = True
            plan.agent_spec = self._build_agent_spec(intent, images)
        
        elif intent.intent_type in [IntentType.ANALYZE, IntentType.EXECUTE]:
            # Always spawn agent for these intents in the new curated tool system
            actions.append("spawn_agent")
            plan.requires_factory = True
            plan.agent_spec = self._build_agent_spec(intent, images=images)
            # Pass model preference to agent spec/context if possible?
            # For now, agents depend on factory/provider manager config which we split.
            # If model_id is specific, we might want to override it here.
            # But AgentSpec doesn't have a clean slot. We'll rely on global "Agent" priority for now.
            # Note: system_prompt currently does not propagate to spawned agents, 
            # they have their own internal context management.
        
        else:
            # Unknown intent - try to have a conversation
            actions.append("direct_response")
            resp_obj = self._generate_chat_response(intent, system_prompt=system_prompt, model_id=model_id, trace_id=trace_id, images=images)
            plan.direct_response = resp_obj.content
            if resp_obj.metadata and 'model' in resp_obj.metadata:
                plan.model_used = resp_obj.metadata['model']
        
        return plan
    
    def execute_plan(self, plan: ActionPlan) -> ExecutionResult:
        """
        Execute an action plan.
        
        Args:
            plan: ActionPlan to execute
            
        Returns:
            ExecutionResult with outcomes
        """
        actions_taken = []
        agents_spawned = []
        memories_queried = 0
        response_parts = []
        
        try:
            # Execute actions in sequence
            for action in plan.actions:
                
                
                if action == "spawn_agent":
                    if self.step_callback:
                        self.step_callback({
                            "type": "agent_step",
                            "title": "Spawning Agent",
                            "content": f"Deploying agent **{plan.agent_spec.name}** to execute task...",
                            "trace_id": plan.trace_id,
                            "status": "running"
                        })
                    
                    agent_result = self.call_factory(plan.agent_spec, plan.trace_id)
                    success = agent_result.get('success', False)
                    output = agent_result.get('output', '')
                    
                    if success:
                        # 1. Check for File Creation
                        potential_files = re.findall(r'[\w\-\.]+\.[a-zA-Z]{2,4}', output)
                        verified_files = set()
                        
                        for fname in potential_files:
                            found = list(WORKSPACE_ROOT.rglob(fname))
                            for path in found:
                                if path.is_file():
                                    verified_files.add(path)
                        
                        if verified_files:
                            links_msg = "\n\n**Verified Output Files:**\n"
                            for vf in sorted(list(verified_files)):
                                relative_path = vf.relative_to(WORKSPACE_ROOT)
                                try:
                                    domain = relative_path.parts[0]
                                    if relative_path.name == domain:
                                        filename = relative_path.name
                                        links_msg += f"- [{filename}](/api/workspace/files/{filename})\n"
                                    else:
                                        filename = relative_path.name
                                        links_msg += f"- [{filename}](/api/workspace/files/{domain}/{filename})\n"
                                except IndexError:
                                    links_msg += f"- {filename}\n"
                            
                            agent_result['output'] = output + links_msg
                    
                    agents_spawned.append(agent_result.get('agent_name', 'unknown'))
                    
                    # Format response based on success/failure
                    if success:
                        response_parts.append(agent_result.get('output', 'No output'))
                    else:
                        error_msg = agent_result.get('error', 'Unknown error')
                        
                        # Extract file and line number from traceback if available
                        traceback_match = re.search(r'File "([^"]+)", line (\d+)', output)
                        location = ""
                        if traceback_match:
                            file_path = traceback_match.group(1)
                            line_num = traceback_match.group(2)
                            file_name = file_path.split('\\')[-1] if '\\' in file_path else file_path.split('/')[-1]
                            location = f" in `{file_name}` line {line_num}"
                        
                        error_type_match = re.search(r'(\w+Error): (.+?)(?:\n|$)', output)
                        error_detail = ""
                        if error_type_match:
                            error_detail = f": {error_type_match.group(1)} - {error_type_match.group(2)}"
                        
                        response_parts.append(
                            f"\n**Status:** ❌ Unsuccessful\n"
                            f"**Error{location}**{error_detail}\n\n"
                            f"<details>\n<summary>View full error details</summary>\n\n"
                            f"```\n{output}\n```\n</details>"
                        )
                    
                    actions_taken.append("spawn_agent")
                    
                    if self.step_callback:
                        status = "completed" if success else "failed"
                        content = f"Agent **{agent_result.get('agent_name')}** finished execution."
                        if not success:
                             content += f" Error: {agent_result.get('error', 'Unknown')}"

                        self.step_callback({
                            "type": "agent_step",
                            "title": "Agent Execution",
                            "agent_name": agent_result.get('agent_name'),
                            "content": content,
                            "trace_id": plan.trace_id,
                            "status": status
                        })

                
                elif action == "query_memory":
                    memory_results = self.query_memory(plan.memory_query, plan.trace_id)
                    memories_queried = len(memory_results)
                    results_text = self._format_memory_results(memory_results)
                    response_parts.append(results_text)
                    actions_taken.append("query_memory")
                    
                    if self.step_callback:
                        self.step_callback({
                            "type": "agent_step",
                            "title": "Memory Search",
                            "content": f"Searched memory for: *{plan.memory_query}*. Found {len(memory_results)} results.",
                            "trace_id": plan.trace_id,
                            "status": "completed"
                        })
                
                elif action == "system_status":
                    response_parts.append(plan.direct_response)
                    actions_taken.append("system_status")
                
                elif action == "direct_response":
                    response_parts.append(plan.direct_response)
                    actions_taken.append("direct_response")
            
            # Combine responses
            final_response = "\n\n".join(response_parts)
            
            # Additional check for empty or whitespace-only response
            if not final_response.strip():
                if agents_spawned:
                     final_response = f"**Agent Execution Completed**\n\nAgent `{agents_spawned[-1]}` completed the task but provided no text output. Please check the workspace for any generated files."
                else:
                     final_response = "Task execution completed, but no output was generated."
            
            return ExecutionResult(
                trace_id=plan.trace_id,
                success=True,
                response=final_response,
                actions_taken=actions_taken,
                agents_spawned=agents_spawned,
                memories_queried=memories_queried,
                execution_time=0,  # Filled by process_message
                model_id=plan.model_used
            )
            
        except Exception as e:
            logger.error(f"[{plan.trace_id}] Plan execution failed: {str(e)}", exc_info=True)
            return ExecutionResult(
                trace_id=plan.trace_id,
                success=False,
                response=f"Execution failed: {str(e)}",
                actions_taken=actions_taken,
                agents_spawned=agents_spawned,
                memories_queried=memories_queried,
                execution_time=0,
                error=str(e)
            )
    
    def call_factory(self, spec: AgentSpec, trace_id: str) -> Dict[str, Any]:
        """
        Spawn an agent via Factory.
        
        Args:
            spec: Agent specification
            trace_id: Trace ID
            
        Returns:
            Dictionary with agent execution results
        """
        logger.info(f"[{trace_id}] Spawning agent: {spec.name}")
        
        # Spawn agent
        agent = self.factory.spawn(spec)
        
        try:
            # Execute agent
            result = agent.execute()
            
            return {
                'agent_name': agent.name,
                'trace_id': agent.trace_id,
                'output': result.content,
                'success': result.success,
                'duration': result.duration_seconds
            }
        finally:
            # Unregister agent to clean up resources
            if hasattr(self.factory, 'registry'):
                self.factory.registry.unregister(agent.trace_id)
    
    
    def query_memory(self, query: str, trace_id: str, domain: str = None) -> List[Dict]:
        """
        Query episodic memory.
        
        Args:
            query: Search query
            trace_id: Trace ID
            domain: Optional domain filter
            
        Returns:
            List of memory results
        """
        logger.info(f"[{trace_id}] Querying memory: {query[:50]}...")
        
        # Search episodic memory
        results = self.episodic_memory.search(query, k=5, domain=domain)
        
        return [
            {
                'memory_id': m.memory_id,
                'summary': m.summary,
                'trace_id': m.trace_id,
                'timestamp': m.timestamp,
                'domain': m.domain,
                'event_type': m.event_type
            }
            for m in results
        ]
    
    def _check_tool_exists(self, tool_name: str) -> bool:
        """Check if a tool exists in the registry."""
        tools = self.knowledge_graph.get_tools_by_domain(None)  # All tools
        return any(t == tool_name for t in tools)
    
    def _build_agent_spec(self, intent: IntentAnalysis, images: Optional[List[Dict[str, Any]]] = None) -> AgentSpec:
        """Build AgentSpec from intent."""
        return AgentSpec(
            domain=intent.domain or "General",
            action=intent.action or "Execute",
            object=intent.object or "Task",
            context={
                'prompt': intent.prompt,
                'parameters': intent.parameters
            },
            description=f"{intent.action} {intent.object}" if intent.action and intent.object else "Execute task",
            temperature=0.7,
            images=images
        )
    
    def _generate_chat_response(self, intent: IntentAnalysis, system_prompt: Optional[str] = None, model_id: Optional[str] = None, trace_id: Optional[str] = None, images: Optional[List[Dict[str, Any]]] = None) -> Response:
        """Generate direct chat response via Aether Core."""
        request = Request(
            prompt=intent.prompt,
            system_prompt=system_prompt,
            request_type="generation",
            temperature=0.7,
            model=model_id,
            trace_id=trace_id,  # propagate so usage log matches task.id
            images=images
        )
        
        response = self.aether.route_request(request)
        
        if response.success:
            return response
        else:
            # Create a localized response with error message
            logger.error(f"Chat generation failed: {response.error}")
            return Response(
                content=f"I encountered an error: {response.error}",
                trace_id=response.trace_id,
                provider=response.provider or "none",
                success=False,
                error=response.error,
                metadata={}
            )
    
    def _get_system_status(self) -> str:
        """Get system status summary."""
        status = self.aether.get_status()
        
        # Format status
        providers_healthy = sum(1 for p in status['providers']['providers'].values() if p['is_healthy'])
        total_providers = len(status['providers']['providers'])
        
        return f"""**System Status**

**Aether Core**: {'✓ Operational' if status['initialized'] else '✗ Not initialized'}
**Active Traces**: {status['active_traces']}
**Firewall**: {'ACTIVE' if status['firewall'].get('enabled') else 'DISABLED'}
**Providers**: {providers_healthy}/{total_providers} healthy

**The Factory**: {len(self.factory.registry.get_all_agents())} agents (all time)
**Memory Tier**: {self.episodic_memory.collection.count() if hasattr(self.episodic_memory, 'collection') else 0} episodic memories

System operational and ready."""
    
    def _format_memory_results(self, results: List[Dict]) -> str:
        """Format memory search results."""
        if not results:
            return "No memories found matching your query."
        
        formatted = [f"**Found {len(results)} memories:**\n"]
        
        for i, mem in enumerate(results, 1):
            formatted.append(
                f"{i}. **{mem['summary']}**\n"
                f"   Domain: {mem['domain']} | Event: {mem['event_type']}\n"
                f"   Trace ID: {mem['trace_id']}\n"
            )
        
        return "\n".join(formatted)
