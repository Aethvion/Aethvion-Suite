"""
Aethvion Suite - Usage Tracker
Tracks API calls, token usage, and estimated costs.
"""

import json
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict

from core.utils import get_logger

logger = get_logger(__name__)

_instance = None
_lock = threading.Lock()

MAX_LOG_ENTRIES = 10000
# __file__ = core/workspace/usage_tracker.py → parent.parent.parent = project root
DATA_DIR = Path(__file__).parent.parent.parent / "data"
# New structure: data/ai/logs/usage/YYYY-MM/usage_YYYY-MM-DD.json
LOGS_DIR = DATA_DIR / "ai" / "logs" / "usage"


def get_usage_tracker():
    """Get or create the singleton UsageTracker."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = UsageTracker()
    return _instance


class UsageTracker:
    """Tracks all API usage: calls, tokens, costs."""

    def __init__(self):
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        self._model_costs = self._load_model_costs()
        logger.info("UsageTracker initialized with daily file structure")

    def _get_daily_log_path(self, dt: Optional[datetime] = None) -> Path:
        """Get the path to the daily log file based on a datetime (default UTC now)."""
        dt = dt or datetime.utcnow()
        month_str = dt.strftime("%Y-%m")
        day_str = dt.strftime("%Y-%m-%d")
        dir_path = LOGS_DIR / month_str
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path / f"usage_{day_str}.json"

    def _load_day_logs(self, dt: datetime) -> List[Dict[str, Any]]:
        """Load logs for a specific day."""
        path = self._get_daily_log_path(dt)
        if path.exists():
            try:
                with _lock: # Use lock for reading to prevent race conditions during write
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        return data if isinstance(data, list) else []
            except Exception as e:
                logger.error(f"Failed to load usage for {dt.date()}: {e}")
        return []

    def _load_model_costs(self) -> Dict[str, Dict[str, float]]:
        """Load per-model input/output cost data from model_registry.json."""
        costs = {}
        try:
            registry_path = DATA_DIR / "config" / "model_registry.json"
            if registry_path.exists():
                with open(registry_path, "r", encoding="utf-8") as f:
                    registry = json.load(f)
                for provider_name, provider_cfg in registry.get("providers", {}).items():
                    for model_key, model_info in provider_cfg.get("models", {}).items():
                        if isinstance(model_info, dict):
                            model_id = model_info.get("id", model_key)
                            # New per-1M format
                            input_cost = model_info.get("input_cost_per_1m_tokens", 0.0)
                            output_cost = model_info.get("output_cost_per_1m_tokens", 0.0)
                            # Backward compat: convert old per-1k to per-1M
                            if input_cost == 0 and output_cost == 0:
                                legacy = model_info.get("cost_per_1k_tokens", 0.0)
                                if legacy:
                                    input_cost = legacy * 1000
                                    output_cost = legacy * 1000
                            costs[model_id] = {
                                "input": input_cost,
                                "output": output_cost
                            }
        except Exception as e:
            logger.warning(f"Could not load model costs: {e}")
        return costs

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count from text length (approx 1 token ≈ 4 chars)."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    def log_api_call(
        self,
        provider: str,
        model: str,
        prompt: str,
        response_content: str,
        trace_id: str,
        operation: str = "chat",
        success: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
        source: str = "chat"
    ):
        """Log an API call with token and cost estimation."""
        metadata = metadata or {}
        now = datetime.utcnow()

        # Extract or estimate token counts
        usage_data = metadata.get("usage", {})
        prompt_tokens = usage_data.get("prompt_tokens") or usage_data.get("prompt_token_count") or self.estimate_tokens(prompt)
        completion_tokens = usage_data.get("completion_tokens") or usage_data.get("candidates_token_count") or self.estimate_tokens(response_content)
        total_tokens = usage_data.get("total_tokens") or (prompt_tokens + completion_tokens)

        # Estimate cost (per 1M tokens)
        model_costs = self._model_costs.get(model, {"input": 0.0, "output": 0.0})
        input_cost = (prompt_tokens / 1_000_000) * model_costs["input"]
        output_cost = (completion_tokens / 1_000_000) * model_costs["output"]
        estimated_cost = input_cost + output_cost

        entry = {
            "timestamp": now.isoformat() + "Z",
            "provider": provider,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "input_cost": round(input_cost, 6),
            "output_cost": round(output_cost, 6),
            "estimated_cost": round(estimated_cost, 6),
            "operation": operation,
            "trace_id": trace_id,
            "success": success,
            "tokens_estimated": "usage" not in metadata,
            "source": source
        }

        # Persist routing metadata
        if metadata.get("route_picker"):
            entry["routing_model"] = metadata["route_picker"]
        if metadata.get("routed_to"):
            entry["routed_model"] = metadata["routed_to"]
        if metadata.get("routing_reason"):
            entry["routing_reason"] = metadata["routing_reason"]

        # Append to daily file
        path = self._get_daily_log_path(now)
        try:
            with _lock:
                logs = []
                if path.exists():
                    with open(path, "r", encoding="utf-8") as f:
                        logs = json.load(f)
                logs.append(entry)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(logs, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to log usage to {path}: {e}")

        logger.debug(
            f"[{trace_id}] Usage logged: {provider}/{model} "
            f"tokens={total_tokens} in=${input_cost:.6f} out=${output_cost:.6f} source={source}"
        )

    def _compute_entry_costs(self, entry: Dict[str, Any]) -> tuple:
        """Compute input/output costs for an entry, recalculating from tokens if missing."""
        ic = entry.get("input_cost", 0.0)
        oc = entry.get("output_cost", 0.0)

        if "input_cost" not in entry:
            m = entry.get("model", "unknown")
            pt = entry.get("prompt_tokens", 0)
            ct = entry.get("completion_tokens", 0)
            model_costs = self._model_costs.get(m, {"input": 0.0, "output": 0.0})
            ic = (pt / 1_000_000) * model_costs["input"]
            oc = (ct / 1_000_000) * model_costs["output"]

        return ic, oc, ic + oc

    def _get_entries_for_range(self, start_date: datetime, end_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Retrieve all entries between start_date and end_date (exclusive)."""
        end_date = end_date or datetime.utcnow()
        all_entries = []
        
        current = start_date
        while current <= end_date:
            all_entries.extend(self._load_day_logs(current))
            current += timedelta(days=1)
            
        # Filter strictly by timestamp if needed, and sort
        start_iso = start_date.isoformat() + "Z"
        end_iso = end_date.isoformat() + "Z"
        
        filtered = [
            e for e in all_entries 
            if start_iso <= e.get("timestamp", "") <= end_iso
        ]
        filtered.sort(key=lambda x: x.get("timestamp", ""))
        return filtered

    def get_summary(
        self, 
        start_date: Optional[datetime] = None, 
        end_date: Optional[datetime] = None, 
        days: int = 30,
        show_local: bool = True,
        show_api: bool = True
    ) -> Dict[str, Any]:
        """Get aggregated usage summary for a date range or last X days."""
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=days)
        
        entries = self._get_entries_for_range(start_date, end_date)
        
        # Apply provider filtering
        if not show_local or not show_api:
            entries = [
                e for e in entries 
                if (show_local and e.get("provider") == "local") or 
                   (show_api and e.get("provider") != "local")
            ]

        if not entries:
            return {
                "total_calls": 0,
                "total_tokens": 0,
                "total_input_cost": 0.0,
                "total_output_cost": 0.0,
                "total_cost": 0.0,
                "by_provider": {},
                "by_model": {},
                "success_rate": 0.0,
                "since": start_date.isoformat() + "Z"
            }

        by_provider = defaultdict(lambda: {"calls": 0, "tokens": 0, "input_cost": 0.0, "output_cost": 0.0, "cost": 0.0})
        by_model = defaultdict(lambda: {
            "calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
            "tokens": 0, "input_cost": 0.0, "output_cost": 0.0, "cost": 0.0
        })
        total_tokens = 0
        total_input_cost = 0.0
        total_output_cost = 0.0
        successes = 0

        for entry in entries:
            p = entry.get("provider", "unknown")
            m = entry.get("model", "unknown")
            t = entry.get("total_tokens", 0)
            pt = entry.get("prompt_tokens", 0)
            ct = entry.get("completion_tokens", 0)

            ic, oc, c = self._compute_entry_costs(entry)

            by_provider[p]["calls"] += 1
            by_provider[p]["tokens"] += t
            by_provider[p]["input_cost"] += ic
            by_provider[p]["output_cost"] += oc
            by_provider[p]["cost"] += c

            by_model[m]["calls"] += 1
            by_model[m]["prompt_tokens"] += pt
            by_model[m]["completion_tokens"] += ct
            by_model[m]["tokens"] += t
            by_model[m]["input_cost"] += ic
            by_model[m]["output_cost"] += oc
            by_model[m]["cost"] += c

            total_tokens += t
            total_input_cost += ic
            total_output_cost += oc
            if entry.get("success", True):
                successes += 1

        # Round aggregated costs
        for v in by_provider.values():
            v["input_cost"] = round(v["input_cost"], 6)
            v["output_cost"] = round(v["output_cost"], 6)
            v["cost"] = round(v["cost"], 6)
        for v in by_model.values():
            v["input_cost"] = round(v["input_cost"], 6)
            v["output_cost"] = round(v["output_cost"], 6)
            v["cost"] = round(v["cost"], 6)

        return {
            "total_calls": len(entries),
            "total_tokens": total_tokens,
            "total_input_cost": round(total_input_cost, 6),
            "total_output_cost": round(total_output_cost, 6),
            "total_cost": round(total_input_cost + total_output_cost, 6),
            "by_provider": dict(by_provider),
            "by_model": dict(by_model),
            "success_rate": round(successes / len(entries) * 100, 1) if entries else 0,
            "since": entries[0].get("timestamp") if entries else start_date.isoformat() + "Z"
        }

    def get_monthly_summary(self, year_month: str) -> Dict[str, Any]:
        """
        Get aggregated summary for a specific month.
        Args:
            year_month: Format 'YYYY-MM'
        """
        month_dir = LOGS_DIR / year_month
        if not month_dir.exists():
            return {"total_calls": 0, "total_tokens": 0, "total_cost": 0.0}
            
        all_entries = []
        for log_file in month_dir.glob("usage_*.json"):
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    all_entries.extend(json.load(f))
            except Exception:
                continue
                
        return self._summarize_entries(all_entries)

    def get_peak_usage_day(self) -> Dict[str, Any]:
        """
        Find the day with the highest total cost.
        """
        peak_date = None
        max_cost = -1.0
        
        # Scan all month directories
        if not LOGS_DIR.exists():
            return {"date": None, "cost": 0.0}
            
        for month_dir in sorted(LOGS_DIR.iterdir(), reverse=True):
            if not month_dir.is_dir(): continue
            
            for log_file in month_dir.glob("usage_*.json"):
                try:
                    date_str = log_file.stem.replace("usage_", "")
                    with open(log_file, 'r', encoding='utf-8') as f:
                        entries = json.load(f)
                        summary = self._summarize_entries(entries)
                        cost = summary.get("total_cost", 0.0)
                        if cost > max_cost:
                            max_cost = cost
                            peak_date = date_str
                except Exception:
                    continue
                    
        return {
            "date": peak_date,
            "cost": round(max_cost, 6) if max_cost >= 0 else 0.0
        }

    def _summarize_entries(self, entries: List[Dict]) -> Dict[str, Any]:
        """Helper to aggregate a list of usage entries."""
        total_tokens = 0
        total_input_cost = 0.0
        total_output_cost = 0.0
        
        for entry in entries:
            total_tokens += entry.get("total_tokens", 0) # Changed from "tokens" to "total_tokens" to match log_api_call
            total_input_cost += entry.get("input_cost", 0.0)
            total_output_cost += entry.get("output_cost", 0.0)
            
        return {
            "total_calls": len(entries),
            "total_tokens": total_tokens,
            "total_input_cost": round(total_input_cost, 6),
            "total_output_cost": round(total_output_cost, 6),
            "total_cost": round(total_input_cost + total_output_cost, 6)
        }

    def get_history(self, limit: int = 100, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, show_local: bool = True, show_api: bool = True) -> List[Dict[str, Any]]:
        """Get recent usage entries (newest first)."""
        if start_date:
            entries = self._get_entries_for_range(start_date, end_date)
            # Filter providers
            if not show_local or not show_api:
                entries = [
                    e for e in entries 
                    if (show_local and e.get("provider") == "local") or 
                       (show_api and e.get("provider") != "local")
                ]
            entries = list(reversed(entries))[:limit]
        else:
            all_recent = []
            now = datetime.utcnow()
            for i in range(365):
                dt = now - timedelta(days=i)
                day_logs = self._load_day_logs(dt)
                if day_logs:
                    # Filter providers
                    if not show_local or not show_api:
                        day_logs = [
                            e for e in day_logs 
                            if (show_local and e.get("provider") == "local") or 
                               (show_api and e.get("provider") != "local")
                        ]
                    if day_logs:
                        all_recent.extend(reversed(day_logs))
                        if len(all_recent) >= limit:
                            break
            entries = all_recent[:limit]
        
        for entry in entries:
            if "input_cost" not in entry:
                ic, oc, c = self._compute_entry_costs(entry)
                entry["input_cost"] = round(ic, 6)
                entry["output_cost"] = round(oc, 6)
                entry["estimated_cost"] = round(c, 6)
        return entries

    def get_usage_by_trace_id(self, trace_id: str) -> Dict[str, Any]:
        """Get aggregated usage summary for trace_id. Scans last 7 days."""
        start = datetime.utcnow() - timedelta(days=7)
        entries = self._get_entries_for_range(start)
        # Search for main ID and router-specific ID
        router_trace_id = f"{trace_id}-router"
        calls = [e for e in entries if e.get("trace_id") in [trace_id, router_trace_id]]
        if not calls:
            return {}

        models_used = {}
        total_prompt = 0
        total_completion = 0
        total_input_cost = 0.0
        total_output_cost = 0.0
        routing_model = None
        routed_model = None
        routing_reason = None

        for entry in calls:
            ic, oc, c = self._compute_entry_costs(entry)
            m = entry.get("model", "unknown")
            pt = entry.get("prompt_tokens", 0)
            ct = entry.get("completion_tokens", 0)

            total_prompt += pt
            total_completion += ct
            total_input_cost += ic
            total_output_cost += oc

            if m not in models_used:
                models_used[m] = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "input_cost": 0.0, "output_cost": 0.0}
            models_used[m]["calls"] += 1
            models_used[m]["prompt_tokens"] += pt
            models_used[m]["completion_tokens"] += ct
            models_used[m]["input_cost"] += ic
            models_used[m]["output_cost"] += oc

            if not routing_model and entry.get("routing_model"):
                routing_model = entry["routing_model"]
            if not routed_model and entry.get("routed_model"):
                routed_model = entry["routed_model"]
            if not routing_reason and entry.get("routing_reason"):
                routing_reason = entry["routing_reason"]

        result = {
            "api_calls": len(calls),
            "models_used": models_used,
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
            "total_input_cost": round(total_input_cost, 6),
            "total_output_cost": round(total_output_cost, 6),
            "total_cost": round(total_input_cost + total_output_cost, 6),
        }
        if routing_model: result["routing_model"] = routing_model
        if routed_model: result["routed_model"] = routed_model
        if routing_reason: result["routing_reason"] = routing_reason
        return result

    def get_cost_by_model(self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, days: int = 30, show_local: bool = True, show_api: bool = True) -> Dict[str, Any]:
        """Get cost breakdown by model for chart data."""
        summary = self.get_summary(start_date, end_date, days, show_local=show_local, show_api=show_api)
        models = []
        for model_name, data in summary.get("by_model", {}).items():
            models.append({
                "name": model_name,
                "input_cost": data.get("input_cost", 0.0),
                "output_cost": data.get("output_cost", 0.0),
                "total_cost": data.get("cost", 0.0)
            })
        models.sort(key=lambda x: x["total_cost"], reverse=True)
        return {"models": models}

    def get_tokens_by_model(self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, days: int = 30, show_local: bool = True, show_api: bool = True) -> Dict[str, Any]:
        """Get token breakdown by model for chart data."""
        summary = self.get_summary(start_date, end_date, days, show_local=show_local, show_api=show_api)
        models = []
        for model_name, data in summary.get("by_model", {}).items():
            models.append({
                "name": model_name,
                "prompt_tokens": data.get("prompt_tokens", 0),
                "completion_tokens": data.get("completion_tokens", 0),
                "total_tokens": data.get("tokens", 0)
            })
        models.sort(key=lambda x: x["total_tokens"], reverse=True)
        return {"models": models}

    def get_hourly_breakdown(self, hours: Optional[int] = 24, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, show_local: bool = True, show_api: bool = True) -> List[Dict[str, Any]]:
        """Get token usage broken down by hour for chart data."""
        if start_date:
            entries = self._get_entries_for_range(start_date, end_date)
            # Filter providers
            if not show_local or not show_api:
                entries = [
                    e for e in entries 
                    if (show_local and e.get("provider") == "local") or 
                       (show_api and e.get("provider") != "local")
                ]
            cutoff_dt = start_date
        else:
            days_to_load = (hours // 24) + 1
            cutoff_dt = datetime.utcnow() - timedelta(hours=hours)
            entries = self._get_entries_for_range(cutoff_dt)
        
        cutoff_str = cutoff_dt.isoformat() + "Z"
        buckets = defaultdict(lambda: {"tokens": 0, "calls": 0, "cost": 0.0})

        for entry in entries:
            ts = entry.get("timestamp", "")
            if ts >= cutoff_str:
                hour_key = ts[:13]
                buckets[hour_key]["tokens"] += entry.get("total_tokens", 0)
                buckets[hour_key]["calls"] += 1
                buckets[hour_key]["cost"] += entry.get("estimated_cost", 0.0)

        result = []
        for key in sorted(buckets.keys()):
            result.append({
                "hour": key,
                "tokens": buckets[key]["tokens"],
                "calls": buckets[key]["calls"],
                "cost": round(buckets[key]["cost"], 6)
            })
        return result

    def get_today_summary(self) -> Dict[str, Any]:
        """Get total tokens and estimated cost for today UTC."""
        day_logs = self._load_day_logs(datetime.utcnow())
        tokens = 0
        cost = 0.0
        for entry in day_logs:
            tokens += entry.get("total_tokens", 0)
            cost += entry.get("estimated_cost", 0.0)
        return {
            "tokens": tokens,
            "cost": round(cost, 6)
        }

    def get_today_summary(self) -> Dict[str, Any]:
        """Get total tokens and estimated cost for today UTC."""
        day_logs = self._load_day_logs(datetime.utcnow())
        tokens = 0
        cost = 0.0
        for entry in day_logs:
            tokens += entry.get("total_tokens", 0)
            cost += entry.get("estimated_cost", 0.0)
        return {
            "tokens": tokens,
            "cost": round(cost, 6)
        }
