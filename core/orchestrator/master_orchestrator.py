"""
Misaka Cipher - Master Orchestrator
Autonomous coordinator for Factory, Forge, and Memory Tier
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime

import re
import json
from pathlib import Path
from tools.standard.file_ops import WORKSPACE_ROOT

from core.nexus_core import NexusCore, Request, Response
from core.factory import AgentFactory, AgentSpec
from core.forge import ToolForge
from core.memory import get_episodic_memory, get_knowledge_graph
from core.memory.memory_spec import EpisodicMemory, generate_memory_id
from core.utils import get_logger, generate_trace_id

from .intent_analyzer import IntentAnalyzer, IntentAnalysis, IntentType
from core.memory.identity_manager import IdentityManager
from core.orchestrator.persona_manager import PersonaManager

logger = get_logger(__name__)


@dataclass
class ActionPlan:
    """Plan for executing user request."""
    trace_id: str
    intent: IntentAnalysis
    actions: List[str]  # Sequence of actions to take
    requires_forge: bool = False
    forge_description: Optional[str] = None
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
    tools_forged: List[str]
    agents_spawned: List[str]
    memories_queried: int
    execution_time: float
    error: Optional[str] = None
    model_id: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None
    media_paths: Optional[List[str]] = None


class MasterOrchestrator:
    """
    Master Orchestrator - Autonomous coordinator for Misaka Cipher.
    
    Analyzes user intents and autonomously decides when to:
    - Spawn specialized agents (Factory)
    - Generate missing tools (Forge)
    - Query knowledge base (Memory Tier)
    - Provide direct responses (Nexus Core)
    
    Acts as a Supervisor Agent that coordinates subsystems without
    requiring explicit user menu selection.
    """
    
    def __init__(self, nexus: NexusCore, factory: AgentFactory, forge: ToolForge):
        """
        Initialize Master Orchestrator.
        
        Args:
            nexus: NexusCore instance for AI routing
            factory: AgentFactory for spawning agents
            forge: ToolForge for generating tools
        """
        self.nexus = nexus
        self.factory = factory
        self.forge = forge
        self.intent_analyzer = IntentAnalyzer(nexus)
        
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
    
    def process_message(self, user_message: str, mode: str = "auto", trace_id: Optional[str] = None, model_id: Optional[str] = None, images: Optional[List[Dict[str, Any]]] = None, source: str = "unknown", security_context: str = "", allow_tools: bool = True) -> ExecutionResult:
        """
        Process user message end-to-end.
        
        Args:
            user_message: User's input message
            mode: Execution mode ("auto" or "chat_only")
            trace_id: Optional trace ID (if provided by caller)
            model_id: Optional specific model ID to force
            images: Optional list of attached images
            source: Client source (dashboard, discord, etc)
            security_context: Special security instructions appended to system prompt
            allow_tools: Whether to allow tool usage and provide tool syntax to the model
            
        Returns:
            ExecutionResult with complete execution details
        """
        start_time = datetime.now()
        if not trace_id:
            trace_id = generate_trace_id()
        self.current_trace_id = trace_id
        
        logger.info(f"[{trace_id}] Processing message: {user_message[:50]}...")
        if model_id:
            logger.info(f"[{trace_id}] Force Model: {model_id}")

        if self.step_callback:
             self.step_callback({
                 "type": "agent_step",
                 "title": "Processing Message",
                 "content": f"Received request: {user_message[:100]}...",
                 "trace_id": trace_id,
                 "status": "running"
             })
        
        try:
            # IDENTIFY PERSONA SOURCE (usually everything but specialized tool-only requests)
            use_persona = (source in ["dashboard", "discord", "misakacipher"])
            
            if use_persona:
                logger.info(f"[{trace_id}] Routing directly to PersonaManager (source={source})")
                import asyncio
                try:
                    result = asyncio.run(self._execute_persona_chat(user_message, trace_id, model_id, images, source, security_context, allow_tools))
                except RuntimeError:
                    # If this is called from a thread that already has an event loop (shouldn't happen with run_in_executor)
                    loop = asyncio.get_event_loop()
                    result = loop.run_until_complete(self._execute_persona_chat(user_message, trace_id, model_id, images, source, security_context, allow_tools))

                
                # PersonaManager handles memory updates inside the loop or we do it here
                result.response = IdentityManager.extract_and_update(result.response)
            else:
                # Step 1: Analyze intent
                force_chat = (mode == "chat_only")
                intent = self.intent_analyzer.analyze(user_message, trace_id, force_chat=force_chat, source=source)
                logger.info(f"[{trace_id}] Intent: {intent.intent_type.value} (confidence: {intent.confidence:.2f})")

                # Step 2: Create action plan for specialized tasks
                plan = self.decide_action(intent, trace_id, model_id=model_id, images=images)
                logger.info(f"[{trace_id}] Action plan: {', '.join(plan.actions)}")
                
                # Step 3: Execute plan
                result = self.execute_plan(plan)
                
                # Extract and update memory tags (already generic)
                result.response = IdentityManager.extract_and_update(result.response)
            
            # Calculate execution time
            execution_time = (datetime.now() - start_time).total_seconds()
            result.execution_time = execution_time
            
            # Store result
            self.execution_history.append(result)
            
            # --- MEMORY STORAGE ---
            try:
                logger.info(f"[{trace_id}] Starting memory creation...")
                
                if use_persona:
                    intent_type_val = "chat"
                    intent_prompt = user_message
                    intent_domain = "General"
                else:
                    intent_type_val = intent.intent_type.value if hasattr(intent.intent_type, 'value') else str(intent.intent_type)
                    intent_prompt = intent.prompt
                    intent_domain = intent.domain or "General"
                
                # Default summary
                summary_text = f"[{intent_type_val}] {intent_prompt}"
                if len(summary_text) > 200:
                    summary_text = summary_text[:197] + "..."
                
                # Debug logging inputs
                logger.info(f"[{trace_id}] Intent Type: {intent_type_val}")
                logger.info(f"[{trace_id}] Domain: {intent_domain}")
                
                # Create episodic memory
                memory = EpisodicMemory(
                    memory_id=generate_memory_id(),
                    trace_id=trace_id,
                    timestamp=datetime.now().isoformat(),
                    event_type=intent_type_val,
                    domain=intent_domain,
                    summary=summary_text,
                    content=f"User: {user_message}\n\nAssistant:\n{result.response}",
                    metadata={
                        'success': result.success,
                        'execution_time': execution_time,
                        'tools_forged': result.tools_forged,
                        'agents_spawned': result.agents_spawned,
                        'model_id': result.model_id or model_id
                    }
                )
                
                # Store in vector DB
                logger.info(f"[{trace_id}] Attempting to store memory: {memory.memory_id}")
                success = self.episodic_memory.store(memory)
                if success:
                    logger.info(f"[{trace_id}] SUCCESSFULLY stored episodic memory: {memory.memory_id}")
                else:
                    logger.error(f"[{trace_id}] EpisodicMemoryStore.store returned False")

                # --- Identity & Dynamic Memory ---
                result.response = IdentityManager.extract_and_update(result.response)
                
            except Exception as mem_err:
                logger.error(f"[{trace_id}] Failed to store memory: {mem_err}")
                import traceback
                logger.error(traceback.format_exc())
            # ----------------------
            
            logger.info(f"[{trace_id}] Execution completed in {execution_time:.2f}s")
            return result
            
        except Exception as e:
            logger.error(f"[{trace_id}] Orchestrator error: {str(e)}", exc_info=True)
            
            execution_time = (datetime.now() - start_time).total_seconds()
            return ExecutionResult(
                trace_id=trace_id,
                success=False,
                response=f"Orchestrator error: {str(e)}",
                actions_taken=["error"],
                tools_forged=[],
                agents_spawned=[],
                memories_queried=0,
                execution_time=execution_time,
                error=str(e)
            )

    async def _execute_persona_chat(self, user_message: str, trace_id: str, model_id: Optional[str], images: Optional[List[Dict[str, Any]]], source: str, security_context: str = "", allow_tools: bool = True) -> ExecutionResult:
        """Handle persona-based chat with iterative tool execution."""
        # 1. Build System Prompt
        system_prompt = PersonaManager.build_system_prompt(source=source, security_context=security_context, allow_tools=allow_tools)
        
        # 2. Get history from HistoryManager for the prompt
        history_context = ""
        try:
            # We fetch last 10 messages for context
            recent_msgs = HistoryManager.get_recent_history(limit=10)
            if recent_msgs:
                lines = []
                for m in recent_msgs:
                    role = "Misaka" if m["role"] == "assistant" else "User"
                    lines.append(f"{role}: {m['content']}")
                history_context = "\n".join(lines) + "\n\n"
        except Exception as e:
            logger.warning(f"[{trace_id}] Failed to load history for persona: {e}")

        # Combine for initial LLM call
        full_prompt = f"{system_prompt}\n\n--- RECENT CONVERSATION history ---\n{history_context}User: {user_message}\nMisaka:"
        
        current_response = ""
        actions_taken = ["persona_chat"]
        media_paths = []
        
        for i in range(3): # Max 3 tool iterations
            request = Request(
                prompt=full_prompt if i == 0 else f"{full_prompt}\n\n{current_response}\n\n--- NEW TOOL RESULTS ---\n{tool_results_str}",
                request_type="generation",
                trace_id=trace_id,
                metadata={"source": source},
                model=model_id,
                images=images
            )
            
            response = self.nexus.route_request(request)
            if not response.success:
                return ExecutionResult(trace_id, False, f"LLM Error: {response.error}", actions_taken, [], [], 0, 0)
            
            content = response.content.strip()
            current_response = content
            
            # Execute tools only if allowed
            if allow_tools:
                cleaned_content, tool_results = await PersonaManager.execute_tools(content)
                
                # Extract media paths from tool results (like screenshots)
                for res in tool_results:
                    if "Saved to: " in res:
                        try:
                            path_line = [line for line in res.splitlines() if "Saved to: " in line][0]
                            media_path = path_line.replace("Saved to: ", "").strip()
                            media_paths.append(media_path)
                        except Exception as e:
                            logger.error(f"Failed to extract media path: {e}")
            else:
                # If tools are not allowed, strip any hallucinated tags but do not execute them
                import re
                cleaned_content = re.sub(r'\[tool:.*?\]', '', content).strip()
                tool_results = []

            
            if not tool_results:
                # No more tools, finish
                return ExecutionResult(
                    trace_id=trace_id,
                    success=True,
                    response=cleaned_content,
                    actions_taken=actions_taken,
                    tools_forged=[],
                    agents_spawned=[],
                    memories_queried=0,
                    execution_time=0,
                    media_paths=media_paths
                )
            
            # Found tools, prepare for next iteration
            tool_results_str = "\n".join(tool_results)
            actions_taken.append(f"tools_executed_{len(tool_results)}")
            
            # Update prompt for followup (we append the conversation so far)
            if i == 0:
                full_prompt = f"{full_prompt}\n{cleaned_content}"
            else:
                full_prompt = f"{full_prompt}\n\n{current_response}\n\n--- NEW TOOL RESULTS ---\n{tool_results_str}"

        return ExecutionResult(trace_id, True, current_response, actions_taken, [], [], 0, 0, media_paths=media_paths)

    def decide_action(self, intent: IntentAnalysis, trace_id: str, model_id: Optional[str] = None, images: Optional[List[Dict[str, Any]]] = None) -> ActionPlan:
        """
        Decide what actions to take based on intent.
        
        Args:
            intent: Analyzed user intent
            trace_id: Trace ID for this execution
            model_id: Optional specific model to use
            
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
            resp_obj = self._generate_chat_response(intent, model_id=model_id, trace_id=trace_id, images=images)
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
            actions.append("forge_tool")
            plan.requires_forge = True
            plan.forge_description = intent.prompt
        
        elif intent.intent_type in [IntentType.ANALYZE, IntentType.EXECUTE]:
            # Check if tool exists
            if intent.requires_tool and intent.tool_name:
                tool_exists = self._check_tool_exists(intent.tool_name)
                if not tool_exists:
                    actions.append("forge_tool")
                    plan.requires_forge = True
                    plan.forge_description = f"Create {intent.tool_name} for {intent.prompt}"
            
            # Spawn agent
            actions.append("spawn_agent")
            plan.requires_factory = True
            plan.agent_spec = self._build_agent_spec(intent, images=images)
            # Pass model preference to agent spec/context if possible?
            # For now, agents depend on factory/provider manager config which we split.
            # If model_id is specific, we might want to override it here.
            # But AgentSpec doesn't have a clean slot. We'll rely on global "Agent" priority for now.
        
        else:
            # Unknown intent - try to have a conversation
            actions.append("direct_response")
            resp_obj = self._generate_chat_response(intent, model_id=model_id, trace_id=trace_id, images=images)
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
        tools_forged = []
        agents_spawned = []
        memories_queried = 0
        response_parts = []
        
        try:
            # Execute actions in sequence
            for action in plan.actions:
                if action == "forge_tool":
                    if self.step_callback:
                        self.step_callback({
                            "type": "agent_step",
                            "title": "Forging Tool",
                            "content": f"Forging tool based on description: *{plan.forge_description}*",
                            "trace_id": plan.trace_id,
                            "status": "running"
                        })
                        
                    tool_result = self.call_forge(plan.forge_description, plan.trace_id)
                    tools_forged.append(tool_result.get('tool_name', 'unknown'))
                    # REMOVED: response_parts.append(f"✓ Forged tool: {tool_result.get('tool_name')}")
                    actions_taken.append("forge_tool")
                    
                    if self.step_callback:
                        status = "completed" if tool_result.get('success') else "failed"
                        content = f"Successfully created tool: **{tool_result.get('tool_name')}**" if tool_result.get('success') else "Failed to forge tool."
                        
                        self.step_callback({
                            "type": "agent_step",
                            "title": "Tool Forged",
                            "content": content,
                            "trace_id": plan.trace_id,
                            "status": status
                        })
                
                
                elif action == "spawn_agent":
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
                elif tools_forged:
                     final_response = f"**Tool Forge Completed**\n\nTool `{tools_forged[-1]}` was successfully created."
                else:
                     final_response = "Task execution completed, but no output was generated."
            
            return ExecutionResult(
                trace_id=plan.trace_id,
                success=True,
                response=final_response,
                actions_taken=actions_taken,
                tools_forged=tools_forged,
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
                tools_forged=tools_forged,
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
    
    def call_forge(self, description: str, trace_id: str) -> Dict[str, Any]:
        """
        Generate a tool via Forge.
        
        Args:
            description: Tool description
            trace_id: Trace ID
            
        Returns:
            Dictionary with tool generation results
        """
        logger.info(f"[{trace_id}] Forging tool from description: {description[:50]}...")
        
        # Generate tool
        result = self.forge.generate_tool(description)
        
        return {
            'tool_name': result['name'],
            'domain': result['domain'],
            'file_path': result['file_path'],
            'trace_id': result.get('trace_id'),
            'success': result.get('validation_status') == 'passed'
        }
    
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
    
    def _generate_chat_response(self, intent: IntentAnalysis, model_id: Optional[str] = None, trace_id: Optional[str] = None, images: Optional[List[Dict[str, Any]]] = None) -> Response:
        """Generate direct chat response via Nexus Core."""
        request = Request(
            prompt=intent.prompt,
            request_type="generation",
            temperature=0.7,
            model=model_id,
            trace_id=trace_id,  # propagate so usage log matches task.id
            images=images
        )
        
        response = self.nexus.route_request(request)
        
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
        status = self.nexus.get_status()
        
        # Format status
        providers_healthy = sum(1 for p in status['providers']['providers'].values() if p['is_healthy'])
        total_providers = len(status['providers']['providers'])
        
        return f"""**System Status**

**Nexus Core**: {'✓ Operational' if status['initialized'] else '✗ Not initialized'}
**Active Traces**: {status['active_traces']}
**Firewall**: {'ACTIVE' if status['firewall'].get('enabled') else 'DISABLED'}
**Providers**: {providers_healthy}/{total_providers} healthy

**The Factory**: {len(self.factory.registry.get_all_agents())} agents (all time)
**The Forge**: {len(self.forge.registry.list_tools())} tools registered
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
