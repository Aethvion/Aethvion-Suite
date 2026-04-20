import os
import json
from pathlib import Path
from core.workspace.usage_tracker import get_usage_tracker

PROJECT_ROOT = Path(__file__).parent.parent
EXCLUDE_DIRS = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', '.gemini', 'data'}

def get_file_counts() -> str:
    """Return a summary of all file types and their counts in the project."""
    counts = {}
    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for file in files:
            ext = Path(file).suffix.lower()
            if ext:
                counts[ext] = counts.get(ext, 0) + 1
            else:
                counts['no_extension'] = counts.get('no_extension', 0) + 1
    
    summary = ["File Counts by Extension:"]
    for ext, count in sorted(counts.items(), key=lambda item: item[1], reverse=True):
        summary.append(f"- {ext}: {count}")
    return "\n".join(summary)

def get_project_size() -> str:
    """Return the total size of the project directory in megabytes."""
    total_size = 0
    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for file in files:
            fp = os.path.join(root, file)
            if not os.path.islink(fp):
                try:
                    total_size += os.path.getsize(fp)
                except Exception:
                    pass
    
    mb = round(total_size / (1024 * 1024), 2)
    return f"Total Project Size (excluding ignored dirs): {mb} MB"

def get_token_usage() -> str:
    """Return the monetary cost and token usage for today, this month, and all-time."""
    tracker = get_usage_tracker()
    today = tracker.get_today_summary()
    
    from datetime import datetime
    now = datetime.utcnow()
    month_str = now.strftime("%Y-%m")
    month_summary = tracker.get_monthly_summary(month_str)
    
    total = tracker.get_summary()
    
    return f"""Token Usage & Cost:
--- TODAY ---
Tokens: {today.get('tokens', 0)}
Cost: ${today.get('cost', 0.0):.6f}

--- THIS MONTH ({month_str}) ---
Calls: {month_summary.get('total_calls', 0)}
Tokens: {month_summary.get('total_tokens', 0)}
Cost: ${month_summary.get('total_cost', 0.0):.6f}

--- ALL-TIME ---
Total Calls: {total.get('total_calls', 0)}
Total Tokens: {total.get('total_tokens', 0)}
Total Cost: ${total.get('total_cost', 0.0):.6f}
"""

def query_usage_detailed(query: str) -> str:
    """Provides detailed answers to usage questions by searching logs."""
    from datetime import datetime, timedelta
    tracker = get_usage_tracker()
    query_lower = query.lower()
    
    if "peak" in query_lower or "highest" in query_lower or "expensive day" in query_lower:
        peak = tracker.get_peak_usage_day()
        if peak['date']:
            return f"Peak usage was on {peak['date']} with a total cost of ${peak['cost']:.6f}."
        return "No usage data found to determine peak day."
        
    if "month" in query_lower:
        now = datetime.utcnow()
        if "last month" in query_lower:
            first_of_this_month = now.replace(day=1)
            last_month = first_of_this_month - timedelta(days=1)
            target = last_month.strftime("%Y-%m")
        else:
            target = now.strftime("%Y-%m")
            
        summary = tracker.get_monthly_summary(target)
        return (f"Usage for {target}:\n"
                f"- Total Calls: {summary.get('total_calls', 0)}\n"
                f"- Total Tokens: {summary.get('total_tokens', 0)}\n"
                f"- Total Cost: ${summary.get('total_cost', 0.0):.6f}")

    # Fallback to today if nothing else matches
    today = tracker.get_today_summary()
    return f"Today's usage ({datetime.utcnow().strftime('%Y-%m-%d')}):\n- Tokens: {today.get('tokens', 0)}\n- Cost: ${today.get('cost', 0.0):.6f}"

def get_system_map() -> str:
    """Returns a textual map/overview of the Aethvion Suite architecture directories."""
    return """Aethvion Suite Architectural Map:
- /apps: User applications (Specter, Synapse).
- /core: The Nervous System (Routing, Ports, Settings, AI interfaces).
- /data: Runtime data (core config, ai history, tools, app data).
- /assets: Static assets (character sprites, icons).
- Start_Aethvion_Suite.bat: Primary launch script.
"""

def search_scripts(keyword: str) -> str:
    """Searches .py and .js files for a particular exact keyword and returns matching files."""
    matches = []
    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for file in files:
            if file.endswith('.py') or file.endswith('.js'):
                path = os.path.join(root, file)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        if keyword.lower() in f.read().lower():
                            matches.append(os.path.relpath(path, PROJECT_ROOT))
                except Exception:
                    pass
                    
    if not matches:
        return f"No scripts found containing '{keyword}'."
    return "Found keyword in these files:\n" + "\n".join(matches)

# List of tools formatted for OpenAI/Gemini tool calling
ASSISTANT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_file_counts",
            "description": "Returns counts of all file extensions (.json, .py, .js, etc) in the project.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_size",
            "description": "Returns the total byte size of the project in MB.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_token_usage",
            "description": "Returns a high-level overview of money spent and LLM tokens used today, this month, and all-time.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_usage_detailed",
            "description": "Provides detailed answers to granular usage questions (e.g., peak usage day, last month's cost).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The specific usage question to answer."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_map",
            "description": "Returns a directory layout and description of the Aethvion Suite Architecture.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_scripts",
            "description": "Searches inside all python and javascript files for a keyword.",
            "parameters": {
                "type": "object", 
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "The term or variable to search for."
                    }
                },
                "required": ["keyword"]
            }
        }
    }
]

ASSISTANT_TOOL_MAP = {
    "get_file_counts": get_file_counts,
    "get_project_size": get_project_size,
    "get_token_usage": get_token_usage,
    "query_usage_detailed": query_usage_detailed,
    "get_system_map": get_system_map,
    "search_scripts": search_scripts
}
