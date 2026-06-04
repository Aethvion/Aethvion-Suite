def _h_ui_display_image(node, inputs, ctx):
    val = inputs.get("in", "")
    return {"_display_image": val}

