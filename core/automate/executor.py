"""
core/automate/executor.py
═════════════════════════
Workflow execution engine — graph traversal and node dispatch only.

Node implementations live in core/automate/nodes/ (one file per category).

Adding a new node type is a two-step process:
  1. Add its definition dict to _NODE_TYPES in automate_routes.py
  2. Add the handler function to the right category file in nodes/, then
     register it in nodes/__init__.py (_REGISTRY dict, one line)

This file should not need to change when new nodes are added.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


class WorkflowExecutor:
    """
    Executes a workflow graph by topological traversal.

    Public state available to node handlers via the ``ctx`` argument:
        ctx.workflow   — the full workflow dict (id, name, nodes, connections)
        ctx._vars      — workflow-scoped variable store (dict, lives for one run)
        ctx._log       — execution log list (append via ctx._info/warn/error)

    Result dict keys:
        ok           — True if no node raised an unhandled exception
        fatal        — error message if the graph itself is broken (cycle, etc.)
        node_status  — {node_id: 'done' | 'error' | 'skipped'}
        node_outputs — {node_id: {port_name: value}}
        node_errors  — {node_id: error_message}
        log          — [{level, msg, ts}, …]
    """

    def __init__(self, workflow: dict) -> None:
        self.workflow    = workflow
        self.nodes: dict[str, dict]          = {n["id"]: n for n in workflow.get("nodes", [])}
        self.connections: list[dict]         = workflow.get("connections", [])

        self._outputs: dict[str, dict[str, Any]] = {}
        self._status:  dict[str, str]            = {}
        self._errors:  dict[str, str]            = {}
        self._log:     list[dict]                = []
        self._vars:    dict[str, Any]            = {}  # set_variable store

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

        # Only run nodes reachable from a trigger; mark everything else skipped.
        reachable = self._reachable_from_triggers()
        run_order = [nid for nid in order if nid in reachable]

        for node_id in order:
            if node_id not in reachable:
                label = self.nodes[node_id].get("label", node_id)
                self._status[node_id] = "skipped"
                self._info(f"⏭ {label} — skipped (not connected to a trigger)")

        if not run_order:
            self._warn("No nodes are connected to a trigger — nothing to execute.")
            return self._build_result()

        for node_id in run_order:
            node  = self.nodes[node_id]
            label = node.get("label", node_id)
            ntype = node.get("type", "unknown")
            self._status[node_id] = "running"
            self._info(f"▶ {label}  [{ntype}]")

            try:
                inputs  = self._gather_inputs(node_id)
                outputs = self._execute_node(node, inputs)
                self._outputs[node_id] = outputs or {}
                self._status[node_id]  = "done"
                summary = _output_summary(outputs)
                if summary:
                    self._info(f"  ✓ {label}: {summary}")
                else:
                    self._info(f"  ✓ {label}")
            except Exception as exc:
                self._status[node_id] = "error"
                self._errors[node_id] = str(exc)
                self._error(f"  ✗ {label}: {exc}")
                # Continue — other branches may still succeed

        errors = sum(1 for s in self._status.values() if s == "error")
        if errors:
            self._warn(f"Workflow finished with {errors} error(s).")
        else:
            self._info("Workflow completed successfully.")

        return self._build_result()

    # ── Graph traversal ───────────────────────────────────────────────────────

    def _reachable_from_triggers(self) -> set[str]:
        """BFS forward from every trigger.* node; returns reachable node IDs."""
        adj: dict[str, list[str]] = {nid: [] for nid in self.nodes}
        for conn in self.connections:
            src, tgt = conn.get("sourceNodeId"), conn.get("targetNodeId")
            if src in self.nodes and tgt in self.nodes:
                adj[src].append(tgt)

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
        """Kahn's algorithm. Returns execution order, or None if a cycle exists."""
        in_deg: dict[str, int]       = {nid: 0 for nid in self.nodes}
        adj:    dict[str, list[str]] = {nid: [] for nid in self.nodes}

        for conn in self.connections:
            src, tgt = conn.get("sourceNodeId"), conn.get("targetNodeId")
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
        """Collect all upstream port values wired into this node's inputs."""
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

    # ── Dispatch ──────────────────────────────────────────────────────────────

    def _execute_node(self, node: dict, inputs: dict[str, Any]) -> dict[str, Any]:
        from core.automate.nodes import get_handler  # noqa: PLC0415
        t       = node.get("type", "")
        handler = get_handler(t)
        if handler:
            return handler(node, inputs, self)
        self._warn(f"Unknown node type: {t!r} — passing input through")
        return {"out": inputs.get("in", "")}

    # ── Result builder ────────────────────────────────────────────────────────

    def _build_result(self, fatal: str | None = None) -> dict:
        return {
            "ok":           not (bool(self._errors) or fatal is not None),
            "fatal":        fatal,
            "node_status":  self._status,
            "node_outputs": self._outputs,
            "node_errors":  self._errors,
            "log":          self._log,
        }

    # ── Logging helpers ───────────────────────────────────────────────────────

    def _info(self, msg: str) -> None:
        self._log.append({"level": "info",    "msg": msg, "ts": _ts()})

    def _warn(self, msg: str) -> None:
        self._log.append({"level": "warning", "msg": msg, "ts": _ts()})

    def _error(self, msg: str) -> None:
        self._log.append({"level": "error",   "msg": msg, "ts": _ts()})


# ── Module-level helpers (not part of the executor class) ─────────────────────

def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _output_summary(outputs: dict | None) -> str:
    """Return a short log preview of the first non-empty output port."""
    if not outputs:
        return ""
    from core.automate.nodes._utils import _to_str  # noqa: PLC0415
    for port, val in outputs.items():
        if port.startswith("_"):
            continue
        s = _to_str(val)
        if s:
            preview = s[:80].replace("\n", " ")
            return f'[{port}] "{preview}{"…" if len(s) > 80 else ""}"'
    return ""
