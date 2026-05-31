def _h_data_format_text(node, inputs, ctx):
    p = node.get("properties", {})
    template = str(p.get("template", "{{input}}"))
    in_val = _to_str(inputs.get("in", ""))
    out = template.replace("{{input}}", in_val).replace("{{value}}", in_val)
    return {"out": out}
