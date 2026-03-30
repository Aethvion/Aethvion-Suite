"""
Aethvion Suite - Factory Test Script
Test AgentFactory spawning and execution
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

from core.nexus_core import NexusCore
from core.factory import AgentFactory, AgentSpec, get_template
from core.utils import get_logger

logger = get_logger(__name__)


def test_factory():
    """Test The Factory functionality."""
    
    print("=" * 70)
    print("AETHVION SUITE - FACTORY VERIFICATION TEST")
    print("=" * 70 + "\n")
    
    # Initialize Nexus Core
    print("Initializing Nexus Core...")
    nexus = NexusCore()
    nexus.initialize()
    
    # Initialize Factory
    print("\nInitializing Agent Factory...")
    factory = AgentFactory(nexus)
    
    print("\n" + "-" * 70)
    print("TEST 1: Spawn Generic Agent")
    print("-" * 70 + "\n")
    
    # Test 1: Generic agent with custom spec
    spec1 = AgentSpec(
        domain="System",
        action="Execute",
        object="Demo",
        context={
            'prompt': "Introduce yourself as Misaka agent and mention your Trace ID."
        },
        description="Test: basic agent spawn"
    )
    
    print(f"Agent Spec: {spec1.name}")
    print(f"Context: {spec1.context}")
    
    agent1 = factory.spawn(spec1)
    print(f"\nSpawned Agent: {agent1.name}")
    print(f"Trace ID: {agent1.trace_id}")
    print(f"Active Agents: {factory.get_agent_count()}")
    
    result1 = agent1.run()
    
    print(f"\nAgent Result:")
    print(f"  Success: {result1.success}")
    print(f"  Duration: {result1.duration_seconds:.2f}s")
    print(f"  Iterations: {result1.iterations}")
    print(f"\nResponse:")
    print(result1.content[:300] + "..." if len(result1.content) > 300 else result1.content)
    
    print("\n" + "-" * 70)
    print("TEST 2: Use Agent Template - Data Analyst")
    print("-" * 70 + "\n")
    
    # Test 2: Data Analyst template
    spec2 = get_template(
        'data_analyst',
        data_source="Q1 2026 sales figures",
        analysis_type="summary"
    )
    
    print(f"Template: Data Analyst")
    print(f"Agent Name: {spec2.name}")
    print(f"Temperature: {spec2.temperature}")
    
    agent2 = factory.spawn(spec2)
    print(f"\nSpawned Agent: {agent2.name}")
    print(f"Trace ID: {agent2.trace_id}")
    
    result2 = agent2.run()
    
    print(f"\nAgent Result:")
    print(f"  Success: {result2.success}")
    print(f"  Duration: {result2.duration_seconds:.2f}s")
    print(f"\nAnalysis:")
    print(result2.content[:300] + "..." if len(result2.content) > 300 else result2.content)
    
    print("\n" + "-" * 70)
    print("TEST 3: Use Agent Template - Question Answerer")
    print("-" * 70 + "\n")
    
    # Test 3: Question Answerer
    spec3 = get_template(
        'question_answerer',
        question="What is the Aethvion naming standard for tools?",
        context="The Aethvion standard requires: [Domain]_[Action]_[Object]"
    )
    
    print(f"Template: Question Answerer")
    print(f"Agent Name: {spec3.name}")
    
    agent3 = factory.spawn(spec3)
    print(f"\nSpawned Agent: {agent3.name}")
    print(f"Trace ID: {agent3.trace_id}")
    
    result3 = agent3.run()
    
    print(f"\nAgent Result:")
    print(f"  Success: {result3.success}")
    print(f"  Duration: {result3.duration_seconds:.2f}s")
    print(f"\nAnswer:")
    print(result3.content)
    
    print("\n" + "-" * 70)
    print("TEST 4: Resource Limits & Registry")
    print("-" * 70 + "\n")
    
    # Test 4: Check registry
    active_agents = factory.get_active_agents()
    print(f"Active Agents in Registry: {len(active_agents)}")
    
    for agent_info in active_agents:
        print(f"  - {agent_info['name']} [{agent_info['trace_id'][:20]}...] - {agent_info['status']}")
    
    print(f"\nResource Limits:")
    print(f"  Max Concurrent Agents: {factory.max_concurrent_agents}")
    print(f"  Agent Timeout: {factory.agent_timeout}s")
    
    print("\n" + "-" * 70)
    print("TEST 5: Aethvion Naming Validation")
    print("-" * 70 + "\n")
    
    # Test 5: Try invalid name (should fail)
    try:
        invalid_spec = AgentSpec(
            domain="agent",   # lowercase - will auto-capitalize
            action="test",    # lowercase - will auto-capitalize
            object="demo",    # lowercase - will auto-capitalize
            context={'prompt': "test"}
        )
        print(f"Agent Name (auto-corrected): {invalid_spec.name}")
        
        # This should succeed because AgentSpec capitalizes
        agent_invalid = factory.spawn(invalid_spec)
        print(f"✓ Agent spawned (name was auto-capitalized): {agent_invalid.name}")
        
    except ValueError as e:
        print(f"✗ Failed to spawn (as expected): {str(e)}")
    
    print("\n" + "=" * 70)
    print("SPRINT 2 VERIFICATION: THE FACTORY - COMPLETE")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    try:
        test_factory()
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
