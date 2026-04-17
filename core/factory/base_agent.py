"""
Misaka Cipher - Base Agent
Abstract base class for all agents
"""

from abc import ABC, abstractmethod
from typing import Optional
import time

from .agent_spec import AgentSpec
from .agent_result import AgentResult
from core.nexus_core import NexusCore, Request
from core.utils import get_logger, get_trace_manager, utcnow_iso


class BaseAgent(ABC):
    """
    Abstract base class for all Misaka Cipher agents.
    
    All agents must:
    - Follow Aethvion naming: [Domain]_[Action]_[Object]
    - Route all requests through Nexus Core
    - Execute statelessly (no persistent state between runs)
    - Clean up resources after execution
    """
    
    def __init__(self, spec: AgentSpec, nexus: NexusCore, trace_id: str):
        """
        Initialize agent.
        
        Args:
            spec: Agent specification
            nexus: NexusCore instance for routing requests
            trace_id: Unique Trace_ID for this agent
        """
        self.spec = spec
        self.nexus = nexus
        self.trace_id = trace_id
        self.name = spec.name
        
        # Execution state
        self.started_at = None
        self.completed_at = None
        self.iterations_count = 0
        
        # Logger
        self.logger = get_logger(f"factory.{self.name}")
        
        # Load memory context
        self.context = self._load_memory_context()
        
        self.logger.info(f"[{self.trace_id}] Agent initialized: {self.name}")
        if self.context.get('available_tools'):
            self.logger.info(
                f"[{self.trace_id}] Loaded context: "
                f"{len(self.context['available_tools'])} tools available in {spec.domain}"
            )
    
    def _load_memory_context(self) -> dict:
        """
        Load relevant context from Memory Tier.
        
        Queries:
        - Available tools in agent's domain (Knowledge Graph)
        - Recent domain activity (Episodic Memory)
        - Workspace manager for output file organization
        
        Returns:
            Context dictionary
        """
        context = {
            'available_tools': [],
            'recent_activity': [],
            'workspace_manager': None,
            'output_path': None
        }
        
        try:
            # Import here to avoid circular dependencies
            from core.memory import get_knowledge_graph, get_episodic_memory
            from core.workspace import get_workspace_manager
            
            # Get workspace manager
            workspace_manager = get_workspace_manager()
            context['workspace_manager'] = workspace_manager
            context['output_path'] = workspace_manager.get_output_path(
                self.spec.domain, 
                ''  # Empty filename - agent will choose filename
            )
            
            # Get available tools from Knowledge Graph
            graph = get_knowledge_graph()
            tool_names = graph.get_tools_by_domain(self.spec.domain)
            
            tools_full = []
            for name in tool_names:
                # Get basic info from knowledge graph
                info = graph.get_node_info(name)
                if info:
                    info['name'] = name  # Ensure name is in dict
                    tools_full.append(info)
            
            # ALWAYS inject standard Data tools (for file ops)
            if self.spec.domain != 'Data':
                data_tool_names = graph.get_tools_by_domain('Data')
                for name in data_tool_names:
                    # Only include standard file ops
                    if name in ['Data_Save_File', 'Data_Read_File']:
                        info = graph.get_node_info(name)
                        if info:
                            info['name'] = name
                            tools_full.append(info)
            
            context['available_tools'] = tools_full
            
            # Get recent activity from Episodic Memory
            episodic = get_episodic_memory()
            recent = episodic.get_recent(hours=24, domain=self.spec.domain)
            context['recent_activity'] = [
                {
                    'event': mem.event_type,
                    'summary': mem.summary,
                    'timestamp': mem.timestamp
                }
                for mem in recent
            ]
            
        except Exception as e:
            self.logger.warning(f"[{self.trace_id}] Failed to load memory context: {str(e)}")
        
        return context
    
    @abstractmethod
    def execute(self) -> AgentResult:
        """
        Execute agent task.
        
        Must be implemented by all agent subclasses.
        
        Returns:
            AgentResult with execution outcome
        """
        pass
    
    def call_nexus(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Make a request through Nexus Core.
        
        Args:
            prompt: Prompt to send
            temperature: Override temperature (uses spec default if None)
            max_tokens: Override max tokens (uses spec default if None)
            
        Returns:
            Response content from Nexus Core
        """
        self.logger.debug(f"[{self.trace_id}] Agent {self.name} calling Nexus Core")
        
        request = Request(
            prompt=prompt,
            request_type="agent_call",
            metadata={
                'agent_name': self.name,
                'agent_trace_id': self.trace_id,
                'iteration': self.iterations_count
            },
            temperature=temperature or self.spec.temperature,
            max_tokens=max_tokens or self.spec.max_tokens,
            images=self.spec.images
        )
        
        response = self.nexus.route_request(request)
        
        if response.success:
            self.logger.debug(
                f"[{self.trace_id}] Agent {self.name} received response "
                f"(provider: {response.provider})"
            )
            return response.content
        else:
            self.logger.error(
                f"[{self.trace_id}] Agent {self.name} Nexus call failed: "
                f"{response.error}"
            )
            raise RuntimeError(f"Nexus Core request failed: {response.error}")
    
    def log(self, message: str, level: str = "info"):
        """
        Log a message with agent context.
        
        Args:
            message: Message to log
            level: Log level (debug, info, warning, error)
        """
        log_func = getattr(self.logger, level.lower(), self.logger.info)
        log_func(f"[{self.trace_id}] {self.name}: {message}")
    
    def run(self) -> AgentResult:
        """
        Run the agent with timing and error handling.
        
        Returns:
            AgentResult
        """
        self.started_at = utcnow_iso()
        start_time = time.time()
        
        self.logger.info(f"[{self.trace_id}] Agent {self.name} starting execution")
        
        try:
            result = self.execute()
            duration = time.time() - start_time
            result.duration_seconds = duration
            
            self.logger.info(
                f"[{self.trace_id}] Agent {self.name} completed successfully "
                f"({duration:.2f}s, {result.iterations} iterations)"
            )
            
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(
                f"[{self.trace_id}] Agent {self.name} failed: {str(e)} "
                f"({duration:.2f}s)"
            )
            
            return AgentResult(
                content="",
                agent_name=self.name,
                trace_id=self.trace_id,
                success=False,
                started_at=self.started_at,
                duration_seconds=duration,
                error=str(e),
                iterations=self.iterations_count
            )
        
        finally:
            self.cleanup()
    
    def cleanup(self):
        """
        Clean up agent resources.
        
        Called automatically after execution.
        Override in subclasses if additional cleanup needed.
        """
        self.completed_at = utcnow_iso()
        self.logger.debug(f"[{self.trace_id}] Agent {self.name} cleanup complete")
    
    def __str__(self) -> str:
        """String representation."""
        return f"{self.__class__.__name__}({self.name}, trace={self.trace_id})"
