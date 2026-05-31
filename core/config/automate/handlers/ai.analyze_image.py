def _h_ai_analyze_image(node, inputs, ctx):
    p = node.get("properties", {})
    model_id = _to_str(inputs.get("model") or p.get("model", "")).strip() or "gemini-1.5-flash"
    image_path = _to_str(inputs.get("image") or p.get("image_path", "")).strip()
    question = str(p.get("question", "Describe this image in detail."))
    system = str(p.get("system_prompt", "You are a helpful vision assistant."))
    temp = float(p.get("temperature", 0.3) or 0.3)
    prompt = _to_str(inputs.get("in", question))
    if not image_path: return {"out": "", "error": "No image path provided"}
    try:
        import google.generativeai as _genai
        from PIL import Image as _PIL_Image
        api_key = os.environ.get("GOOGLE_AI_API_KEY", "")
        if not api_key: raise RuntimeError("GOOGLE_AI_API_KEY not set")
        _genai.configure(api_key=api_key)
        model = _genai.GenerativeModel(model_name=model_id, system_instruction=system or None)
        img = _PIL_Image.open(image_path)
        resp = model.generate_content([prompt, img], generation_config=_genai.GenerationConfig(temperature=temp))
        return {"out": resp.text, "error": ""}
    except Exception as exc:
        return {"out": "", "error": str(exc)}
