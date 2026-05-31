def _h_aethviondb_semantic_search(node, inputs, ctx):
    # Semantic search requires a live Aethvion Suite instance (embedding API + entity files).
    # It cannot run inside a compiled standalone bundle.
    ctx._warn("AethvionDB Semantic Search was skipped: this node requires a live Aethvion Suite "
              "instance and cannot run in a compiled bundle.")
    return {"out": "[]", "count": 0, "speed": "0ms",
            "error": "Not supported in compiled bundles — use inside Aethvion Suite Automate."}
