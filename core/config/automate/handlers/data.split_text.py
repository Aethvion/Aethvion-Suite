def _h_data_split_text(node, inputs, ctx):
    p = node.get("properties", {})
    mode = str(p.get("mode", "delimiter"))
    text = _to_str(inputs.get("in", ""))
    delimiter = str(p.get("delimiter", ",")).replace("\\n", "\n").replace("\\t", "\t")
    chunk_size = int(p.get("chunk_size", 500) or 500)
    trim = bool(p.get("trim", True))
    remove_empty = bool(p.get("remove_empty", True))
    if mode == "lines":   parts = text.splitlines()
    elif mode == "words": parts = text.split()
    elif mode == "chunks": parts = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    else: parts = text.split(delimiter)
    if trim: parts = [x.strip() for x in parts]
    if remove_empty: parts = [x for x in parts if x]
    return {"out": parts, "first": parts[0] if parts else "", "last": parts[-1] if parts else "", "count": len(parts)}
