def _h_trigger_webhook(node, inputs, ctx):
    return {"trigger": True, "out": inputs.get("body", {}), "body": inputs.get("body", {})}
