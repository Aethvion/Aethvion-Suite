def _h_trigger_file_watch(node, inputs, ctx):
    return {"trigger": True, "path": "", "event": "manual"}
