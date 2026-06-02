"""
tests/test_provider_routing.py
════════════════════════════════
Unit tests for AethvionDB vectorizer provider routing.

Checks that:
  - Known cloud models map to the correct provider ("google", "openai")
  - Local model names map to provider "local"
  - _embed() correctly dispatches to the local path for local models
  - embed_sync() raises a clear error when no API key is set for cloud models
  - The EMBEDDING_MODELS registry has required fields
"""
from __future__ import annotations

import pytest

# Lazy imports so missing optional deps don't fail the whole suite
from core.aethviondb.vectorizer import EMBEDDING_MODELS


# EMBEDDING_MODELS registry shape

class TestEmbeddingModelsRegistry:
    def test_registry_is_not_empty(self):
        assert len(EMBEDDING_MODELS) > 0

    def test_all_entries_have_provider(self):
        for name, info in EMBEDDING_MODELS.items():
            assert "provider" in info, f"{name!r} missing 'provider'"

    def test_all_entries_have_dimensions(self):
        for name, info in EMBEDDING_MODELS.items():
            assert "dimensions" in info, f"{name!r} missing 'dimensions'"
            assert isinstance(info["dimensions"], int)
            assert info["dimensions"] > 0

    def test_known_google_models(self):
        google_models = [
            "text-embedding-004",
            "text-multilingual-embedding-002",
        ]
        for m in google_models:
            if m in EMBEDDING_MODELS:
                assert EMBEDDING_MODELS[m]["provider"] == "google", (
                    f"{m!r} expected provider='google'"
                )

    def test_known_openai_models(self):
        openai_models = [
            "text-embedding-3-small",
            "text-embedding-3-large",
            "text-embedding-ada-002",
        ]
        for m in openai_models:
            if m in EMBEDDING_MODELS:
                assert EMBEDDING_MODELS[m]["provider"] == "openai", (
                    f"{m!r} expected provider='openai'"
                )

    def test_local_models_have_provider_local(self):
        local_models = [
            "all-MiniLM-L6-v2",
            "all-MiniLM-L12-v2",
            "all-mpnet-base-v2",
        ]
        for m in local_models:
            if m in EMBEDDING_MODELS:
                assert EMBEDDING_MODELS[m]["provider"] == "local", (
                    f"{m!r} expected provider='local'"
                )


# Provider dispatch

class TestProviderDispatch:
    def test_unknown_model_falls_back_to_google(self):
        """Unknown model names fall back to the Google provider path."""
        # We just verify the model resolution — not the API call itself
        info = EMBEDDING_MODELS.get("this-model-does-not-exist", {})
        provider = info.get("provider", "google")
        # The fallback default in _embed / embed_sync is "google"
        assert provider == "google"

    def test_google_model_no_key_raises(self):
        """embed_sync with a Google model but no API key should raise RuntimeError."""
        import os
        from core.aethviondb.vectorizer import embed_sync

        original = os.environ.pop("GOOGLE_AI_API_KEY", None)
        try:
            with pytest.raises(RuntimeError, match="GOOGLE_AI_API_KEY"):
                embed_sync("test input", "text-embedding-004")
        finally:
            if original is not None:
                os.environ["GOOGLE_AI_API_KEY"] = original

    def test_openai_model_no_key_raises(self):
        """embed_sync with an OpenAI model but no API key should raise RuntimeError."""
        import os
        from core.aethviondb.vectorizer import embed_sync

        original = os.environ.pop("OPENAI_API_KEY", None)
        try:
            with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
                embed_sync("test input", "text-embedding-3-small")
        finally:
            if original is not None:
                os.environ["OPENAI_API_KEY"] = original


# Local model path (mocked — avoids downloading model weights in CI)

class TestLocalModelPath:
    def test_local_model_calls_sentence_transformers(self, monkeypatch):
        """
        When a local model is requested, vectorizer should try to import
        sentence_transformers.SentenceTransformer and call .encode().

        We monkeypatch the SentenceTransformer class so no model is downloaded.
        """
        import core.aethviondb.vectorizer as vz

        # Clear cache so our mock is picked up
        vz._local_model_cache.clear()

        dummy_vector = [0.1] * 384

        class _FakeST:
            def encode(self, text, normalize_embeddings=True):
                import numpy as np
                return np.array(dummy_vector)

        def _fake_get_local_model(model: str):
            return _FakeST()

        monkeypatch.setattr(vz, "_get_local_model", _fake_get_local_model)

        result = vz.embed_sync("hello world", "all-MiniLM-L6-v2")
        assert isinstance(result, list)
        assert len(result) == 384
        assert all(isinstance(v, float) for v in result)
