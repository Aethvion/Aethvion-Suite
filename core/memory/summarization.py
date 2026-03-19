"""
Misaka Cipher - Heartbeat Summarization
Recursive log compression into Core Insights
"""

import yaml
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta

from .memory_spec import CoreInsight, generate_insight_id
from .episodic_memory import EpisodicMemoryStore, get_episodic_memory
from .knowledge_graph import KnowledgeGraph, get_knowledge_graph
from core.nexus_core import NexusCore, Request
from core.utils import get_logger
from core.utils.paths import KNOWLEDGE_INSIGHTS

logger = get_logger(__name__)


class Heartbeat:
    """
    Heartbeat - Recursive summarization engine.
    
    Compresses episodic memories into Core Insights at regular intervals:
    - Short (1 hour): Recent activity summary
    - Medium (6 hours): Session summary
    - Long (24 hours): Daily summary
    """
    
    def __init__(
        self,
        memory_store: Optional[EpisodicMemoryStore] = None,
        knowledge_graph: Optional[KnowledgeGraph] = None,
        nexus_core: Optional[NexusCore] = None,
        config_path: Optional[Path] = None
    ):
        """
        Initialize Heartbeat.
        
        Args:
            memory_store: Episodic memory store
            knowledge_graph: Knowledge graph
            nexus_core: Nexus Core for AI summarization
            config_path: Path to memory.yaml
        """
        self.memory_store = memory_store or get_episodic_memory()
        self.knowledge_graph = knowledge_graph or get_knowledge_graph()
        self.nexus_core = nexus_core
        
        # Load configuration
        if config_path is None:
            workspace = Path(__file__).parent.parent
            config_path = workspace / "config" / "memory.yaml"
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        self.config = config.get('summarization', {})
        self.enabled = self.config.get('enabled', True)
        
        # Intervals (in seconds)
        intervals = self.config.get('heartbeat_intervals', {})
        self.short_interval = intervals.get('short', 3600)    # 1 hour
        self.medium_interval = intervals.get('medium', 21600)  # 6 hours
        self.long_interval = intervals.get('long', 86400)      # 24 hours
        
        # Storage for insights
        self.insights_path = KNOWLEDGE_INSIGHTS
        self.insights_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info(
            f"Heartbeat initialized (intervals: {self.short_interval/3600}h, "
            f"{self.medium_interval/3600}h, {self.long_interval/3600}h)"
        )
    
    def run(self, hours: int, session_number: int = 1) -> Optional[CoreInsight]:
        """
        Run heartbeat summarization for a time window.
        
        Args:
            hours: Time window in hours
            session_number: Session number for insight ID
            
        Returns:
            Core Insight or None if no memories to summarize
        """
        if not self.enabled:
            logger.info("Heartbeat is disabled")
            return None
        
        logger.info(f"Running Heartbeat for last {hours} hours...")
        
        # Get memories from time window
        memories = self.memory_store.get_recent(hours=hours)
        
        if not memories:
            logger.info(f"No memories found in last {hours} hours")
            return None
        
        logger.info(f"Aggregating {len(memories)} memories...")
        
        # Aggregate data
        domains_active = set()
        tools_generated = []
        agents_spawned = 0
        trace_ids = []
        key_events = []
        
        for memory in memories:
            domains_active.add(memory.domain)
            trace_ids.append(memory.trace_id)
            
            if memory.event_type == 'tool_forge':
                tool_name = memory.metadata.get('tool_name', 'Unknown')
                tools_generated.append(tool_name)
                key_events.append(f"Forged tool: {tool_name}")
            
            elif memory.event_type == 'agent_spawn':
                agents_spawned += 1
                agent_name = memory.metadata.get('agent_name', 'Unknown')
                key_events.append(f"Spawned agent: {agent_name}")
            
            elif memory.event_type == 'forge_intent_detection':
                intent_categories = memory.metadata.get('intent_categories', '')
                key_events.append(f"Intent detected: {intent_categories}")
        
        # Generate natural language summary via Nexus Core (if available)
        if self.nexus_core:
            summary_prompt = self._build_summary_prompt(
                memories=memories,
                domains=list(domains_active),
                tools=tools_generated,
                agents=agents_spawned,
                events=key_events
            )
            
            try:
                response = self.nexus_core.route_request(Request(
                    prompt=summary_prompt,
                    request_type="heartbeat_summarization",
                    temperature=0.3,
                    max_tokens=500
                ))
                
                if response.success:
                    summary = response.content
                else:
                    summary = self._build_default_summary(domains_active, tools_generated, agents_spawned)
            except:
                summary = self._build_default_summary(domains_active, tools_generated, agents_spawned)
        else:
            summary = self._build_default_summary(domains_active, tools_generated, agents_spawned)
        
        # Create Core Insight
        time_window_end = datetime.now()
        time_window_start = time_window_end - timedelta(hours=hours)
        
        insight = CoreInsight(
            insight_id=generate_insight_id(session_number),
            timestamp=datetime.now().isoformat(),
            time_window_start=time_window_start.isoformat(),
            time_window_end=time_window_end.isoformat(),
            summary=summary,
            domains_active=list(domains_active),
            tools_generated=tools_generated,
            agents_spawned=agents_spawned,
            trace_ids=trace_ids,
            key_events=key_events[:10],  # Limit to top 10 events
            metadata={'compression_ratio': len(memories)}
        )
        
        # Add to Knowledge Graph
        self.knowledge_graph.add_core_insight(
            insight_id=insight.insight_id,
            trace_ids=trace_ids,
            metadata={
                'time_window_hours': hours,
                'memories_compressed': len(memories),
                'domains': list(domains_active)
            }
        )
        
        # Save knowledge graph
        self.knowledge_graph.save()
        
        logger.info(
            f"Heartbeat complete: {insight.insight_id} | "
            f"Compressed {len(memories)} memories | "
            f"Domains: {', '.join(domains_active)}"
        )
        
        return insight
    
    def _build_summary_prompt(
        self,
        memories: List,
        domains: List[str],
        tools: List[str],
        agents: int,
        events: List[str]
    ) -> str:
        """Build prompt for AI summarization."""
        return f"""Summarize the following system activity:

Domains Active: {', '.join(domains)}
Tools Generated: {len(tools)}
Agents Spawned: {agents}

Key Events:
{chr(10).join(f'- {event}' for event in events[:10])}

Provide a concise 2-3 sentence summary of the session's focus and accomplishments."""
    
    def _build_default_summary(self, domains: set, tools: List[str], agents: int) -> str:
        """Build default summary without AI."""
        parts = []
        
        if tools:
            parts.append(f"Generated {len(tools)} tool(s) in {', '.join(domains)}")
        
        if agents > 0:
            parts.append(f"spawned {agents} agent(s)")
        
        if not parts:
            return f"Activity in {', '.join(domains)} domain(s)"
        
        return ". ".join(parts) + "."


# Global instance
_heartbeat = None


def get_heartbeat(
    memory_store: Optional[EpisodicMemoryStore] = None,
    knowledge_graph: Optional[KnowledgeGraph] = None,
    nexus_core: Optional[NexusCore] = None
) -> Heartbeat:
    """Get the global heartbeat instance."""
    global _heartbeat
    if _heartbeat is None:
        _heartbeat = Heartbeat(memory_store, knowledge_graph, nexus_core)
    return _heartbeat
