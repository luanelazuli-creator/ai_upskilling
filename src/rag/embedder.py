"""Fábrica de funções de embedding plugáveis (SPEC-004 §5).

Todas as funções retornadas seguem a interface `EmbeddingFunction` do ChromaDB,
de modo que a coleção é dona do embedding e o resto do pipeline não precisa
computar vetores manualmente.

Backends:
    - "chroma_default": ONNX all-MiniLM-L6-v2 (leve, sem torch) — bom para testes.
    - "fake":           determinístico por hash (zero download) — testes de mecânica.
    - "<model_name>":   sentence-transformers (ex.: paraphrase-multilingual-MiniLM-L12-v2).
"""

from __future__ import annotations

import hashlib
from typing import List

try:
    from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

    _BASE = EmbeddingFunction
except ImportError:  # pragma: no cover - chromadb é dependência do módulo rag
    _BASE = object
    Documents = list  # type: ignore
    Embeddings = list  # type: ignore


def get_embedding_function(model_spec: str = "chroma_default"):
    """Resolve a string de configuração para uma EmbeddingFunction do ChromaDB."""
    if model_spec == "fake":
        return HashEmbeddingFunction()

    from chromadb.utils import embedding_functions

    if model_spec == "chroma_default":
        return embedding_functions.DefaultEmbeddingFunction()

    # Qualquer outro valor é tratado como nome de modelo sentence-transformers.
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=model_spec
    )


class HashEmbeddingFunction(_BASE):
    """Embedder determinístico, sem dependências de ML.

    Mapeia tokens para um vetor de dimensão fixa via hash. NÃO captura semântica —
    serve apenas para validar a mecânica do pipeline (chunking, persistência,
    contagem) sem baixar modelos. Implementa a interface `EmbeddingFunction` do
    ChromaDB, então herda os caminhos corretos de indexação e consulta.
    """

    def __init__(self, dim: int = 384):
        self.dim = dim

    @staticmethod
    def name() -> str:
        return "hash-fake"

    def __call__(self, input: "Documents") -> "Embeddings":
        return [self._embed(text) for text in input]

    def get_config(self) -> dict:
        return {"dim": self.dim}

    @classmethod
    def build_from_config(cls, config: dict) -> "HashEmbeddingFunction":
        return cls(dim=config.get("dim", 384))

    def _embed(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        for token in text.lower().split():
            h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec
