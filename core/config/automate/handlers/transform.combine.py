def _h_transform_combine(node, inputs, ctx):
    sep = str(node.get("properties", {}).get("separator", "\\n")).replace("\\n", "\n").replace("\\t", "\t")
    parts = [x for x in [_to_str(inputs.get("a", "")), _to_str(inputs.get("b", ""))] if x]
    return {"out": sep.join(parts)}
