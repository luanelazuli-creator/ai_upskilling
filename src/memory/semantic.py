"""Memória Semântica — fatos aprendidos sobre o usuário (SPEC-003-2 / SPEC-MEM §4.3).

⚠️ NÃO confundir com RAG de documentos:
    - RAG indexa arquivos em `/data` (coleções `diario`, `cursos`, `referencias`).
    - SemanticMemory indexa fatos atômicos extraídos de conversas
      (coleção `user_facts`), na mesma instância de ChromaDB.

Schema antigo (JSON+keyword, com `add_relation` e `keywords[]`) foi descontinuado:
busca semântica vetorial cobre o caso de uso e mantém o contrato consistente com
os outros tiers (SPEC-MEM §9).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..rag.store import VectorStore


@dataclass
class Fact:
    """Fato sobre o usuário, persistido em ChromaDB.

    `source_conversation_id` é uma FK opcional para EpisodicMemory: aponta a
    conversa de onde o fato foi extraído (rastreabilidade para evals e UX
    de "esquecimento explícito").
    """

    fact_id: str
    user_id: str
    content: str
    category: Optional[str]
    source_conversation_id: Optional[str]
    confidence: float
    timestamp: str

    def to_chroma_metadata(self) -> Dict[str, Any]:
        """Metadata achatada para ChromaDB (só escalares)."""
        meta: Dict[str, Any] = {
            "user_id": self.user_id,
            "confidence": float(self.confidence),
            "timestamp": self.timestamp,
        }
        if self.category is not None:
            meta["category"] = self.category
        if self.source_conversation_id is not None:
            meta["source_conversation_id"] = self.source_conversation_id
        return meta

    @classmethod
    def from_chroma(cls, fact_id: str, content: str, metadata: Dict[str, Any]) -> "Fact":
        return cls(
            fact_id=fact_id,
            user_id=metadata.get("user_id", ""),
            content=content,
            category=metadata.get("category"),
            source_conversation_id=metadata.get("source_conversation_id"),
            confidence=float(metadata.get("confidence", 0.0)),
            timestamp=metadata.get("timestamp", ""),
        )


class SemanticMemory:
    """Armazena e recupera fatos sobre o usuário em ChromaDB (`user_facts`)."""

    def __init__(
        self,
        vector_store: VectorStore,
        collection_name: str = "user_facts",
    ):
        self._store = vector_store
        self._collection_name = collection_name
        # Garante que a coleção existe no startup.
        self._store.get_or_create_collection(collection_name)

    # ------------------------------------------------------------------ write

    def add_fact(
        self,
        user_id: str,
        content: str,
        category: Optional[str] = None,
        source_conversation_id: Optional[str] = None,
        confidence: float = 0.9,
    ) -> str:
        """Adiciona um fato e devolve `fact_id`.

        Raises:
            ValueError: se `user_id` ou `content` estiverem vazios.
        """
        if not user_id:
            raise ValueError("user_id é obrigatório")
        if not content or not content.strip():
            raise ValueError("content é obrigatório e não pode ser vazio")

        fact_id = f"fact_{uuid.uuid4().hex}"
        fact = Fact(
            fact_id=fact_id,
            user_id=user_id,
            content=content.strip(),
            category=category,
            source_conversation_id=source_conversation_id,
            confidence=float(confidence),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._store.add_chunks(
            collection=self._collection_name,
            ids=[fact_id],
            documents=[fact.content],
            metadatas=[fact.to_chroma_metadata()],
        )
        return fact_id

    def delete_fact(self, fact_id: str) -> None:
        """Remove um fato. Idempotente: ID inexistente é no-op (SPEC-003-2 §9)."""
        col = self._store.get_or_create_collection(self._collection_name)
        try:
            col.delete(ids=[fact_id])
        except Exception:
            # Idempotência: ChromaDB pode levantar para IDs inexistentes em
            # algumas versões; queremos no-op silencioso.
            return

    # ------------------------------------------------------------------- read

    def search(
        self,
        user_id: str,
        query: str,
        top_k: int = 3,
    ) -> List[Fact]:
        """Busca semântica restrita a fatos do usuário."""
        results = self._store.search(
            collection=self._collection_name,
            query=query,
            top_k=top_k,
            where={"user_id": user_id},
        )
        return [
            Fact.from_chroma(r["id"], r["content"], r["metadata"]) for r in results
        ]

    def get_fact(self, fact_id: str) -> Optional[Fact]:
        """Recupera um fato por ID (consulta direta, sem busca semântica)."""
        col = self._store.get_or_create_collection(self._collection_name)
        got = col.get(ids=[fact_id], include=["documents", "metadatas"])
        ids = got.get("ids") or []
        if not ids:
            return None
        return Fact.from_chroma(
            fact_id=ids[0],
            content=got["documents"][0],
            metadata=got["metadatas"][0],
        )

    def list_by_category(self, user_id: str, category: str) -> List[Fact]:
        """Lista todos os fatos do usuário em uma categoria."""
        col = self._store.get_or_create_collection(self._collection_name)
        got = col.get(
            where={"$and": [{"user_id": user_id}, {"category": category}]},
            include=["documents", "metadatas"],
        )
        ids = got.get("ids") or []
        return [
            Fact.from_chroma(ids[i], got["documents"][i], got["metadatas"][i])
            for i in range(len(ids))
        ]

    def get_statistics(self, user_id: str) -> Dict[str, Any]:
        """Estatísticas agregadas dos fatos de um usuário."""
        col = self._store.get_or_create_collection(self._collection_name)
        got = col.get(where={"user_id": user_id}, include=["metadatas"])
        metas = got.get("metadatas") or []
        if not metas:
            return {
                "user_id": user_id,
                "total_facts": 0,
                "avg_confidence": 0.0,
                "categories": {},
            }
        categories: Dict[str, int] = {}
        for m in metas:
            cat = m.get("category") or "(uncategorized)"
            categories[cat] = categories.get(cat, 0) + 1
        confidences = [float(m.get("confidence", 0.0)) for m in metas]
        return {
            "user_id": user_id,
            "total_facts": len(metas),
            "avg_confidence": sum(confidences) / len(confidences),
            "categories": categories,
        }
