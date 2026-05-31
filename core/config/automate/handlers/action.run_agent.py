def _h_action_run_agent(node, inputs, ctx):
    p = node.get("properties", {})
    model_id = _to_str(inputs.get("model") or p.get("model", "")).strip() or "gemini-2.0-flash"
    domain = str(p.get("domain", "Automate"))
    action = str(p.get("action", "Execute"))
    obj = str(p.get("object", "Task"))
    instructions = str(p.get("instructions", "")).strip()
    temp = float(p.get("temperature", 0.7) or 0.7)
    goal = _to_str(inputs.get("in", ""))
    system = f"You are an AI agent specialising in {domain}. Your task is to {action} the {obj}."
    if instructions: system += f"\nAdditional instructions: {instructions}"
    try:
        out = _ai_call(model_id, system, goal, temp)
        return {"out": out, "agent": model_id, "error": ""}
    except Exception as exc:
        return {"out": "", "agent": "", "error": str(exc)}
