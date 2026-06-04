def _h_ui_display_text(node, inputs, ctx):
    val = inputs.get("in", "")
    return {"_display": val}

