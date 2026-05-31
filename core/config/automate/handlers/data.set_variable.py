def _h_data_set_variable(node, inputs, ctx):
    name = str(node.get("properties", {}).get("name", "myVar")).strip()
    val = inputs.get("in")
    ctx._vars[name] = val
    return {"out": val}
