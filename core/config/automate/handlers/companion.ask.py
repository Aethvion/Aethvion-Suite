def _h_companion_ask(node, inputs, ctx):
    p = node.get("properties", {})
    model_id = _to_str(inputs.get("model") or p.get("model", "")).strip() or "gemini-2.0-flash"
    system = _to_str(inputs.get("system") or p.get("system_prompt", "You are a helpful assistant."))
    prompt = _to_str(inputs.get("in", ""))
    temp = float(p.get("temperature", 0.7) or 0.7)
    try:
        return {"out": _ai_call(model_id, system, prompt, temp), "error": ""}
    except Exception as exc:
        return {"out": "", "error": str(exc)}
