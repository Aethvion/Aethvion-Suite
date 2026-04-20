
import sys
from pathlib import Path
import os

# Add project root to sys.path
root = Path(r"c:\Aethvion\Aethvion-Suite")
sys.path.append(str(root))

from core.schedulers.schedule_manager import get_schedule_manager

print("Calling list_tasks()...")
try:
    mgr = get_schedule_manager()
    tasks = mgr.list_tasks()
    print(f"Tasks: {len(tasks)}")
    for t in tasks:
        print(f" - {t.get('name')} (ID: {t.get('id')})")
except Exception as e:
    import traceback
    traceback.print_exc()
print("Done.")
