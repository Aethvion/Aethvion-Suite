def _h_ai_speech_to_text(node, inputs, ctx):
    try: import whisper as _whisper
    except ImportError: raise RuntimeError("openai-whisper not installed")
    p = node.get("properties", {})
    path = _to_str(inputs.get("path") or p.get("path", "")).strip()
    model_id = str(p.get("model_id", "whisper") or "base")
    if model_id == "whisper": model_id = "base"
    lang = str(p.get("language", "")).strip() or None
    if not path: return {"out": "", "language": "", "error": "No audio path"}
    try:
        model = _whisper.load_model(model_id)
        result = model.transcribe(path, language=lang)
        return {"out": result.get("text", ""), "language": result.get("language", ""), "error": ""}
    except Exception as exc:
        return {"out": "", "language": "", "error": str(exc)}
