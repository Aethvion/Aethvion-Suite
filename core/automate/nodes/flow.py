"""
core/automate/nodes/flow.py
Sub-workflows: the way to loop, retry and reuse pipelines without cycles in the graph.

    flow.input         named input of a workflow (any type — text, number, asset…)
    flow.return        named output of a workflow
    flow.subworkflow   run another workflow once
    flow.for_each      run another workflow once per list item (optionally in parallel)
    flow.retry_until   run another workflow until it reports success (generate → verify → retry)

A workflow becomes reusable by giving it flow.input / global.* nodes for its parameters and
flow.return nodes for its results.  It needs no trigger when called as a sub-workflow.
"""
from __future__ import annotations

import concurrent.futures
import json
from typing import Any

from ._utils import _to_str
from .models import fail, parse_params


# flow.input / flow.return

def flow_input(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p    = node.get("properties", {})
    name = str(p.get("name", "input")).strip() or "input"
    if name in ctx._vars and ctx._vars[name] not in (None, ""):
        val = ctx._vars[name]
    else:
        default = p.get("default", "")
        val = default if default not in (None, "") else None
    ctx._vars[name] = val
    return {"out": val}


def flow_return(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p    = node.get("properties", {})
    name = str(p.get("name", "result")).strip() or "result"
    val  = inputs.get("in")
    ctx._returns[name] = val
    return {"out": val}


# Child-run plumbing

def _load_workflow(key: str) -> dict:
    from core.automate.automate_routes import _DATA_DIR, _wf_path  # noqa: PLC0415

    key = (key or "").strip()
    if not key:
        raise ValueError("No workflow selected — open the node's properties and pick one.")
    p = _wf_path(key)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    if _DATA_DIR.exists():
        for f in _DATA_DIR.glob("*.json"):
            try:
                wf = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if str(wf.get("name", "")).strip().lower() == key.lower():
                return wf
    raise ValueError(f"Workflow '{key}' not found.")


def _run_child(ctx, wf: dict, variables: dict, tag: str = "") -> dict:
    from core.automate.executor import WorkflowExecutor, MAX_SUBWORKFLOW_DEPTH  # noqa: PLC0415

    if ctx.depth + 1 > MAX_SUBWORKFLOW_DEPTH:
        raise RuntimeError(f"Sub-workflows are nested more than {MAX_SUBWORKFLOW_DEPTH} levels deep "
                           "(a workflow may be calling itself).")
    prefix = "    │ " + (f"[{tag}] " if tag else "")

    def _forward(event: dict) -> None:
        # Only log lines travel up — node ids belong to the child graph, not this canvas.
        if event.get("type") == "log":
            ctx._emit({**event, "msg": prefix + str(event.get("msg", ""))})
            ctx._log.append({"level": event.get("level", "info"),
                             "msg": prefix + str(event.get("msg", "")), "ts": event.get("ts", "")})

    child = WorkflowExecutor(wf, variables=variables, event_callback=_forward, parent=ctx)
    return child.execute()


def _child_error(result: dict) -> str:
    if result.get("fatal"):
        return str(result["fatal"])
    errs = result.get("node_errors") or {}
    return "; ".join(f"{k}: {v}" for k, v in list(errs.items())[:3])


def _primary(returns: dict, name: str = "result") -> Any:
    if name in returns:
        return returns[name]
    return next(iter(returns.values()), None) if returns else None


def _variables(node: dict, inputs: dict) -> dict:
    p = node.get("properties", {})
    return parse_params(p.get("variables", ""), inputs.get("variables"))


# flow.subworkflow

def flow_subworkflow(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    ports = ("out", "returns")
    p  = node.get("properties", {})
    wf = _load_workflow(_to_str(inputs.get("workflow") or p.get("workflow", "")))
    variables = _variables(node, inputs)
    if inputs.get("in") is not None:
        variables[str(p.get("input_name", "input")).strip() or "input"] = inputs["in"]

    result = _run_child(ctx, wf, variables)
    if not result.get("ok"):
        return fail(ctx, node, f"Sub-workflow '{wf.get('name')}' failed: {_child_error(result) or 'unknown error'}", ports)
    returns = result.get("returns") or {}
    return {"out": _primary(returns), "returns": returns, "error": ""}


# flow.for_each

def flow_for_each(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    ports = ("results", "all", "count")
    p  = node.get("properties", {})
    wf = _load_workflow(_to_str(inputs.get("workflow") or p.get("workflow", "")))

    items = inputs.get("items")
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except ValueError:
            items = [ln.strip() for ln in items.splitlines() if ln.strip()]
    if items is None:
        items = []
    if not isinstance(items, list):
        items = [items]
    try:
        max_items = max(1, int(p.get("max_items", 100) or 100))
    except (TypeError, ValueError):
        max_items = 100
    if len(items) > max_items:
        ctx._warn(f"    For Each: {len(items)} items given, running the first {max_items} (Max Items).")
        items = items[:max_items]

    base      = _variables(node, inputs)
    item_name = str(p.get("item_name", "item")).strip() or "item"
    try:
        parallel = max(1, min(8, int(p.get("parallel", 1) or 1)))
    except (TypeError, ValueError):
        parallel = 1
    stop_on_error = bool(p.get("stop_on_error", False))

    def _one(i: int, item: Any) -> dict:
        if ctx.cancelled:
            return {"ok": False, "returns": {}, "fatal": "cancelled"}
        return _run_child(ctx, wf, {**base, item_name: item, "index": i}, tag=f"{i + 1}/{len(items)}")

    results: list[dict | None] = [None] * len(items)
    if parallel == 1:
        for i, item in enumerate(items):
            results[i] = _one(i, item)
            if stop_on_error and not results[i].get("ok"):
                break
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel, thread_name_prefix="automate-foreach") as pool:
            futures = {pool.submit(_one, i, item): i for i, item in enumerate(items)}
            for fut in concurrent.futures.as_completed(futures):
                results[futures[fut]] = fut.result()

    done   = [r for r in results if r is not None]
    errors = [f"item {i + 1}: {_child_error(r) or 'failed'}" for i, r in enumerate(results) if r is not None and not r.get("ok")]
    if errors and (stop_on_error or len(errors) == len(done)):
        return fail(ctx, node, "For Each failed — " + " | ".join(errors[:5]), ports)
    if errors:
        ctx._warn(f"    For Each: {len(errors)} of {len(done)} item(s) failed.")

    all_returns = [(r.get("returns") or {}) if r and r.get("ok") else None for r in results]
    return {
        "results": [_primary(r) if r is not None else None for r in all_returns],
        "all":     all_returns,
        "count":   sum(1 for r in all_returns if r is not None),
        "errors":  "\n".join(errors),
        "error":   "",
    }


# flow.retry_until

def _truthy(val: Any) -> bool:
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "pass", "passed", "ok")
    return bool(val)


def flow_retry_until(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    """Run a workflow repeatedly until its `passed` return is true.

    Each attempt receives the variables  attempt (1-based)  and  feedback  (what the
    previous attempt's reviewer said), so the generator step can correct itself.
    """
    ports = ("out", "pass", "fail", "returns", "feedback", "attempts")
    p  = node.get("properties", {})
    wf = _load_workflow(_to_str(inputs.get("workflow") or p.get("workflow", "")))
    base = _variables(node, inputs)
    if inputs.get("in") is not None:
        base[str(p.get("input_name", "input")).strip() or "input"] = inputs["in"]
    try:
        max_attempts = max(1, min(20, int(p.get("max_attempts", 3) or 3)))
    except (TypeError, ValueError):
        max_attempts = 3
    pass_name     = str(p.get("pass_name", "passed")).strip() or "passed"
    feedback_name = str(p.get("feedback_name", "feedback")).strip() or "feedback"

    feedback: Any = ""
    returns: dict = {}
    passed = False
    attempt = 0
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        if ctx.cancelled:
            break
        ctx._info(f"    Attempt {attempt}/{max_attempts}")
        result = _run_child(ctx, wf, {**base, "attempt": attempt, feedback_name: feedback},
                            tag=f"try {attempt}")
        if not result.get("ok"):
            last_error = _child_error(result) or "failed"
            ctx._warn(f"    Attempt {attempt} errored: {last_error}")
            continue
        last_error = ""
        returns = result.get("returns") or {}
        if pass_name not in returns:
            return fail(ctx, node, f"The workflow '{wf.get('name')}' has no Return node named "
                                   f"'{pass_name}', so there is nothing to decide a retry on.", ports)
        passed = _truthy(returns.get(pass_name))
        feedback = returns.get(feedback_name, "") or ""
        if passed:
            break

    if not returns and last_error:
        return fail(ctx, node, f"Every attempt failed. Last error: {last_error}", ports)

    out = _primary(returns)
    ctx._info(f"    {'Passed' if passed else 'Did not pass'} after {attempt} attempt(s)")
    return {
        "out":      out,
        "pass":     out if passed else None,
        "fail":     None if passed else out,
        "passed":   passed,
        "returns":  returns,
        "feedback": _to_str(feedback),
        "attempts": attempt,
        "error":    "",
    }
