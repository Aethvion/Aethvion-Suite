def _h_ui_custom_html(node, inputs, ctx):
    val = inputs.get("in", "")
    return {"out": val, "_display_html": val}
