"""Semantic Retriever — API de busca consumida pelos agentes (SPEC-004 §8)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .store import VectorStore


@dataclass
class RAGChunk:
    id: str
    content: str
    collection: str
    relevance_score: Optional[float]
    metadata: Dict[str, Any]


class SemanticRetriever:
    """Busca semântica sobre as coleções de documentos (diario/cursos/referencias)."""

    def __init__(
        self,
        db_path: str = "./data/vectorstore",
        embedding_function: Any = None,
    ):
        self.vector_store = VectorStore(
            db_path=db_path, embedding_function=embedding_function
        )

    def retrieve(
        self,
        query: str,
        collection: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[RAGChunk]:
        raw = self.vector_store.search(
            collection=collection, query=query, top_k=top_k, where=filters
        )
        return [
            RAGChunk(
                id=r["id"],
                content=r["content"],
                collection=r["collection"],
                relevance_score=r["relevance_score"],
                metadata=r["metadata"],
            )
            for r in raw
        ]

    def retrieve_multi_collection(
        self,
        query: str,
        collections: List[str],
        top_k_per_collection: int = 3,
    ) -> Dict[str, List[RAGChunk]]:
        return {
            col: self.retrieve(query, col, top_k=top_k_per_collection)
            for col in collections
        }

    def get_statistics(self, collection: str) -> Dict[str, Any]:
        return self.vector_store.get_collection_stats(collection)
