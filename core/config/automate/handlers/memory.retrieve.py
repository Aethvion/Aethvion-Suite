def _h_memory_retrieve(node, inputs, ctx):
    p = node.get("properties", {})
    key = str(p.get("key", "")).strip()
    default = p.get("default", "")
    if not key: return {"out": default, "found": False, "error": "No key specified"}
    found = key in _MEMORY_STORE
    return {"out": _MEMORY_STORE.get(key, default), "found": found, "error": ""}
