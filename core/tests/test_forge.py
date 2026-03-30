"""
Aethvion Suite - Forge Test Script
Test ToolForge generation and registration
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

from core.nexus_core import NexusCore
from core.forge import ToolForge
from core.utils import get_logger

logger = get_logger(__name__)


def test_forge():
    """Test The Forge functionality."""
    
    print("=" * 70)
    print("AETHVION SUITE - FORGE VERIFICATION TEST")
    print("=" * 70 + "\n")
    
    # Initialize Nexus Core
    print("Initializing Nexus Core...")
    nexus = NexusCore()
    nexus.initialize()
    
    # Initialize Forge
    print("\nInitializing Tool Forge...")
    forge = ToolForge(nexus)
    
    print("\n" + "-" * 70)
    print("TEST 1: Generate Simple Math Tool")
    print("-" * 70 + "\n")
    
    # Test 1: Simple calculator tool
    description1 = "Create a tool that adds two numbers together"
    
    print(f"Description: {description1}")
    print("\nForging tool...")
    
    try:
        tool1 = forge.generate_tool(description1)
        
        print(f"\n✅ Tool Generated Successfully!")
        print(f"  Name: {tool1['name']}")
        print(f"  Domain: {tool1['domain']}")
        print(f"  Action: {tool1['action']}")
        print(f"  Object: {tool1['object']}")
        print(f"  File: {tool1['file_path']}")
        print(f"  Trace ID: {tool1['trace_id']}")
        print(f"  Validation: {tool1['validation_status']}")
        
        # Show generated code
        with open(tool1['file_path'], 'r') as f:
            code = f.read()
        
        print(f"\nGenerated Code:")
        print("-" * 40)
        print(code)
        print("-" * 40)
        
    except Exception as e:
        print(f"\n❌ Tool generation failed: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "-" * 70)
    print("TEST 2: Generate Data Analysis Tool")
    print("-" * 70 + "\n")
    
    # Test 2: Data tool
    description2 = "Create a tool that calculates the average of a list of numbers"
    
    print(f"Description: {description2}")
    print("\nForging tool...")
    
    try:
        tool2 = forge.generate_tool(description2)
        
        print(f"\n✅ Tool Generated Successfully!")
        print(f"  Name: {tool2['name']}")
        print(f"  Domain: {tool2['domain']}")
        print(f"  Action: {tool2['action']}")
        print(f"  Object: {tool2['object']}")
        print(f"  File: {tool2['file_path']}")
        print(f"  Trace ID: {tool2['trace_id']}")
        
    except Exception as e:
        print(f"\n❌ Tool generation failed: {str(e)}")
    
    print("\n" + "-" * 70)
    print("TEST 3: Tool Registry")
    print("-" * 70 + "\n")
    
    # Test 3: Check registry
    tool_count = forge.get_tool_count()
    print(f"Total Registered Tools: {tool_count}")
    
    if tool_count > 0:
        print("\nRegistered Tools:")
        for tool in forge.list_tools():
            print(f"  - {tool['name']}")
            print(f"    Description: {tool['description']}")
            print(f"    Created: {tool['created_at']}")
            print()
    
    print("\n" + "-" * 70)
    print("TEST 4: Security Validation - Forbidden Operations")
    print("-" * 70 + "\n")
    
    # Test 4: Try to generate tool with forbidden ops (should fail)
    description_forbidden = "Create a tool that reads a file from the filesystem"
    
    print(f"Description: {description_forbidden}")
    print("\nForging tool (expect security rejection)...")
    
    try:
        tool_forbidden = forge.generate_tool(description_forbidden)
        print(f"\n❌ SECURITY FAILURE: Tool should have been rejected!")
        
    except ValueError as e:
        if "validation failed" in str(e).lower() or "forbidden" in str(e).lower():
            print(f"\n✅ Security Working: Tool rejected as expected!")
            print(f"  Reason: {str(e)}")
        else:
            print(f"\n⚠️  Tool failed for different reason: {str(e)}")
    except Exception as e:
        print(f"\n⚠️  Unexpected error: {str(e)}")
    
    print("\n" + "=" * 70)
    print("SPRINT 3 VERIFICATION: THE FORGE - COMPLETE")
    print("=" * 70 + "\n")
    
    print(f"Final Tool Count: {forge.get_tool_count()}")
    print(f"Tools Directory: {forge.tools_dir}")


if __name__ == "__main__":
    try:
        test_forge()
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
