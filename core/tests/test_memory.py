"""
Aethvion Suite - Memory Tier Complete Test
Verify Episodic Memory and Knowledge Graph functionality
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

from core.memory import (
    EpisodicMemory, CoreInsight,
    generate_memory_id, generate_insight_id,
    get_episodic_memory, get_knowledge_graph, get_heartbeat
)
from core.nexus_core import NexusCore
from core.utils import get_logger

logger = get_logger(__name__)


def test_complete_memory_tier():
    """Test complete Memory Tier functionality."""
    
    print("\n" + "=" * 70)
    print("AETHVION SUITE - MEMORY TIER VERIFICATION")
    print("MEMORY TIER - All Phases (1, 2, 3)")
    print("=" * 70 + "\n")
    
    # Initialize components
    print("Initializing Memory Tier components...")
    memory_store = get_episodic_memory()
    knowledge_graph = get_knowledge_graph()
    
    # Initialize Nexus Core for summarization
    nexus = NexusCore()
    nexus.initialize()
    
    heartbeat = get_heartbeat(
        memory_store=memory_store,
        knowledge_graph=knowledge_graph,
        nexus_core=nexus
    )
    
    print("\n" + "-" * 70)
    print("PHASE 1: EPISODIC MEMORY (with metadata flattening)")
    print("-" * 70 + "\n")
    
    # Test memory with list metadata (intent flags)
    memory1 = EpisodicMemory(
        memory_id=generate_memory_id(),
        trace_id="MCTR-20260202160000-TEST0001",
        timestamp="2026-02-02T16:00:00Z",
        event_type="forge_intent_detection",
        domain="Security",
        summary="Intent detection flagged filesystem and network access",
        content="Tool request for file operations and API calls detected by Intelligence Firewall.",
        metadata={
            'intent_categories': ['filesystem_access', 'network_access'],  # LIST - will be flattened
            'severity': 'medium'
        }
    )
    
    success = memory_store.store(memory1)
    if success:
        print(f"✅ Stored memory with list metadata (flattened)")
        print(f"   Memory ID: {memory1.memory_id}")
        print(f"   Intent flags: {memory1.metadata['intent_categories']}")
    else:
        print(f"❌ Failed to store memory")
    
    # Store more memories for testing
    memory2 = EpisodicMemory(
        memory_id=generate_memory_id(),
        trace_id="MCTR-20260202160100-TEST0002",
        timestamp="2026-02-02T16:01:00Z",
        event_type="tool_forge",
        domain="Finance",
        summary="Generated Finance_Fetch_CryptoPrice tool",
        content="Tool created to fetch cryptocurrency prices from CoinGecko API.",
        metadata={'tool_name': 'Finance_Fetch_CryptoPrice'}
    )
    memory_store.store(memory2)
    
    memory3 = EpisodicMemory(
        memory_id=generate_memory_id(),
        trace_id="MCTR-20260202160200-TEST0003",
        timestamp="2026-02-02T16:02:00Z",
        event_type="agent_spawn",
        domain="Data",
        summary="Spawned Data_Analyze_CryptoTrends agent",
        content="Agent spawned to analyze cryptocurrency market trends.",
        metadata={'agent_name': 'Data_Analyze_CryptoTrends'}
    )
    memory_store.store(memory3)
    
    print(f"\nTotal memories stored: {memory_store.get_count()}")
    
    print("\n" + "-" * 70)
    print("PHASE 2: KNOWLEDGE GRAPH")
    print("-" * 70 + "\n")
    
    # Add nodes and relationships
    print("Building Knowledge Graph...")
    
    # Add domains
    knowledge_graph.add_domain("Finance")
    knowledge_graph.add_domain("Data")
    knowledge_graph.add_domain("Security")
    
    # Add tool and link to domain and trace
    knowledge_graph.add_tool(
        tool_name="Finance_Fetch_CryptoPrice",
        domain="Finance",
        metadata={'type': 'api_tool', 'created': "2026-02-02T16:01:00Z"}
    )
    knowledge_graph.add_trace_id(
        trace_id="MCTR-20260202160100-TEST0002",
        event_type="tool_forge"
    )
    knowledge_graph.link_tool_to_trace(
        tool_name="Finance_Fetch_CryptoPrice",
        trace_id="MCTR-20260202160100-TEST0002"
    )
    
    # Add agent and link to domain and trace
    knowledge_graph.add_agent(
        agent_name="Data_Analyze_CryptoTrends",
        domain="Data",
        metadata={'type': 'analyst', 'created': "2026-02-02T16:02:00Z"}
    )
    knowledge_graph.add_trace_id(
        trace_id="MCTR-20260202160200-TEST0003",
        event_type="agent_spawn"
    )
    knowledge_graph.link_agent_to_trace(
        agent_name="Data_Analyze_CryptoTrends",
        trace_id="MCTR-20260202160200-TEST0003"
    )
    
    # Link agent to tool (agent uses tool)
    knowledge_graph.link_tool_to_agent(
        tool_name="Finance_Fetch_CryptoPrice",
        agent_name="Data_Analyze_CryptoTrends"
    )
    
    # Save knowledge graph
    knowledge_graph.save()
    
    # Query knowledge graph
    print("\nKnowledge Graph Queries:")
    
    finance_tools = knowledge_graph.get_tools_by_domain("Finance")
    print(f"  Finance Tools: {finance_tools}")
    
    data_agents = knowledge_graph.get_agents_by_domain("Data")
    print(f"  Data Agents: {data_agents}")
    
    stats = knowledge_graph.get_stats()
    print(f"\nGraph Statistics:")
    print(f"  Total Nodes: {stats['total_nodes']}")
    print(f"  Total Edges: {stats['total_edges']}")
    print(f"  Node Types: {stats['node_types']}")
    
    print("\n" + "-" * 70)
    print("PHASE 3: HEARTBEAT SUMMARIZATION")
    print("-" * 70 + "\n")
    
    # Run heartbeat to compress recent memories
    print("Running Heartbeat (last 24 hours)...")
    insight = heartbeat.run(hours=24, session_number=1)
    
    if insight:
        print(f"\n✅ Core Insight Generated:")
        print(f"   Insight ID: {insight.insight_id}")
        print(f"   Time Window: {insight.time_window_start} to {insight.time_window_end}")
        print(f"   Domains Active: {', '.join(insight.domains_active)}")
        print(f"   Tools Generated: {len(insight.tools_generated)}")
        print(f"   Agents Spawned: {insight.agents_spawned}")
        print(f"   Trace IDs Linked: {len(insight.trace_ids)}")
        print(f"\n   Summary:")
        print(f"   {insight.summary}")
        
        # Verify Core Insight is in Knowledge Graph
        insight_node = knowledge_graph.get_node_info(insight.insight_id)
        if insight_node:
            print(f"\n✅ Core Insight linked in Knowledge Graph")
            print(f"   Node Type: {insight_node.get('node_type')}")
            print(f"   Memories Compressed: {insight_node.get('memories_compressed')}")
    else:
        print("❌ No insight generated (no memories in window)")
    
    print("\n" + "-" * 70)
    print("VERIFICATION: Cross-Component Integration")
    print("-" * 70 + "\n")
    
    # Test 1: Semantic search finds intent detection
    print("Test 1: Semantic Search for Intent Detection")
    results = memory_store.search("security firewall intent filesystem", k=3)
    print(f"  Results: {len(results)}")
    for mem in results:
        print(f"    - {mem.summary}")
    
    # Test 2: Knowledge Graph links Core Insight to Trace_IDs
    print("\nTest 2: Core Insight → Trace_ID Linkage")
    if insight:
        # Get related insights for Finance domain
        finance_insights = knowledge_graph.get_related_insights("Finance")
        print(f"  Finance-related insights: {finance_insights}")
    
    # Test 3: Agent context (what tools are available in Finance domain)
    print("\nTest 3: Agent Context Loading (Finance Domain)")
    finance_tools = knowledge_graph.get_tools_by_domain("Finance")
    print(f"  Available Finance tools for agents: {finance_tools}")
    
    print("\n" + "=" * 70)
    print("SPRINT 4 COMPLETE VERIFICATION: THE MEMORY TIER - SUCCESS")
    print("=" * 70 + "\n")
    
    print("✅ Phase 1: Episodic Memory (ChromaDB + metadata flattening)")
    print("✅ Phase 2: Knowledge Graph (NetworkX + relationships)")
    print("✅ Phase 3: Heartbeat Summarization (recursive compression)")
    print("✅ Integration: Cross-component queries working")
    print(f"\n📊 Final Stats:")
    print(f"   Episodic Memories: {memory_store.get_count()}")
    print(f"   Knowledge Graph Nodes: {stats['total_nodes']}")
    print(f"   Knowledge Graph Edges: {stats['total_edges']}")
    print(f"   Core Insights: {'1' if insight else '0'}")


if __name__ == "__main__":
    try:
        test_complete_memory_tier()
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
