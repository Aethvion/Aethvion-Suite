def _h_action_file_read(node, inputs, ctx):
    p = node.get("properties", {})
    path = _to_str(inputs.get("path") or p.get("path", "")).strip()
    encoding = str(p.get("encoding", "utf-8"))
    strip = bool(p.get("strip", False))
    max_bytes = int(p.get("max_bytes", 0) or 0)
    if not path: return {"out": "", "path": "", "size": 0, "error": "No path"}
    try:
        import os.path as _op
        path = _op.expandvars(_op.expanduser(path))
        if encoding == "binary":
            data = open(path, "rb").read()
            if max_bytes: data = data[:max_bytes]
            return {"out": data.hex(), "path": path, "size": len(data), "error": ""}
        content = open(path, encoding=encoding).read()
        if max_bytes: content = content[:max_bytes]
        if strip: content = content.strip()
        return {"out": content, "path": path, "size": len(content), "error": ""}
    except Exception as exc:
        return {"out": "", "path": path, "size": 0, "error": str(exc)}
