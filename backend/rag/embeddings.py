from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.rag.config import get_embedding_model_name


class LocalEmbedder:
    """Thin wrapper around sentence-transformers with offline-safe behavior."""

    def __init__(self, model_name: str | None = None, cache_dir: str | Path | None = None):
        self.model_name = model_name or get_embedding_model_name()
        self.cache_dir = str(cache_dir) if cache_dir is not None else None
        self._model = None

    def _load_model(self):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - exercised when dependency is absent
            raise RuntimeError(
                "sentence-transformers is not installed. Install requirements or use the project venv."
            ) from exc

        try:
            model = SentenceTransformer(self.model_name, cache_folder=self.cache_dir)
        except Exception as exc:  # pragma: no cover - network/download guard
            raise RuntimeError(
                "Model download failed because the environment is offline or the network is unavailable. "
                "Please make a network connection or preload the model cache before retrying."
            ) from exc
        self._model = model
        return model

    def encode(self, texts: list[str] | str):
        if isinstance(texts, str):
            texts = [texts]
        model = self._model or self._load_model()
        vectors = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        return vectors.tolist() if isinstance(vectors, Any) else vectors

    def encode_query(self, text: str):
        vectors = self.encode(text)
        return vectors[0]
