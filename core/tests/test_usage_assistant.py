import sys
from pathlib import Path
from datetime import datetime

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from core.workspace.usage_tracker import get_usage_tracker
from core.system_retrieval import query_usage_detailed, get_token_usage

def test_usage_retrieval():
    print("--- Testing Usage Retrieval ---")
    tracker = get_usage_tracker()
    
    # 1. Test get_token_usage (Static summary)
    print("\n[1] Testing get_token_usage()...")
    summary = get_token_usage()
    print(summary)
    
    # 2. Test query_usage_detailed for Peak Day
    print("\n[2] Testing query_usage_detailed('peak')...")
    peak_resp = query_usage_detailed("What was my peak usage day?")
    print(f"Response: {peak_resp}")
    
    # 3. Test query_usage_detailed for Month
    print("\n[3] Testing query_usage_detailed('month')...")
    this_month = datetime.utcnow().strftime("%Y-%m")
    month_resp = query_usage_detailed(f"How much did I use this month ({this_month})?")
    print(f"Response: {month_resp}")

    print("\n--- Test Complete ---")

if __name__ == "__main__":
    test_usage_retrieval()
