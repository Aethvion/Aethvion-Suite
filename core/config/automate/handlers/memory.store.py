def _h_memory_store(node, inputs, ctx):
    p = node.get("properties", {})
    key = _to_str(inputs.get("key") or p.get("key", "")).strip()
    if not key: return {"out": inputs.get("in"), "error": "No key specified"}
    _MEMORY_STORE[key] = inputs.get("in")
    return {"out": inputs.get("in"), "error": ""}
