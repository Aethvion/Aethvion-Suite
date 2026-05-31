def _h_data_extract_json(node, inputs, ctx):
    import re as _re
    p        = node.get("properties", {})
    key_path = str(p.get("key", "")).strip()
    default  = p.get("default", "")
    output_as = str(p.get("output_as", "auto"))
    in_val = inputs.get("in", "")
    if isinstance(in_val, str):
        try:
            obj = json.loads(in_val)
        except Exception as exc:
            return {"out": default, "error": f"JSON parse error: {exc}"}
    else:
        obj = in_val
    if not key_path:
        result = obj
    else:
        _INDEX_RE   = _re.compile(r"\[(\d+)\]")
        _SEGMENT_RE = _re.compile(r"^([^\[]*)((?:\[\d+\])*)$")
        def _resolve(root, path):
            current = root
            for raw_seg in path.split("."):
                seg = raw_seg.strip()
                if not seg:
                    continue
                m = _SEGMENT_RE.match(seg)
                if not m:
                    raise KeyError(seg)
                key_part = m.group(1)
                idx_part = m.group(2)
                if key_part:
                    if isinstance(current, list):
                        current = current[int(key_part)]
                    elif isinstance(current, dict):
                        current = current[key_part]
                    else:
                        raise KeyError(key_part)
                for idx_str in _INDEX_RE.findall(idx_part):
                    if not isinstance(current, (list, tuple)):
                        raise IndexError(f"[{idx_str}] on non-list")
                    current = current[int(idx_str)]
            return current
        try:
            result = _resolve(obj, key_path)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            if default != "":
                return {"out": default, "error": ""}
            return {"out": "", "error": f"Key not found: {key_path} ({exc})"}
    if output_as == "string": result = _to_str(result)
    elif output_as == "json": result = json.dumps(result, ensure_ascii=False)
    return {"out": result, "error": ""}
