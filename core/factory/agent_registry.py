"""
Misaka Cipher - Agent Registry
Thread-safe registry of active agents
"""

from typing import Dict, List, Optional
from threading import Lock
from datetime import datetime

from .base_agent import BaseAgent
from core.utils import get_logger, utcnow_iso

logger = get_logger(__name__)


class AgentRegistry:
    """
    Thread-safe registry for tracking active agents.
    
    Maintains a central record of all spawned agents for monitoring
    and resource management.
    """
    
    def __init__(self):
        """Initialize registry."""
        self._agents: Dict[str, Dict] = {}
        self._lock = Lock()
        logger.info("Agent registry initialized")
    
    def register(self, agent: BaseAgent):
        """
        Register a new agent.
        
        Args:
            agent: Agent to register
        """
        with self._lock:
            self._agents[agent.trace_id] = {
                'agent': agent,
                'name': agent.name,
                'trace_id': agent.trace_id,
                'spec': agent.spec.to_dict(),
                'status': 'spawning',
                'registered_at': utcnow_iso()
            }
            
            logger.info(f"[{agent.trace_id}] Registered agent: {agent.name}")
    
    def update_status(self, trace_id: str, status: str):
        """
        Update agent status.
        
        Args:
            trace_id: Agent trace ID
            status: New status (spawning, executing, completed, failed)
        """
        with self._lock:
            if trace_id in self._agents:
                self._agents[trace_id]['status'] = status
                self._agents[trace_id]['updated_at'] = utcnow_iso()
                
                logger.debug(f"[{trace_id}] Agent status updated: {status}")
    
    def unregister(self, trace_id: str):
        """
        Unregister an agent.
        
        Args:
            trace_id: Agent trace ID
        """
        with self._lock:
            if trace_id in self._agents:
                agent_name = self._agents[trace_id]['name']
                del self._agents[trace_id]
                logger.info(f"[{trace_id}] Unregistered agent: {agent_name}")
    
    def get_agent(self, trace_id: str) -> Optional[Dict]:
        """
        Get agent information.
        
        Args:
            trace_id: Agent trace ID
            
        Returns:
            Agent info dict or None
        """
        with self._lock:
            return self._agents.get(trace_id)
    
    def get_all_agents(self) -> List[Dict]:
        """
        Get all registered agents.
        
        Returns:
            List of agent info dicts
        """
        with self._lock:
            return [
                {k: v for k, v in agent_info.items() if k != 'agent'}
                for agent_info in self._agents.values()
            ]
    
    def get_active_count(self) -> int:
        """
        Get count of active agents.
        
        Returns:
            Number of registered agents
        """
        with self._lock:
            return len(self._agents)
    
    def get_by_status(self, status: str) -> List[Dict]:
        """
        Get agents by status.
        
        Args:
            status: Status to filter by
            
        Returns:
            List of matching agent info dicts
        """
        with self._lock:
            return [
                {k: v for k, v in agent_info.items() if k != 'agent'}
                for agent_info in self._agents.values()
                if agent_info['status'] == status
            ]
    
    def cleanup_stale(self, max_age_seconds: int = 3600):
        """
        Clean up stale agent entries.
        
        Args:
            max_age_seconds: Maximum age before cleanup
            
        Returns:
            Number of entries cleaned up
        """
        with self._lock:
            now = datetime.now()
            to_remove = []
            
            for trace_id, agent_info in self._agents.items():
                registered_at = datetime.fromisoformat(agent_info['registered_at'])
                age_seconds = (now - registered_at).total_seconds()
                
                if age_seconds > max_age_seconds:
                    to_remove.append(trace_id)
            
            for trace_id in to_remove:
                agent_name = self._agents[trace_id]['name']
                del self._agents[trace_id]
                logger.warning(f"[{trace_id}] Cleaned up stale agent: {agent_name}")
            
            return len(to_remove)


# Global registry instance
_registry = AgentRegistry()


def get_agent_registry() -> AgentRegistry:
    """Get the global agent registry."""
    return _registry
