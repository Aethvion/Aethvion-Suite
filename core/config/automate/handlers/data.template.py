def _h_data_template(node, inputs, ctx):
    import re as _re
    p = node.get("properties", {})
    template = str(p.get("template", ""))
    in_val = inputs.get("in", {})
    if isinstance(in_val, str):
        try: in_val = json.loads(in_val)
        except Exception: pass
    ctx_vars = {}
    if isinstance(in_val, dict): ctx_vars.update(in_val)
    for port in ("var_a", "var_b", "var_c"):
        if port in inputs: ctx_vars[port] = inputs[port]
    def _replace(m):
        key = m.group(1).strip()
        if "|" in key:
            key, default = key.split("|", 1)
            return _to_str(ctx_vars.get(key.strip(), default.strip()))
        return _to_str(ctx_vars.get(key, ""))
    try:
        return {"out": _re.sub(r"\{\{([^}]+)\}\}", _replace, template), "error": ""}
    except Exception as exc:
        return {"out": "", "error": str(exc)}
