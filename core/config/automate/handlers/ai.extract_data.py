def _h_ai_extract_data(node, inputs, ctx):
    p = node.get("properties", {})
    model_id = _to_str(inputs.get("model") or p.get("model", "")).strip()
    if not model_id: raise ValueError("ai.extract_data: No model selected")
    text = _to_str(inputs.get("in", ""))
    fields_raw = _to_str(inputs.get("schema") or p.get("fields", ""))
    context = str(p.get("context", "")).strip()
    missing = str(p.get("missing_value", ""))
    field_defs = {}
    for line in fields_raw.strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            if k.strip(): field_defs[k.strip()] = v.strip()
    if not field_defs: return {"out": "{}", "error": "No fields configured"}
    schema_desc = "\n".join(f'- "{k}": {v}' for k, v in field_defs.items())
    system = (f"Extract fields from text as JSON.{f' Context: {context}' if context else ''}"
              f"\nFields:\n{schema_desc}"
              f"\nMissing fields use {repr(missing)}. Return ONLY the JSON object.")
    try:
        resp = _ai_call(model_id, system, text, 0.1)
        parsed = _extract_json_block(resp)
        if not parsed: return {"out": resp, "error": "Could not parse JSON from AI response"}
        for k in field_defs:
            if k not in parsed: parsed[k] = missing
        return {"out": json.dumps(parsed, ensure_ascii=False), "error": ""}
    except Exception as exc:
        return {"out": "{}", "error": str(exc)}
