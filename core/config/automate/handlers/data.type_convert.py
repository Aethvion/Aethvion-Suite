def _h_data_type_convert(node, inputs, ctx):
    p = node.get("properties", {})
    to = str(p.get("to", "string"))
    val = inputs.get("in")
    try:
        if to == "string":  return {"out": _to_str(val), "error": ""}
        if to == "integer": return {"out": int(float(_to_str(val))), "error": ""}
        if to == "float":   return {"out": float(_to_str(val)), "error": ""}
        if to == "json":    return {"out": json.loads(_to_str(val)), "error": ""}
        if to == "boolean":
            tv = [v.strip().lower() for v in str(p.get("true_values",  "true,yes,1,on")).split(",")]
            fv = [v.strip().lower() for v in str(p.get("false_values", "false,no,0,off")).split(",")]
            s = _to_str(val).lower()
            if s in tv: return {"out": True, "error": ""}
            if s in fv: return {"out": False, "error": ""}
            return {"out": bool(val), "error": ""}
        return {"out": val, "error": ""}
    except Exception as exc:
        return {"out": None, "error": str(exc)}
