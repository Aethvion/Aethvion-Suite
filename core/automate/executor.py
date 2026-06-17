"""
core/automate/executor.py
Workflow execution engine — graph traversal and node dispatch only.

Node implementations live in core/automate/nodes/ (one file per category).

Adding a new node type is a two-step process:
  1. Add its definition dict to _NODE_TYPES in automate_routes.py
  2. Add the handler function to the right category file in nodes/, then
     register it in nodes/__init__.py (_REGISTRY dict, one line)

This file should not need to change when new nodes are added.
"""
from __future__ import annotations

import concurrent.futures
import threading
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

    def __init__(self, workflow: dict, variables: dict | None = None,
                 trigger_id: str | None = None,
                 event_callback=None) -> None:
        self.workflow    = workflow
        self.nodes: dict[str, dict]          = {n["id"]: n for n in workflow.get("nodes", [])}
        self.connections: list[dict]         = workflow.get("connections", [])

        self._outputs: dict[str, dict[str, Any]] = {}
        self._status:  dict[str, str]            = {}
        self._errors:  dict[str, str]            = {}
        self._log:     list[dict]                = []
        # Pre-seed with injected variable values so data.variable nodes read them
        self._vars:    dict[str, Any]            = dict(variables or {})
        # Optional: run only nodes reachable from this specific trigger node id
        self._trigger_id: str | None             = trigger_id
        # Optional: callable(event: dict) fired for each node state change and log line
        self._event_callback                     = event_callback

        # Pre-build forward / reverse adjacency once — reused by _topo_sort,
        # _reachable_from_triggers, and _sibling_trigger_territory so that
        # connections are iterated once instead of four times per execute().
        self._fwd: dict[str, list[str]] = {nid: [] for nid in self.nodes}
        self._rev: dict[str, list[str]] = {nid: [] for nid in self.nodes}
        for conn in self.connections:
            src, tgt = conn.get("sourceNodeId"), conn.get("targetNodeId")
            if src in self.nodes and tgt in self.nodes:
                self._fwd[src].append(tgt)
                self._rev[tgt].append(src)

        # Pre-compute topological order alongside adjacency maps (graph is static).
        self._topo_order: list[str] | None = self._topo_sort()

    # Public entry point

    def execute(self) -> dict:
        name = self.workflow.get("name", "Workflow")
        self._info(f'Starting workflow "{name}"')

        order = self._topo_order
        if order is None:
            self._error("Cycle detected in workflow graph — cannot execute.")
            return self._build_result(fatal="Cycle detected in workflow graph.")

        if not order:
            self._warn("No nodes to execute.")
            return self._build_result()

        # Only run nodes reachable from a trigger; mark everything else skipped.
        reachable = self._reachable_from_triggers()
        run_order = [nid for nid in order if nid in reachable]

        # When running a specific trigger, compute which nodes belong to OTHER trigger
        # chains so we can skip marking them.  Emitting "skipped" for sibling-chain nodes
        # causes the frontend to wipe their canvas state and display output — we only want
        # to mark nodes that are genuinely orphan (not reachable from ANY trigger).
        if self._trigger_id:
            other_chains = self._sibling_trigger_territory()
        else:
            other_chains: set[str] = set()

        for node_id in order:
            if node_id not in reachable:
                if node_id in other_chains:
                    # Node belongs to a sibling trigger chain — leave it untouched.
                    continue
                label = self.nodes[node_id].get("label", node_id)
                self._status[node_id] = "skipped"
                self._info(f"⏭ {label} — skipped (not connected to a trigger)")
                self._emit({"type": "node_status", "node_id": node_id, "status": "skipped"})

        if not run_order:
            self._warn("No nodes are connected to a trigger — nothing to execute.")
            return self._build_result()

        completed_nodes = set()
        completed_lock  = threading.Lock()
        completed_cond  = threading.Condition(completed_lock)
        running_nodes: set[str] = set()
        pending_nodes = set(run_order)

        def run_node_task(node_id: str):
            node  = self.nodes[node_id]
            label = node.get("label", node_id)

            try:
                inputs  = self._gather_inputs(node_id)
                outputs = self._execute_node(node, inputs)
                
                with completed_lock:
                    self._outputs[node_id] = outputs or {}
                    self._status[node_id]  = "done"
                
                summary = _output_summary(outputs)
                if summary:
                    self._info(f"  ✓ {label}: {summary}")
                else:
                    self._info(f"  ✓ {label}")
                self._emit({"type": "node_status", "node_id": node_id,
                            "status": "done", "outputs": outputs or {}, "error": None})
            except Exception as exc:
                with completed_lock:
                    self._status[node_id] = "error"
                    self._errors[node_id] = str(exc)
                self._error(f"  ✗ {label}: {exc}")
                self._emit({"type": "node_status", "node_id": node_id,
                            "status": "error", "outputs": {}, "error": str(exc)})
            
            with completed_lock:
                running_nodes.remove(node_id)
                completed_nodes.add(node_id)
                completed_cond.notify_all()

        max_workers = min(16, len(run_order))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="automate-worker") as executor:
            while pending_nodes or running_nodes:
                with completed_lock:
                    # Find all pending nodes whose active dependencies are completed
                    ready_nodes = []
                    for node_id in list(pending_nodes):
                        deps = [dep for dep in self._rev[node_id] if dep in run_order]
                        if all(dep in completed_nodes for dep in deps):
                            ready_nodes.append(node_id)
                            pending_nodes.remove(node_id)
                            running_nodes.add(node_id)
                    
                    # Submit ready nodes to executor
                    for node_id in ready_nodes:
                        node  = self.nodes[node_id]
                        label = node.get("label", node_id)
                        ntype = node.get("type", "unknown")
                        self._status[node_id] = "running"
                        self._info(f"▶ {label}  [{ntype}]")
                        self._emit({"type": "node_status", "node_id": node_id, "status": "running"})
                        
                        executor.submit(run_node_task, node_id)
                    
                    # Check for deadlocks (graph cycles - should not happen due to _topo_sort check)
                    if not running_nodes and pending_nodes:
                        self._error("Cycle or dependency deadlock detected during execution.")
                        break
                    
                    # Wait for a worker thread to signal completion
                    if not ready_nodes and running_nodes:
                        completed_cond.wait()

        errors = sum(1 for s in self._status.values() if s == "error")
        if errors:
            self._warn(f"Workflow finished with {errors} error(s).")
        else:
            self._info("Workflow completed successfully.")

        return self._build_result()

    # Graph traversal

    def _reachable_from_triggers(self) -> set[str]:
        """Three-phase reachability — returns the set of node IDs to execute.

        Phase 1 — forward BFS from the active trigger seed(s):
            Finds every node that this trigger chain directly activates.

        Phase 2 — forward BFS from every INACTIVE trigger:
            Builds the "other territory" — nodes owned by sibling chains.

        Phase 3 — backward BFS from the Phase 1 set:
            Pulls in upstream data suppliers (input.text, input.file,
            data.variable, intermediate nodes, …) that feed into the active
            chain.  A candidate is skipped if it lives in "other territory",
            which prevents the walk from crossing into a sibling trigger's
            branch even when both chains share a downstream node.

        Example — Web to Summary (single trigger):
            trigger → scrape  (forward: trigger, scrape, summarize, display)
            url_input → scrape  ← backward walk adds url_input ✓
            No inactive triggers → other_territory is empty.

        Example — two triggers sharing a Summarize node:
            Run_1 → Scrape_1 → Summarize,  URL_1 → Scrape_1
            Run_2 → Scrape_2 → Summarize,  URL_2 → Scrape_2
            When Run_1 fires:
              forward         = {Run_1, Scrape_1, Summarize, Summary}
              other_territory = {Run_2, Scrape_2, Summarize, Summary}
              backward walk from Scrape_1 → adds URL_1 ✓
              backward walk from Summarize → finds Scrape_2 (in other_territory) → skipped ✓
              Result: {Run_1, Scrape_1, Summarize, Summary, URL_1} ✓
        """
        all_triggers = [nid for nid, n in self.nodes.items()
                        if n.get("type", "").startswith("trigger.")]

        def _forward_bfs(seeds: list[str]) -> set[str]:
            visited: set[str] = set(seeds)
            queue = list(seeds)
            while queue:
                nid = queue.pop(0)
                for nxt in self._fwd[nid]:
                    if nxt not in visited:
                        visited.add(nxt)
                        queue.append(nxt)
            return visited

        # Phase 1: forward from active seeds
        if self._trigger_id:
            active_seeds = [self._trigger_id] if self._trigger_id in self.nodes else []
        else:
            active_seeds = list(all_triggers)

        forward: set[str] = _forward_bfs(active_seeds)

        # Phase 2: forward from inactive triggers → "other territory"
        inactive_triggers = [t for t in all_triggers if t not in active_seeds]
        other_territory: set[str] = set()
        for t in inactive_triggers:
            other_territory |= _forward_bfs([t])

        # Phase 3: backward from forward set
        # Skip nodes that are trigger nodes OR belong to another trigger's chain.
        trigger_set = set(all_triggers)
        blocked     = trigger_set | other_territory

        reachable: set[str] = set(forward)
        queue = [nid for nid in forward if nid not in trigger_set]
        while queue:
            nid = queue.pop(0)
            for upstream in self._rev[nid]:
                if upstream not in reachable and upstream not in blocked:
                    reachable.add(upstream)
                    queue.append(upstream)

        return reachable

    def _sibling_trigger_territory(self) -> set[str]:
        """Return all nodes reachable from triggers OTHER than self._trigger_id.

        Used to avoid marking sibling-chain nodes as 'skipped' when only one
        trigger is being run — those nodes simply aren't part of this run; they
        should not have their canvas state or display output disturbed.
        """
        sibling_triggers = [
            nid for nid, n in self.nodes.items()
            if n.get("type", "").startswith("trigger.") and nid != self._trigger_id
        ]

        territory: set[str] = set()
        for t in sibling_triggers:
            queue = [t]
            while queue:
                nid = queue.pop(0)
                if nid not in territory:
                    territory.add(nid)
                    queue.extend(self._fwd.get(nid, []))
        return territory

    def _topo_sort(self) -> list[str] | None:
        """Kahn's algorithm. Returns execution order, or None if a cycle exists."""
        in_deg: dict[str, int] = {nid: 0 for nid in self.nodes}
        for nid in self.nodes:
            for tgt in self._fwd[nid]:
                in_deg[tgt] += 1

        queue  = [nid for nid, d in in_deg.items() if d == 0]
        result: list[str] = []

        while queue:
            nid = queue.pop(0)
            result.append(nid)
            for neighbour in self._fwd[nid]:
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

    # Dispatch

    def _execute_node(self, node: dict, inputs: dict[str, Any]) -> dict[str, Any]:
        from core.automate.nodes import get_handler  # noqa: PLC0415
        t       = node.get("type", "")
        handler = get_handler(t)
        if handler:
            return handler(node, inputs, self)
        self._warn(f"Unknown node type: {t!r} — passing input through")
        return {"out": inputs.get("in", "")}

    # Result builder

    def _build_result(self, fatal: str | None = None) -> dict:
        return {
            "ok":           not (bool(self._errors) or fatal is not None),
            "fatal":        fatal,
            "node_status":  self._status,
            "node_outputs": self._outputs,
            "node_errors":  self._errors,
            "log":          self._log,
        }

    # Event emission

    def _emit(self, event: dict) -> None:
        """Fire event_callback if one was supplied (non-blocking best-effort)."""
        if self._event_callback is not None:
            try:
                self._event_callback(event)
            except Exception:
                pass  # never let callback errors kill the executor

    # Logging helpers

    def _info(self, msg: str) -> None:
        entry = {"level": "info",    "msg": msg, "ts": _ts()}
        self._log.append(entry)
        self._emit({"type": "log", **entry})

    def _warn(self, msg: str) -> None:
        entry = {"level": "warning", "msg": msg, "ts": _ts()}
        self._log.append(entry)
        self._emit({"type": "log", **entry})

    def _error(self, msg: str) -> None:
        entry = {"level": "error",   "msg": msg, "ts": _ts()}
        self._log.append(entry)
        self._emit({"type": "log", **entry})


# Module-level helpers (not part of the executor class)

def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _output_summary(outputs: dict | None) -> str:
    """Return a short log preview of the most informative non-private output port.

    Pass 1: skip trivially-empty JSON ("[]", "{}") so nodes like search that
            return empty results don't hide the error/count ports.
    Pass 2: if nothing useful was found in pass 1, fall back to any non-empty value.
    """
    if not outputs:
        return ""
    from core.automate.nodes._utils import _to_str  # noqa: PLC0415
    _TRIVIAL = frozenset({"[]", "{}", "null", "None"})

    def _fmt(port: str, s: str) -> str:
        preview = s[:80].replace("\n", " ")
        return f'[{port}] "{preview}{"…" if len(s) > 80 else ""}"'

    # Pass 1 — skip trivially-empty values
    for port, val in outputs.items():
        if port.startswith("_"):
            continue
        s = _to_str(val)
        if s and s not in _TRIVIAL:
            return _fmt(port, s)

    # Pass 2 — anything non-empty (catches counts, speeds, etc.)
    for port, val in outputs.items():
        if port.startswith("_"):
            continue
        s = _to_str(val)
        if s:
            return _fmt(port, s)

    return ""
