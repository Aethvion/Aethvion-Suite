def _h_trigger_app_event(node, inputs, ctx):
    return {"trigger": True, "event_type": "manual", "source": "standalone", "data": None}
