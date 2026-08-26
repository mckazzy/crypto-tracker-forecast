import json
import os
from pathlib import Path

import pytest

from app.models.registry import ModelRegistry, model_registry


@pytest.fixture
def registry(tmp_path, monkeypatch):
    r = ModelRegistry(base_dir=str(tmp_path / "models"))
    monkeypatch.setattr("app.models.registry.model_registry", r)
    return r


class TestModelRegistry:
    def test_save_and_load_roundtrip(self, registry):
        meta = {"type": "test", "symbol": "BTCUSDT", "timeframe": "1h", "trained_at": "2026-01-01"}
        registry.save_model("test_model", {"coef": [1.0, 2.0]}, meta)
        model, loaded_meta = registry.load_model("test_model")
        assert model == {"coef": [1.0, 2.0]}
        assert loaded_meta["type"] == "test"

    def test_list_models(self, registry):
        for i in range(3):
            registry.save_model(f"m{i}", {}, {"type": "t"})
        assert registry.list_models() == ["m0", "m1", "m2"]

    def test_load_missing_raises(self, registry):
        with pytest.raises(FileNotFoundError):
            registry.load_model("nope")

    def test_tampered_meta_rejected(self, registry, tmp_path):
        """Meta không đúng schema → load bị chặn."""
        registry.save_model("ok", {}, {"type": "t"})
        meta_path = registry._model_path("ok").with_suffix(".meta.json")
        meta_path.write_text("{not-json", encoding="utf-8")
        with pytest.raises(ValueError, match="meta"):
            registry.load_model("ok")

    def test_path_traversal_blocked(self, registry):
        with pytest.raises(ValueError, match="invalid"):
            registry.save_model("../evil", {}, {"type": "t"})

    def test_global_registry(self):
        assert str(model_registry.base_dir).endswith("models")
