from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import joblib

logger = logging.getLogger(__name__)

_MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9_.@-]+$")


class ModelRegistry:
    """File-based model registry: models/{name}.pkl + {name}.meta.json."""

    def __init__(self, base_dir: str = "models"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _model_path(self, name: str) -> Path:
        if not _MODEL_NAME_RE.match(name) or name.startswith("."):
            raise ValueError(f"invalid model name: {name}")
        return self.base_dir / f"{name}.pkl"

    def _meta_path(self, name: str) -> Path:
        if not _MODEL_NAME_RE.match(name) or name.startswith("."):
            raise ValueError(f"invalid model name: {name}")
        return self.base_dir / f"{name}.meta.json"

    def save_model(self, name: str, model, meta: dict) -> None:
        if not isinstance(meta, dict) or "type" not in meta:
            raise ValueError("meta must be dict with 'type' key")
        joblib.dump(model, self._model_path(name))
        self._meta_path(name).write_text(json.dumps(meta, default=str), encoding="utf-8")
        logger.info("saved model %s (type=%s)", name, meta["type"])

    def load_model(self, name: str) -> tuple:
        pkl = self._model_path(name)
        meta_p = self._meta_path(name)
        if not pkl.exists() or not meta_p.exists():
            raise FileNotFoundError(f"model not found: {name}")
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"corrupt meta for {name}: {e}") from e
        if not isinstance(meta, dict) or "type" not in meta:
            raise ValueError(f"invalid meta schema for {name}")
        model = joblib.load(pkl)
        return model, meta

    def list_models(self) -> list[str]:
        names = []
        for p in sorted(self.base_dir.glob("*.pkl")):
            names.append(p.stem)
        return names

    def has(self, name: str) -> bool:
        return self._model_path(name).exists()


model_registry = ModelRegistry()
