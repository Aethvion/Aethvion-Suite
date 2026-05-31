def _h_ai_classify(node, inputs, ctx):
    p = node.get("properties", {})
    model_id = _to_str(inputs.get("model") or p.get("model", "")).strip()
    if not model_id: raise ValueError("ai.classify: No model selected")
    text = _to_str(inputs.get("in", ""))
    labels = [lb.strip() for lb in _to_str(inputs.get("labels") or p.get("labels", "")).split(",") if lb.strip()]
    context = str(p.get("context", "")).strip()
    if not labels: return {"label": "", "reasoning": "", "all": "{}", "error": "No categories configured"}
    system = (f"Classify the text into exactly one of: {', '.join(labels)}."
              + (f"\nContext: {context}" if context else "")
              + '\nRespond ONLY with JSON: {"label": "...", "reasoning": "..."}')
    try:
        resp = _ai_call(model_id, system, text, 0.1)
        parsed = _extract_json_block(resp)
        label = str(parsed.get("label", "")).strip()
        reasoning = str(parsed.get("reasoning", "")).strip()
        if label not in labels:
            lower_map = {lb.lower(): lb for lb in labels}
            label = lower_map.get(label.lower(), label or "unknown")
        return {"label": label, "reasoning": reasoning,
                "all": json.dumps({"label": label, "reasoning": reasoning}), "error": ""}
    except Exception as exc:
        return {"label": "", "reasoning": "", "all": "{}", "error": str(exc)}
