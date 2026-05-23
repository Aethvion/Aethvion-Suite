"""
core/automate/executor.py
═════════════════════════
Workflow execution engine.

Traverses the node graph in topological order, executes each node,
and passes outputs along connections to downstream inputs.

Isolated from other Aethvion modules — only ProviderManager is imported
lazily for AI nodes, and only its call_with_failover() utility is used.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from typing import Any

# ── Lazy ProviderManager ──────────────────────────────────────────────────────
_pm = None

def _get_pm():
    global _pm
    if _pm is None:
        from core.providers.provider_manager import ProviderManager  # noqa: PLC0415
        _pm = ProviderManager()
    return _pm


# ── Utilities ─────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _to_str(val: Any) -> str:
    if isinstance(val, str):
        return val
    if val is None:
        return ""
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    return str(val)


def _safe_eval(expr: str, local_vars: dict) -> Any:
    """Evaluate a simple expression in a restricted namespace."""
    safe_builtins = {"len": len, "str": str, "int": int, "float": float,
                     "bool": bool, "list": list, "dict": dict, "True": True, "False": False}
    return eval(expr, {"__builtins__": safe_builtins}, local_vars)  # noqa: S307


# ── Executor ──────────────────────────────────────────────────────────────────

class WorkflowExecutor:
    """
    Executes a workflow graph by topological traversal.

    Results:
        ok           — True if no node raised an error
        node_status  — {node_id: 'done'|'error'|'skipped'}
        node_outputs — {node_id: {port: value}}
        node_errors  — {node_id: error_message}
        log          — [{level, msg, ts}]
    """

    def __init__(self, workflow: dict) -> None:
        self.workflow    = workflow
        self.nodes: dict[str, dict] = {n["id"]: n for n in workflow.get("nodes", [])}
        self.connections: list[dict] = workflow.get("connections", [])

        self._outputs: dict[str, dict[str, Any]]  = {}
        self._status:  dict[str, str]             = {}
        self._errors:  dict[str, str]             = {}
        self._log:     list[dict]                 = []
        self._vars:    dict[str, Any]             = {}  # workflow-scoped variable store

    # ── Public entry point ────────────────────────────────────────────────────

    def execute(self) -> dict:
        name = self.workflow.get("name", "Workflow")
        self._info(f'Starting workflow "{name}"')

        order = self._topo_sort()
        if order is None:
            self._error("Cycle detected in workflow graph — cannot execute.")
            return self._build_result(fatal="Cycle detected in workflow graph.")

        if not order:
            self._warn("No nodes to execute.")
            return self._build_result()

        # Only execute nodes that are reachable from a trigger node.
        # Everything else is marked "skipped" so the UI can dim it.
        reachable  = self._reachable_from_triggers()
        run_order  = [nid for nid in order if nid in reachable]

        for node_id in order:
            if node_id not in reachable:
                label = self.nodes[node_id].get("label", node_id)
                self._status[node_id] = "skipped"
                self._info(f"⏭ {label} — skipped (not connected to a trigger)")

        if not run_order:
            self._warn("No nodes are connected to a trigger — nothing to execute.")
            return self._build_result()

        for node_id in run_order:
            node = self.nodes[node_id]
            label = node.get("label", node_id)
            ntype = node.get("type", "unknown")
            self._status[node_id] = "running"
            self._info(f"▶ {label}  [{ntype}]")

            try:
                inputs  = self._gather_inputs(node_id)
                outputs = self._execute_node(node, inputs)
                self._outputs[node_id] = outputs or {}
                self._status[node_id]  = "done"
                # Summarise output for the log
                summary = self._output_summary(outputs)
                if summary:
                    self._info(f"  ✓ {label}: {summary}")
                else:
                    self._info(f"  ✓ {label}")
            except Exception as exc:
                self._status[node_id] = "error"
                self._errors[node_id] = str(exc)
                self._error(f"  ✗ {label}: {exc}")
                # Continue — other branches may still run

        errors = sum(1 for s in self._status.values() if s == "error")
        if errors:
            self._warn(f"Workflow finished with {errors} error(s).")
        else:
            self._info("Workflow completed successfully.")

        return self._build_result()

    # ── Graph traversal ───────────────────────────────────────────────────────

    def _reachable_from_triggers(self) -> set[str]:
        """
        BFS forward from every trigger.* node.
        Returns the set of node IDs that should actually be executed.
        Trigger nodes themselves are always included in the result.
        """
        # Build forward adjacency: src → [tgt, …]
        adj: dict[str, list[str]] = {nid: [] for nid in self.nodes}
        for conn in self.connections:
            src = conn.get("sourceNodeId")
            tgt = conn.get("targetNodeId")
            if src in self.nodes and tgt in self.nodes:
                adj[src].append(tgt)

        # Seed the BFS with every trigger node
        seeds   = [nid for nid, n in self.nodes.items()
                   if n.get("type", "").startswith("trigger.")]
        visited = set(seeds)
        queue   = list(seeds)

        while queue:
            nid = queue.pop(0)
            for neighbour in adj[nid]:
                if neighbour not in visited:
                    visited.add(neighbour)
                    queue.append(neighbour)

        return visited

    def _topo_sort(self) -> list[str] | None:
        """Kahn's algorithm. Returns ordered node-id list, or None if a cycle exists."""
        in_deg: dict[str, int]        = {nid: 0 for nid in self.nodes}
        adj:    dict[str, list[str]]  = {nid: [] for nid in self.nodes}

        for conn in self.connections:
            src = conn.get("sourceNodeId")
            tgt = conn.get("targetNodeId")
            if src in self.nodes and tgt in self.nodes:
                adj[src].append(tgt)
                in_deg[tgt] += 1

        queue  = [nid for nid, d in in_deg.items() if d == 0]
        result: list[str] = []

        while queue:
            nid = queue.pop(0)
            result.append(nid)
            for neighbour in adj[nid]:
                in_deg[neighbour] -= 1
                if in_deg[neighbour] == 0:
                    queue.append(neighbour)

        return result if len(result) == len(self.nodes) else None

    def _gather_inputs(self, node_id: str) -> dict[str, Any]:
        """Collect upstream outputs wired into this node's input ports."""
        inputs: dict[str, Any] = {}
        for conn in self.connections:
            if conn.get("targetNodeId") != node_id:
                continue
            src_id   = conn.get("sourceNodeId", "")
            src_port = conn.get("sourcePort", "")
            tgt_port = conn.get("targetPort", "")
            if src_id in self._outputs:
                val = self._outputs[src_id].get(src_port)
                if val is not None:
                    inputs[tgt_port] = val
        return inputs

    # ── Node dispatch ─────────────────────────────────────────────────────────

    def _execute_node(self, node: dict, inputs: dict[str, Any]) -> dict[str, Any]:
        t = node.get("type", "")
        p = node.get("properties", {})

        # ── Triggers ──────────────────────────────────────────────────────
        if t == "trigger.manual":
            return {"out": inputs.get("in", "")}

        if t == "trigger.schedule":
            # "trigger" fires the chain (no payload); "data" carries the timestamp
            return {"trigger": None, "data": datetime.now().isoformat()}

        if t == "trigger.webhook":
            body = inputs.get("body", {})
            return {"out": body, "body": body}

        # ── Inputs ────────────────────────────────────────────────────────
        if t == "input.text":
            return {"out": str(p.get("value", ""))}

        if t == "input.number":
            try:
                return {"out": float(p.get("value", 0))}
            except (ValueError, TypeError):
                return {"out": 0.0}

        # ── AI ────────────────────────────────────────────────────────────
        if t in ("ai.google", "ai.any"):
            return self._exec_ai(p, inputs)

        # ── Actions ───────────────────────────────────────────────────────
        if t == "action.http":
            return self._exec_http(p, inputs)

        if t == "action.log":
            in_val = _to_str(inputs.get("in", ""))
            msg    = str(p.get("message", "{{input}}")).replace("{{input}}", in_val)
            level  = str(p.get("level", "info")).lower()
            self._log.append({"level": level, "msg": f"[LOG] {msg}", "ts": _now()})
            return {"out": in_val}

        if t == "action.run_script":
            return self._exec_script(p, inputs)

        # ── Logic ─────────────────────────────────────────────────────────
        if t == "logic.if":
            in_val    = inputs.get("in", "")
            condition = str(p.get("condition", "")).strip()
            try:
                result = bool(_safe_eval(condition, {"value": in_val, "input": in_val}))
            except Exception:
                result = bool(in_val)
            return {"true": in_val if result else None, "false": in_val if not result else None}

        if t == "logic.delay":
            ms = float(p.get("duration", 1000))
            time.sleep(min(ms / 1000.0, 10.0))  # cap at 10 s
            return {"out": inputs.get("in", "")}

        if t == "logic.loop":
            items = inputs.get("in", [])
            if not isinstance(items, list):
                try:
                    items = json.loads(_to_str(items))
                except Exception:
                    items = [items]
            first = items[0] if items else None
            return {"item": first, "done": items}

        # ── Data ──────────────────────────────────────────────────────────
        if t == "data.format_text":
            template = str(p.get("template", "{{input}}"))
            in_val   = _to_str(inputs.get("in", ""))
            out      = template.replace("{{input}}", in_val)
            for k, v in self._vars.items():
                out = out.replace("{{" + k + "}}", _to_str(v))
            return {"out": out}

        if t == "data.parse_json":
            raw = _to_str(inputs.get("in", ""))
            try:
                return {"out": json.loads(raw), "error": ""}
            except json.JSONDecodeError as exc:
                return {"out": None, "error": str(exc)}

        if t == "data.set_variable":
            name  = str(p.get("name", "var")).strip() or "var"
            value = inputs.get("in", "")
            self._vars[name] = value
            return {"out": value}

        if t == "data.filter":
            items = inputs.get("in", [])
            if not isinstance(items, list):
                try:
                    items = json.loads(_to_str(items))
                except Exception:
                    items = [items]
            expr   = str(p.get("expression", "")).strip()
            if not expr:
                return {"match": items, "rest": []}
            match, rest = [], []
            for item in items:
                try:
                    ok = bool(_safe_eval(expr, {"item": item}))
                except Exception:
                    ok = False
                (match if ok else rest).append(item)
            return {"match": match, "rest": rest}

        if t == "transform.combine":
            a   = _to_str(inputs.get("a", ""))
            b   = _to_str(inputs.get("b", ""))
            sep = str(p.get("separator", "\\n")).replace("\\n", "\n").replace("\\t", "\t")
            return {"out": a + sep + b}

        # ── Outputs ───────────────────────────────────────────────────────
        if t == "output.display":
            val = inputs.get("in", "")
            return {"_display": val}

        # ── Unknown — pass-through ─────────────────────────────────────────
        self._warn(f"Unknown node type: {t} — passing input through")
        return {"out": inputs.get("in", "")}

    # ── Node implementations ──────────────────────────────────────────────────

    def _exec_ai(self, p: dict, inputs: dict[str, Any]) -> dict[str, Any]:
        # Input ports take priority over node property values when connected.
        # An empty/missing port value falls through to the property default.
        def _inp(port: str, prop_key: str, default: str = "") -> str:
            wired = _to_str(inputs.get(port, "")).strip()
            return wired if wired else str(p.get(prop_key, default)).strip()

        model_id      = _inp("model",         "model")
        system_prompt = _inp("system_prompt", "system_prompt", "") or None
        prefix        = _inp("prompt_prefix", "prompt_prefix")
        suffix        = _inp("prompt_suffix", "prompt_suffix")
        in_val        = _to_str(inputs.get("in", ""))

        # Temperature: port overrides property, must be a float
        _temp_raw = inputs.get("temperature")
        try:
            temperature = float(_temp_raw) if _temp_raw not in (None, "") else float(p.get("temperature", 0.7))
        except (ValueError, TypeError):
            temperature = float(p.get("temperature", 0.7))

        if not model_id:
            raise ValueError("No model selected — open node properties and pick a model.")

        parts  = [x for x in [prefix, in_val, suffix] if x]
        prompt = "\n\n".join(parts) if parts else "(no input)"

        pm   = _get_pm()
        resp = pm.call_with_failover(
            prompt=prompt,
            trace_id=f"automate-exec-{uuid.uuid4().hex[:8]}",
            system_prompt=system_prompt,
            temperature=temperature,
            model=model_id,
            request_type="generation",
            source="automate-execution",
        )
        if not resp.success:
            return {"out": "", "error": resp.error or "AI call failed"}
        return {"out": resp.content, "error": ""}

    def _exec_http(self, p: dict, inputs: dict[str, Any]) -> dict[str, Any]:
        import urllib.request  # noqa: PLC0415

        url    = str(p.get("url", "")).strip()
        method = str(p.get("method", "GET")).upper()
        body   = _to_str(inputs.get("in", p.get("body", "")))
        try:
            headers = json.loads(str(p.get("headers", "{}")))
        except json.JSONDecodeError:
            headers = {}

        if not url:
            raise ValueError("HTTP node: no URL configured.")

        req = urllib.request.Request(url, method=method)
        for k, v in (headers or {}).items():
            req.add_header(str(k), str(v))

        if body and method in ("POST", "PUT", "PATCH"):
            req.data = body.encode("utf-8")
            if "Content-Type" not in headers:
                req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read().decode("utf-8", errors="replace")
                return {"out": raw, "error": ""}
        except Exception as exc:
            return {"out": "", "error": str(exc)}

    def _exec_script(self, p: dict, inputs: dict[str, Any]) -> dict[str, Any]:
        script     = str(p.get("script", ""))
        input_data = inputs.get("in", "")
        local_ns   = {"input_data": input_data, "result": None}
        try:
            exec(compile(script, "<automate-script>", "exec"), {}, local_ns)  # noqa: S102
            return {"out": local_ns.get("result", input_data), "error": ""}
        except Exception as exc:
            return {"out": "", "error": str(exc)}

    # ── Result builder ────────────────────────────────────────────────────────

    def _build_result(self, fatal: str | None = None) -> dict:
        has_errors = bool(self._errors) or fatal is not None
        return {
            "ok":           not has_errors,
            "fatal":        fatal,
            "node_status":  self._status,
            "node_outputs": self._outputs,
            "node_errors":  self._errors,
            "log":          self._log,
        }

    @staticmethod
    def _output_summary(outputs: dict | None) -> str:
        if not outputs:
            return ""
        # Show first non-empty string output, truncated
        for port, val in (outputs or {}).items():
            if port.startswith("_"):
                continue
            s = _to_str(val)
            if s:
                preview = s[:80].replace("\n", " ")
                return f'[{port}] "{preview}{"…" if len(s) > 80 else ""}"'
        return ""

    # ── Logging helpers ───────────────────────────────────────────────────────

    def _info(self, msg: str) -> None:
        self._log.append({"level": "info", "msg": msg, "ts": _now()})

    def _warn(self, msg: str) -> None:
        self._log.append({"level": "warning", "msg": msg, "ts": _now()})

    def _error(self, msg: str) -> None:
        self._log.append({"level": "error", "msg": msg, "ts": _now()})
