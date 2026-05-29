"""
Aethvion Suite - Agent Factory
Core spawning engine for creating transient worker agents.

NOTE: This module is actively used by the CLI, server, and orchestrator.
It is not deprecated — the name "factory" refers to the dynamic agent-spawning
pattern, not a legacy abstraction. Do not remove without updating all call sites
in core/main.py, core/cli.py, and core/orchestration/.
"""

import yaml
from pathlib import Path
from typing import Optional, Type

from .agent_spec import AgentSpec
from .base_agent import BaseAgent
from .generic_agent import GenericAgent
from .agent_registry import get_agent_registry
from core.aether_core import AetherCore
from core.utils import get_logger, get_trace_manager, validate_tool_name
from core.workspace import get_workspace_manager

logger = get_logger(__name__)


class AgentFactory:
    """
    Agent Factory - Dynamic agent spawning system.
    
    Creates transient, stateless worker agents that:
    - Follow Aethvion naming: [Domain]_[Action]_[Object]
    - Route all requests through Aether Core
    - Execute tasks and automatically clean up
    """
    
    def __init__(self, nexus: AetherCore, config_path: Optional[str] = None):
        """
        Initialize Agent Factory.
        
        Args:
            nexus: AetherCore instance for routing
            config_path: Optional path to aethvion.yaml
        """
        self.nexus = nexus
        self.registry = get_agent_registry()
        self.trace_manager = get_trace_manager()
        
        # Load configuration
        if config_path is None:
            # __file__ = core/factory/agent_factory.py → parent.parent.parent = project root
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "core" / "config" / "aethvion.yaml"
        
        self.config = self._load_config(config_path)
        
        # Resource limits
        self.max_concurrent_agents = self.config.get('resources', {}).get('max_concurrent_agents', 10)
        self.agent_timeout = self.config.get('resources', {}).get('agent_timeout', 300)
        
        # Agent type registry
        self._agent_types: dict[str, Type[BaseAgent]] = {
            'generic': GenericAgent
        }
        
        logger.info(
            f"Agent Factory initialized (max_agents: {self.max_concurrent_agents}, "
            f"timeout: {self.agent_timeout}s)"
        )
    
    def _load_config(self, config_path: Path) -> dict:
        """Load configuration from YAML."""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {str(e)}")
            return {}
    
    def spawn(
        self,
        spec: AgentSpec,
        agent_type: str = 'generic'
    ) -> BaseAgent:
        """
        Spawn a new agent.
        
        Args:
            spec: Agent specification
            agent_type: Type of agent to spawn (default: 'generic')
            
        Returns:
            Spawned agent instance
            
        Raises:
            ValueError: If agent name invalid or resource limits exceeded
            RuntimeError: If agent type not found
        """
        # Validate Aethvion naming
        is_valid, error = validate_tool_name(spec.name)
        if not is_valid:
            logger.error(f"Invalid agent name: {spec.name} - {error}")
            raise ValueError(f"Agent name violates Aethvion Standard: {error}")
        
        # Check resource limits
        active_count = self.registry.get_active_count()
        if active_count >= self.max_concurrent_agents:
            logger.error(
                f"Cannot spawn agent {spec.name}: "
                f"Max concurrent agents reached ({self.max_concurrent_agents})"
            )
            raise ValueError(
                f"Resource limit: Maximum {self.max_concurrent_agents} concurrent agents"
            )
        
        # Get agent class
        agent_class = self._agent_types.get(agent_type)
        if not agent_class:
            raise RuntimeError(f"Unknown agent type: {agent_type}")
        
        # Generate Trace_ID for this agent
        trace_id = self.trace_manager.start_trace(metadata={
            'agent_name': spec.name,
            'agent_type': agent_type,
            'spec': spec.to_dict()
        })
        
        logger.info(f"[{trace_id}] Spawning agent: {spec.name} (type: {agent_type})")
        
        # Create agent instance
        agent = agent_class(spec=spec, nexus=self.nexus, trace_id=trace_id)
        
        # Register agent
        self.registry.register(agent)
        self.registry.update_status(trace_id, 'spawned')
        
        logger.info(
            f"[{trace_id}] Agent spawned successfully: {spec.name} "
            f"(active agents: {self.registry.get_active_count()})"
        )
        
        return agent
    
    def register_agent_type(self, type_name: str, agent_class: Type[BaseAgent]):
        """
        Register a custom agent type.
        
        Args:
            type_name: Name for this agent type
            agent_class: Agent class (must inherit from BaseAgent)
        """
        if not issubclass(agent_class, BaseAgent):
            raise ValueError(f"{agent_class} must inherit from BaseAgent")
        
        self._agent_types[type_name] = agent_class
        logger.info(f"Registered agent type: {type_name}")
    
    def get_active_agents(self) -> list:
        """
        Get list of active agents.
        
        Returns:
            List of agent info dicts
        """
        return self.registry.get_all_agents()
    
    def get_agent_count(self) -> int:
        """
        Get count of active agents.
        
        Returns:
            Number of active agents
        """
        return self.registry.get_active_count()
    
    def cleanup_stale_agents(self, max_age_seconds: int = 3600) -> int:
        """
        Clean up stale agent entries.
        
        Args:
            max_age_seconds: Maximum age before cleanup
            
        Returns:
            Number of cleaned up agents
        """
        count = self.registry.cleanup_stale(max_age_seconds)
        if count > 0:
            logger.info(f"Cleaned up {count} stale agent(s)")
        return count
