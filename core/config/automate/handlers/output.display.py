def _h_output_display(node, inputs, ctx):
    p = node.get("properties", {})
    label = str(p.get("label", "Result"))
    val = inputs.get("in")
    _OUTPUT_RESULTS.append({"label": label, "value": _to_str(val) if not isinstance(val, str) else val})
    return {}
