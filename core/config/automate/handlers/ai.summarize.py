def _h_ai_summarize(node, inputs, ctx):
    p = node.get("properties", {})
    model_id = _to_str(inputs.get("model") or p.get("model", "")).strip()
    if not model_id: raise ValueError("ai.summarize: No model selected")
    text = _to_str(inputs.get("in", ""))
    style = str(p.get("style", "paragraph"))
    length = _to_str(inputs.get("length") or p.get("length", "medium"))
    language = str(p.get("language", "")).strip()
    sm = {"paragraph": "Write a clear summary in flowing prose.", "bullets": "Write a bullet-point list.",
          "headline": "Write a one-sentence headline followed by 2 sentences.", "tldr": "Write a single TL;DR sentence."}
    lm = {"short": "Keep to 1-2 sentences.", "medium": "About one paragraph.",
          "long": "Multiple paragraphs covering all key points."}
    lang = f" Write in {language}." if language else ""
    system = f"You are a professional text summarizer.{lang} {sm.get(style,'')} {lm.get(length,'')}"
    try:
        return {"out": _ai_call(model_id, system, text, 0.3), "error": ""}
    except Exception as exc:
        return {"out": "", "error": str(exc)}
