def _h_logic_if(node, inputs, ctx):
    p = node.get("properties", {})
    condition = str(p.get("condition", "")).strip()
    in_val = inputs.get("in")
    if not condition:
        result = bool(in_val)
    else:
        try:
            result = bool(_safe_eval(condition, {"value": in_val, "input": in_val}))
        except Exception as exc:
            ctx._warn(f"logic.if condition error: {exc}")
            result = False
    return {"true": in_val if result else None, "false": in_val if not result else None}
