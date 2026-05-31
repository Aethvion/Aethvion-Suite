def _h_data_variable(node, inputs, ctx):
    p = node.get("properties", {})
    name = str(p.get("name", "var")).strip() or "var"
    default = p.get("value", "")
    var_type = str(p.get("varType", "string"))
    val = ctx._vars.get(name, default)
    if var_type == "number":
        try:
            s = str(val)
            val = float(s) if "." in s else int(s)
        except (ValueError, TypeError):
            pass
    elif var_type == "boolean":
        if isinstance(val, str):
            val = val.lower() in ("true", "1", "yes")
    ctx._vars[name] = val
    return {"out": val, "value": val}
