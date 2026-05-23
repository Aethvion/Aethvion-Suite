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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Persistent memory store shared across all workflow runs
_MEMORY_PATH = Path(__file__).parent.parent.parent / "data" / "automate" / "memory.json"

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
            # Fire the chain without passing data (consistent with trigger.schedule's
            # "trigger" port — returning None means _gather_inputs skips it).
            return {"trigger": None}

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

        if t == "action.file_read":
            return self._exec_file_read(p, inputs)

        if t == "action.file_write":
            return self._exec_file_write(p, inputs)

        if t == "action.notify":
            return self._exec_notify(p, inputs)

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

        if t == "logic.try_catch":
            in_val     = inputs.get("in", "")
            error_val  = str(inputs.get("error_in", "") or "").strip()
            filter_str = str(p.get("error_contains", "")).strip()
            is_error   = bool(error_val)
            if filter_str and is_error:
                is_error = filter_str.lower() in error_val.lower()
            if is_error:
                return {"try": None, "catch": error_val, "always": error_val}
            return {"try": in_val, "catch": None, "always": in_val}

        if t == "logic.switch":
            in_val = inputs.get("in", "")
            key    = str(p.get("switch_on", "")).strip()
            if key:
                try:
                    obj = json.loads(_to_str(in_val)) if isinstance(in_val, str) else in_val
                    compare_val = str(obj.get(key, ""))
                except Exception:
                    compare_val = _to_str(in_val)
            else:
                compare_val = _to_str(in_val)
            num     = max(1, min(4, int(p.get("num_cases", 2))))
            result  = {f"case_{i}": None for i in range(1, 5)}
            result["default"] = None
            matched = False
            for i in range(1, num + 1):
                if not matched and compare_val == str(p.get(f"case_{i}", "")):
                    result[f"case_{i}"] = in_val
                    matched = True
            if not matched:
                result["default"] = in_val
            return result

        if t == "logic.merge":
            mode = str(p.get("mode", "first"))
            if mode == "all":
                collected = {port: inputs[port] for port in ("a", "b", "c", "d") if inputs.get(port) is not None}
                return {"out": collected, "source": "all"}
            for port in ("a", "b", "c", "d"):
                val = inputs.get(port)
                if val is not None:
                    return {"out": val, "source": port}
            return {"out": None, "source": ""}

        # ── Memory ────────────────────────────────────────────────────────
        if t == "memory.store":
            return self._exec_memory_store(p, inputs)

        if t == "memory.retrieve":
            return self._exec_memory_retrieve(p, inputs)

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

        # ── Sprint 1: Data nodes ──────────────────────────────────────────────

        if t == "data.template":
            import re as _re  # noqa: PLC0415
            template = str(p.get("template", ""))
            in_val   = inputs.get("in", "")
            variables: dict = {}
            # Expand JSON input object into variables
            if isinstance(in_val, dict):
                variables.update({str(k): _to_str(v) for k, v in in_val.items()})
            else:
                raw_in = _to_str(in_val)
                try:
                    obj = json.loads(raw_in)
                    if isinstance(obj, dict):
                        variables.update({str(k): _to_str(v) for k, v in obj.items()})
                except Exception:
                    pass
                variables["input"] = raw_in
            # Named port overrides
            for _port in ("var_a", "var_b", "var_c"):
                _val = inputs.get(_port)
                if _val is not None:
                    variables[_port] = _to_str(_val)

            def _tmpl_replacer(m):
                parts   = m.group(1).split("|", 1)
                key     = parts[0].strip()
                default = parts[1] if len(parts) > 1 else ""
                return variables.get(key, default)

            result     = _re.sub(r"\{\{([^}]+)\}\}", _tmpl_replacer, template)
            unresolved = _re.findall(r"\{\{[^}]+\}\}", result)
            error      = f"Unresolved: {unresolved}" if unresolved else ""
            return {"out": result, "error": error}

        if t == "data.extract_json":
            in_val = inputs.get("in", "")
            if isinstance(in_val, str):
                try:
                    obj = json.loads(in_val)
                except Exception as exc:
                    return {"out": p.get("default", ""), "error": f"JSON parse error: {exc}"}
            else:
                obj = in_val
            key_path = str(p.get("key", "")).strip()
            if not key_path:
                return {"out": obj, "error": ""}
            try:
                current = obj
                for part in key_path.split("."):
                    if isinstance(current, list):
                        current = current[int(part)]
                    elif isinstance(current, dict):
                        current = current[part]
                    else:
                        raise KeyError(part)
                mode = str(p.get("output_as", "auto"))
                if mode == "string":
                    out = _to_str(current)
                elif mode == "json":
                    out = json.dumps(current, ensure_ascii=False)
                else:
                    out = current
                return {"out": out, "error": ""}
            except (KeyError, IndexError, TypeError) as exc:
                default = p.get("default", "")
                if default != "":
                    return {"out": default, "error": ""}
                return {"out": "", "error": f"Key not found: {key_path} ({exc})"}

        if t == "data.type_convert":
            val = inputs.get("in", "")
            to  = str(p.get("to", "string"))
            try:
                if to == "string":
                    out = json.dumps(val, ensure_ascii=False) if isinstance(val, (dict, list)) else str(val)
                elif to == "integer":
                    out = int(float(str(val).strip()))
                elif to == "float":
                    out = float(str(val).strip())
                elif to == "boolean":
                    s          = str(val).strip().lower()
                    true_vals  = [v.strip().lower() for v in str(p.get("true_values",  "true,yes,1,on")).split(",")]
                    false_vals = [v.strip().lower() for v in str(p.get("false_values", "false,no,0,off")).split(",")]
                    if s in true_vals:
                        out = True
                    elif s in false_vals:
                        out = False
                    else:
                        out = bool(val)
                elif to == "json":
                    out = json.loads(val) if isinstance(val, str) else val
                else:
                    out = val
                return {"out": out, "error": ""}
            except Exception as exc:
                return {"out": val, "error": f"Conversion to {to} failed: {exc}"}

        if t == "data.split_text":
            text         = _to_str(inputs.get("in", ""))
            mode         = str(p.get("mode", "delimiter"))
            trim         = bool(p.get("trim", True))
            remove_empty = bool(p.get("remove_empty", True))
            if mode == "lines":
                parts = text.splitlines()
            elif mode == "words":
                parts = text.split()
            elif mode == "chunks":
                size  = max(1, int(p.get("chunk_size", 500) or 500))
                parts = [text[i:i + size] for i in range(0, max(len(text), 1), size)]
            else:  # delimiter
                parts = text.split(str(p.get("delimiter", ",")))
            if trim and mode != "chunks":
                parts = [s.strip() for s in parts]
            if remove_empty:
                parts = [s for s in parts if s]
            first = parts[0]  if parts else ""
            last  = parts[-1] if parts else ""
            return {"out": json.dumps(parts, ensure_ascii=False), "first": first, "last": last, "count": len(parts)}

        if t == "data.regex":
            import re as _re  # noqa: PLC0415
            text     = _to_str(inputs.get("in", ""))
            pattern  = _to_str(inputs.get("pattern") or p.get("pattern", ""))
            mode     = str(p.get("mode", "extract"))
            repl     = str(p.get("replacement", ""))
            flag_str = str(p.get("flags", ""))
            flags    = 0
            if "i" in flag_str: flags |= _re.IGNORECASE
            if "m" in flag_str: flags |= _re.MULTILINE
            if "s" in flag_str: flags |= _re.DOTALL
            try:
                compiled = _re.compile(pattern, flags)
            except _re.error as exc:
                return {"out": "", "matches": "[]", "matched": "false", "error": str(exc)}
            if mode == "match":
                found = bool(compiled.search(text))
                return {"out": str(found).lower(), "matches": "[]",
                        "matched": str(found).lower(), "error": ""}
            if mode == "replace":
                result  = compiled.sub(repl, text)
                matched = str(bool(compiled.search(text))).lower()
                return {"out": result, "matches": "[]", "matched": matched, "error": ""}
            # extract
            raw_matches = compiled.findall(text)
            # findall returns tuples when multiple groups — flatten each to a string
            all_m = [(" ".join(m) if isinstance(m, tuple) else str(m)) for m in raw_matches]
            matched = bool(all_m)
            if p.get("all_matches", False):
                out = json.dumps(all_m, ensure_ascii=False)
            else:
                out = all_m[0] if all_m else ""
            return {"out": out, "matches": json.dumps(all_m, ensure_ascii=False),
                    "matched": str(matched).lower(), "error": ""}

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

    def _exec_file_read(self, p: dict, inputs: dict[str, Any]) -> dict[str, Any]:
        import os       # noqa: PLC0415
        import base64   # noqa: PLC0415

        file_path = str(inputs.get("path") or p.get("path", "")).strip()
        if not file_path:
            return {"out": "", "path": "", "size": 0, "error": "No file path configured"}

        encoding  = str(p.get("encoding", "utf-8"))
        strip     = bool(p.get("strip", False))
        max_bytes = int(p.get("max_bytes", 0) or 0)

        try:
            size = os.path.getsize(file_path)
            if max_bytes and size > max_bytes:
                return {"out": "", "path": file_path, "size": size,
                        "error": f"File too large: {size} bytes (max {max_bytes})"}
            if encoding == "binary":
                with open(file_path, "rb") as fh:
                    content = base64.b64encode(fh.read()).decode("ascii")
            else:
                with open(file_path, "r", encoding=encoding, errors="replace") as fh:
                    content = fh.read()
            if strip:
                content = content.strip()
            return {"out": content, "path": file_path, "size": size, "error": ""}
        except Exception as exc:
            return {"out": "", "path": file_path, "size": 0, "error": str(exc)}

    def _exec_file_write(self, p: dict, inputs: dict[str, Any]) -> dict[str, Any]:
        import os  # noqa: PLC0415

        file_path   = str(inputs.get("path") or p.get("path", "")).strip()
        content     = _to_str(inputs.get("in", ""))
        mode        = str(p.get("mode", "overwrite"))
        encoding    = str(p.get("encoding", "utf-8"))
        newline     = bool(p.get("newline", True))
        create_dirs = bool(p.get("create_dirs", True))

        if not file_path:
            return {"out": content, "path": "", "error": "No file path configured"}

        write_content = content
        if newline and not write_content.endswith("\n"):
            write_content += "\n"

        try:
            if create_dirs:
                os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)

            if mode == "overwrite":
                with open(file_path, "w", encoding=encoding) as fh:
                    fh.write(write_content)
            elif mode == "append":
                with open(file_path, "a", encoding=encoding) as fh:
                    fh.write(write_content)
            elif mode == "prepend":
                existing = ""
                if os.path.exists(file_path):
                    with open(file_path, "r", encoding=encoding) as fh:
                        existing = fh.read()
                with open(file_path, "w", encoding=encoding) as fh:
                    fh.write(write_content + existing)

            return {"out": content, "path": file_path, "error": ""}
        except Exception as exc:
            return {"out": content, "path": file_path, "error": str(exc)}

    def _exec_notify(self, p: dict, inputs: dict[str, Any]) -> dict[str, Any]:
        import subprocess  # noqa: PLC0415
        import sys         # noqa: PLC0415

        title   = _to_str(inputs.get("title")   or p.get("title",   "Aethvion"))
        message = _to_str(inputs.get("message") or p.get("message", "Workflow completed."))
        in_val  = _to_str(inputs.get("in", ""))
        message = message.replace("{{input}}", in_val)

        # Sanitise for shell embedding — strip quotes to avoid injection
        title_safe   = title.replace('"', "'")
        message_safe = message.replace('"', "'")

        try:
            if sys.platform == "win32":
                try:
                    from winotify import Notification  # noqa: PLC0415
                    toast = Notification(app_id="Aethvion Suite", title=title_safe, msg=message_safe)
                    toast.show()
                except ImportError:
                    # PowerShell balloon toast — hidden window, fire-and-forget (no blocking).
                    # ShowBalloonTip timeout is 5 s; Sleep 6 keeps the icon alive until it
                    # self-dismisses, then hides. No CMD/PS window ever appears.
                    ps_cmd = (
                        "Add-Type -AssemblyName System.Windows.Forms; "
                        "$n = New-Object System.Windows.Forms.NotifyIcon; "
                        "$n.Icon = [System.Drawing.SystemIcons]::Information; "
                        "$n.Visible = $true; "
                        f'$n.ShowBalloonTip(5000, "{title_safe}", "{message_safe}", '
                        "[System.Windows.Forms.ToolTipIcon]::Info); "
                        "Start-Sleep 6; $n.Visible = $false"
                    )
                    subprocess.Popen(  # noqa: S603
                        [
                            "powershell",
                            "-NoProfile", "-NonInteractive",
                            "-WindowStyle", "Hidden",
                            "-Command", ps_cmd,
                        ],
                        creationflags=0x08000000,  # CREATE_NO_WINDOW
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    # Popen is fire-and-forget — execution continues immediately.

            elif sys.platform == "darwin":
                subprocess.Popen(  # noqa: S603
                    ["osascript", "-e",
                     f'display notification "{message_safe}" with title "{title_safe}"'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                subprocess.Popen(  # noqa: S603
                    ["notify-send", title_safe, message_safe],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            return {"out": in_val, "error": ""}
        except Exception as exc:
            return {"out": in_val, "error": str(exc)}

    def _exec_memory_store(self, p: dict, inputs: dict[str, Any]) -> dict[str, Any]:
        key     = _to_str(inputs.get("key") or p.get("key", "")).strip()
        scope   = str(p.get("scope", "global"))
        ttl_hrs = float(p.get("ttl", 0) or 0)
        in_val  = inputs.get("in", "")

        if not key:
            return {"out": in_val, "error": "No storage key configured"}

        if scope == "workflow":
            key = f"wf:{self.workflow.get('id', 'unknown')}:{key}"

        try:
            store: dict = json.loads(_MEMORY_PATH.read_text(encoding="utf-8")) if _MEMORY_PATH.exists() else {}
        except Exception:
            store = {}

        entry: dict = {"value": in_val}
        if ttl_hrs > 0:
            entry["expires"] = (datetime.now() + timedelta(hours=ttl_hrs)).isoformat()

        store[key] = entry

        try:
            _MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            _MEMORY_PATH.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")
            return {"out": in_val, "error": ""}
        except Exception as exc:
            return {"out": in_val, "error": str(exc)}

    def _exec_memory_retrieve(self, p: dict, inputs: dict[str, Any]) -> dict[str, Any]:
        key     = str(p.get("key", "")).strip()
        scope   = str(p.get("scope", "global"))
        default = p.get("default", "")

        if not key:
            return {"out": default, "found": "false", "error": "No storage key configured"}

        if scope == "workflow":
            key = f"wf:{self.workflow.get('id', 'unknown')}:{key}"

        try:
            store: dict = json.loads(_MEMORY_PATH.read_text(encoding="utf-8")) if _MEMORY_PATH.exists() else {}
        except Exception as exc:
            return {"out": default, "found": "false", "error": str(exc)}

        entry = store.get(key)
        if entry is None:
            return {"out": default, "found": "false", "error": ""}

        expires = entry.get("expires")
        if expires:
            try:
                if datetime.now() > datetime.fromisoformat(expires):
                    return {"out": default, "found": "false", "error": ""}
            except Exception:
                pass

        return {"out": entry.get("value", default), "found": "true", "error": ""}

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
