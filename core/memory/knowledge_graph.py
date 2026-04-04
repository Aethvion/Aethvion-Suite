"""
Aethvion Suite - Knowledge Graph
NetworkX-based relationship mapping for domains, tools, agents, and trace IDs
"""

import json
# heavy import moved to lazy loading
# import networkx as nx
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from datetime import datetime

from core.utils import get_logger, utcnow_iso
from core.utils.paths import KNOWLEDGE_GRAPH

logger = get_logger(__name__)


class KnowledgeGraph:
    """
    Knowledge Graph - Relationship mapping using NetworkX.
    
    Maps relationships between:
    - Domains (Finance, Data, Security, etc.)
    - Tools (Finance_Fetch_StockPrice, etc.)
    - Agents (Data_Analyze_Dataset, etc.)
    - Trace IDs (ASTR-20260201...)
    - Core Insights (ASINS-20260201...)
    """
    
    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize Knowledge Graph.
        
        Args:
            storage_path: Path to knowledge_graph.json
        """
        if storage_path is None:
            storage_path = KNOWLEDGE_GRAPH
        
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Lazy import networkx
        import networkx as nx
        self.graph = nx.MultiDiGraph()
        
        # Load existing graph if available
        if self.storage_path.exists():
            self._load()
            logger.info(f"Loaded Knowledge Graph: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")
        else:
            logger.info("Initialized new Knowledge Graph")
    
    def add_domain(self, domain: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Add a domain node to the graph.
        
        Args:
            domain: Domain name (Finance, Data, etc.)
            metadata: Optional metadata
        """
        if not self.graph.has_node(domain):
            self.graph.add_node(
                domain,
                node_type='domain',
                created=utcnow_iso(),
                **(metadata or {})
            )
            logger.debug(f"Added domain: {domain}")
    
    def add_tool(self, tool_name: str, domain: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Add a tool node and link it to a domain.
        
        Args:
            tool_name: Tool name (Finance_Fetch_StockPrice)
            domain: Domain the tool belongs to
            metadata: Optional metadata
        """
        # Ensure domain exists
        self.add_domain(domain)
        
        # Add tool node
        if not self.graph.has_node(tool_name):
            # Filter out reserved keywords from metadata
            safe_metadata = {k: v for k, v in (metadata or {}).items() 
                           if k not in ['node_type', 'domain', 'created']}
            
            self.graph.add_node(
                tool_name,
                node_type='tool',
                domain=domain,
                created=utcnow_iso(),
                **safe_metadata
            )
            logger.debug(f"Added tool: {tool_name}")
        
        # Link tool to domain
        self.graph.add_edge(domain, tool_name, edge_type='contains', relationship='domain_contains_tool')
    
    def add_agent(self, agent_name: str, domain: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Add an agent node and link it to a domain.
        
        Args:
            agent_name: Agent name (Data_Analyze_Dataset)
            domain: Domain the agent operates in
            metadata: Optional metadata
        """
        # Ensure domain exists
        self.add_domain(domain)
        
        # Add agent node
        if not self.graph.has_node(agent_name):
            # Filter out reserved keywords from metadata
            safe_metadata = {k: v for k, v in (metadata or {}).items() 
                           if k not in ['node_type', 'domain', 'created']}
            
            self.graph.add_node(
                agent_name,
                node_type='agent',
                domain=domain,
                created=utcnow_iso(),
                **safe_metadata
            )
            logger.debug(f"Added agent: {agent_name}")
        
        # Link agent to domain
        self.graph.add_edge(domain, agent_name, edge_type='contains', relationship='domain_contains_agent')
    
    def add_trace_id(self, trace_id: str, event_type: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Add a Trace_ID node.
        
        Args:
            trace_id: Trace ID (ASTR-20260201...)
            event_type: Type of event (tool_forge, agent_spawn, etc.)
            metadata: Optional metadata
        """
        if not self.graph.has_node(trace_id):
            self.graph.add_node(
                trace_id,
                node_type='trace_id',
                event_type=event_type,
                created=utcnow_iso(),
                **(metadata or {})
            )
            logger.debug(f"Added Trace_ID: {trace_id}")
    
    def add_file_node(
        self,
        file_path: str,
        domain: str,
        trace_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Add a file node for user deliverables.
        
        Args:
            file_path: Relative path to file in outputfiles
            domain: Domain category (Finance, System, etc.)
            trace_id: Trace_ID that created this file
            metadata: Optional metadata (size, type, etc.)
        """
        # Ensure domain exists
        self.add_domain(domain)
        
        # Ensure trace_id exists
        if not self.graph.has_node(trace_id):
            self.add_trace_id(trace_id, 'file_creation')
        
        # Create unique file ID
        normalized_path = file_path.replace('/', '_').replace('\\', '_')
        file_id = f"file_{normalized_path}"
        
        # Add file node
        if not self.graph.has_node(file_id):
            safe_metadata = {k: v for k, v in (metadata or {}).items()
                           if k not in ['node_type', 'domain', 'path', 'trace_id', 'created']}
            
            self.graph.add_node(
                file_id,
                node_type='file',
                domain=domain,
                path=file_path,
                trace_id=trace_id,
                created=utcnow_iso(),
                **safe_metadata
            )
            logger.debug(f"Added file node: {file_id}")
        
        # Link file to domain
        self.graph.add_edge(domain, file_id, edge_type='contains', relationship='domain_contains_file')
        
        # Link trace_id to file
        self.graph.add_edge(trace_id, file_id, edge_type='created', relationship='trace_created_file')
    
    def add_core_insight(self, insight_id: str, trace_ids: List[str], metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Add a Core Insight and link it to originating Trace_IDs.
        
        Args:
            insight_id: Insight ID (ASINS-20260201...)
            trace_ids: List of Trace_IDs this insight summarizes
            metadata: Optional metadata
        """
        # Add insight node
        if not self.graph.has_node(insight_id):
            self.graph.add_node(
                insight_id,
                node_type='core_insight',
                created=utcnow_iso(),
                **(metadata or {})
            )
            logger.debug(f"Added Core Insight: {insight_id}")
        
        # Link to trace IDs
        for trace_id in trace_ids:
            if self.graph.has_node(trace_id):
                self.graph.add_edge(
                    insight_id,
                    trace_id,
                    edge_type='summarizes',
                    relationship='insight_summarizes_trace'
                )
    
    def link_tool_to_trace(self, tool_name: str, trace_id: str) -> None:
        """Link a tool to the Trace_ID that created it."""
        if self.graph.has_node(tool_name) and self.graph.has_node(trace_id):
            self.graph.add_edge(trace_id, tool_name, edge_type='created', relationship='trace_created_tool')
    
    def link_agent_to_trace(self, agent_name: str, trace_id: str) -> None:
        """Link an agent to the Trace_ID that spawned it."""
        if self.graph.has_node(agent_name) and self.graph.has_node(trace_id):
            self.graph.add_edge(trace_id, agent_name, edge_type='spawned', relationship='trace_spawned_agent')
    
    def link_tool_to_agent(self, tool_name: str, agent_name: str) -> None:
        """Link a tool to an agent that uses it."""
        if self.graph.has_node(tool_name) and self.graph.has_node(agent_name):
            self.graph.add_edge(agent_name, tool_name, edge_type='uses', relationship='agent_uses_tool')
    
    def get_tools_by_domain(self, domain: str) -> List[str]:
        """Get all tools in a specific domain."""
        if not self.graph.has_node(domain):
            return []
        
        tools = []
        for successor in self.graph.successors(domain):
            if self.graph.nodes[successor].get('node_type') == 'tool':
                tools.append(successor)
        
        return tools
    
    def get_agents_by_domain(self, domain: str) -> List[str]:
        """Get all agents in a specific domain."""
        if not self.graph.has_node(domain):
            return []
        
        agents = []
        for successor in self.graph.successors(domain):
            if self.graph.nodes[successor].get('node_type') == 'agent':
                agents.append(successor)
        
        return agents
    
    def get_files_by_domain(self, domain: str) -> List[Dict[str, Any]]:
        """
        Get all files in a specific domain.
        
        Args:
            domain: Domain name
            
        Returns:
            List of file info dicts
        """
        if not self.graph.has_node(domain):
            return []
        
        files = []
        for successor in self.graph.successors(domain):
            if self.graph.nodes[successor].get('node_type') == 'file':
                file_data = dict(self.graph.nodes[successor])
                file_data['file_id'] = successor
                files.append(file_data)
        
        return files
    
    def get_file_by_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """
        Get file created by a specific Trace_ID.
        
        Args:
            trace_id: Trace ID
            
        Returns:
            File info dict or None
        """
        if not self.graph.has_node(trace_id):
            return None
        
        # Find file nodes created by this trace
        for successor in self.graph.successors(trace_id):
            if self.graph.nodes[successor].get('node_type') == 'file':
                file_data = dict(self.graph.nodes[successor])
                file_data['file_id'] = successor
                return file_data
        
        return None
    
    def get_domains(self) -> List[str]:
        """Get all domain nodes."""
        return [
            node for node, data in self.graph.nodes(data=True)
            if data.get('node_type') == 'domain'
        ]
    
    def get_related_insights(self, domain: str) -> List[str]:
        """Get Core Insights related to a domain."""
        insights = set()
        
        # Get all tools/agents in domain
        tools = self.get_tools_by_domain(domain)
        agents = self.get_agents_by_domain(domain)
        
        # Find insights that reference these entities
        for node in tools + agents:
            for predecessor in self.graph.predecessors(node):
                if self.graph.nodes[predecessor].get('node_type') == 'core_insight':
                    insights.add(predecessor)
        
        return list(insights)
    
    def get_node_info(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific node."""
        if self.graph.has_node(node_id):
            return dict(self.graph.nodes[node_id])
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        node_types = {}
        for node, data in self.graph.nodes(data=True):
            node_type = data.get('node_type', 'unknown')
            node_types[node_type] = node_types.get(node_type, 0) + 1
        
        return {
            'total_nodes': self.graph.number_of_nodes(),
            'total_edges': self.graph.number_of_edges(),
            'node_types': node_types,
            'domains': len(self.get_domains())
        }
    
    def save(self) -> None:
        """Save graph to JSON."""
        try:
            # Convert to JSON-serializable format
            data = {
                'nodes': [
                    {'id': node, **data}
                    for node, data in self.graph.nodes(data=True)
                ],
                'edges': [
                    {'source': u, 'target': v, **data}
                    for u, v, data in self.graph.edges(data=True)
                ]
            }
            
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.debug(f"Saved Knowledge Graph to {self.storage_path}")
            
        except Exception as e:
            logger.error(f"Failed to save Knowledge Graph: {str(e)}")
    
    def _load(self) -> None:
        """Load graph from JSON."""
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            # Reconstruct graph
            for node_data in data.get('nodes', []):
                node_id = node_data.pop('id')
                self.graph.add_node(node_id, **node_data)
            
            for edge_data in data.get('edges', []):
                source = edge_data.pop('source')
                target = edge_data.pop('target')
                self.graph.add_edge(source, target, **edge_data)
            
            logger.debug(f"Loaded Knowledge Graph from {self.storage_path}")
            
        except Exception as e:
            logger.error(f"Failed to load Knowledge Graph: {str(e)}")
    
    def visualize_mermaid(self) -> str:
        """Generate Mermaid diagram of the graph."""
        lines = ["graph LR"]
        
        # Add nodes by type
        for node, data in self.graph.nodes(data=True):
            node_type = data.get('node_type', 'unknown')
            safe_id = node.replace('-', '_').replace(' ', '_')
            
            if node_type == 'domain':
                lines.append(f'    {safe_id}["{node}"]:::domain')
            elif node_type == 'tool':
                lines.append(f'    {safe_id}{{"{node}"}}:::tool')
            elif node_type == 'agent':
                lines.append(f'    {safe_id}("{node}"):::agent')
        
        # Add edges
        for u, v, data in self.graph.edges(data=True):
            safe_u = u.replace('-', '_').replace(' ', '_')
            safe_v = v.replace('-', '_').replace(' ', '_')
            lines.append(f'    {safe_u} --> {safe_v}')
        
        # Add styling
        lines.extend([
            "",
            "    classDef domain fill:#4a9eff,stroke:#333,stroke-width:2px",
            "    classDef tool fill:#51cf66,stroke:#333,stroke-width:2px",
            "    classDef agent fill:#ff6b6b,stroke:#333,stroke-width:2px"
        ])
        
        return "\n".join(lines)


# Global instance
_knowledge_graph = None


def get_knowledge_graph(storage_path: Optional[Path] = None) -> KnowledgeGraph:
    """Get the global knowledge graph."""
    global _knowledge_graph
    if _knowledge_graph is None:
        _knowledge_graph = KnowledgeGraph(storage_path)
    return _knowledge_graph
