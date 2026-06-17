def _h_ai_generate_image(node, inputs, ctx):
    p = node.get("properties", {})
    model_id = str(p.get("model", "imagen-3.0-generate-002"))
    aspect_ratio = str(p.get("aspect_ratio", "1:1"))
    path = _to_str(inputs.get("path") or p.get("path", "")).strip()
    prompt = _to_str(inputs.get("in", ""))
    if not path:
        import tempfile as _tf, os as _os
        path = _os.path.join(_tf.gettempdir(), f"imagen_{_ts().replace(':','').replace('.','')}.png")
    try:
        import google.generativeai as _genai
        api_key = os.environ.get("GOOGLE_AI_API_KEY", "")
        if not api_key: raise RuntimeError("GOOGLE_AI_API_KEY not set")
        _genai.configure(api_key=api_key)
        model = _genai.ImageGenerationModel(model_id)
        resp = model.generate_images(prompt=prompt, number_of_images=1, aspect_ratio=aspect_ratio)
        resp.images[0].save(path)
        return {"out": path, "path": path, "count": 1, "error": ""}
    except Exception as exc:
        return {"out": "", "path": "", "count": 0, "error": str(exc)}
