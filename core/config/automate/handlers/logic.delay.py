def _h_logic_delay(node, inputs, ctx):
    import time as _time
    ms = float(node.get("properties", {}).get("duration", 1000) or 1000)
    _time.sleep(ms / 1000)
    return {"out": inputs.get("in")}
