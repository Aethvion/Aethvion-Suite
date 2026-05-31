def _h_logic_switch(node, inputs, ctx):
    p = node.get("properties", {})
    in_val = inputs.get("in")
    switch_on = str(p.get("switch_on", "")).strip()
    val = str(in_val.get(switch_on, "")) if (switch_on and isinstance(in_val, dict)) else _to_str(in_val)
    out = {"case_1": None, "case_2": None, "case_3": None, "case_4": None, "default": None}
    matched = False
    for i in range(1, 5):
        case_val = str(p.get(f"case_{i}", "")).strip()
        if case_val and val == case_val:
            out[f"case_{i}"] = in_val
            matched = True
            break
    if not matched:
        out["default"] = in_val
    return out
