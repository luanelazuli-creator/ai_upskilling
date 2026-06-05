"""Vector Store — ChromaDB com embedding plugável (SPEC-004 §5/§6).

A coleção é dona da função de embedding; o pipeline só passa documentos/texto.
Inclui helpers para re-indexação incremental por hash (SPEC-004 §6).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import chromadb
except ImportError:  # pragma: no cover
    chromadb = None


class VectorStore:
    """Vector store local sobre ChromaDB, com embedding function injetável."""

    def __init__(
        self,
        db_path: str = "./data/vectorstore",
        embedding_function: Any = None,
    ):
        if chromadb is None:
            raise ImportError(
                "chromadb não está instalado. Execute: pip install chromadb"
            )
        if embedding_function is None:
            from .embedder import get_embedding_function

            embedding_function = get_embedding_function("chroma_default")

        Path(db_path).mkdir(parents=True, exist_ok=True)
        self.db = chromadb.PersistentClient(path=db_path)
        self.embedding_function = embedding_function
        self.collections: Dict[str, Any] = {}

    def get_or_create_collection(self, name: str) -> Any:
        if name not in self.collections:
            self.collections[name] = self.db.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
                embedding_function=self.embedding_function,
            )
        return self.collections[name]

    # --- escrita -----------------------------------------------------------

    def add_chunks(
        self,
        collection: str,
        ids: List[str],
        documents: List[str],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        """Adiciona chunks em lote (ChromaDB computa os embeddings)."""
        if not ids:
            return
        col = self.get_or_create_collection(collection)
        col.add(ids=ids, documents=documents, metadatas=metadatas)

    def delete_by_source(self, collection: str, source_file: str) -> int:
        """Remove todos os chunks de um arquivo. Retorna quantos havia."""
        col = self.get_or_create_collection(collection)
        existing = col.get(where={"source_file": source_file}, include=[])
        count = len(existing.get("ids", []))
        if count:
            col.delete(where={"source_file": source_file})
        return count

    # --- leitura -----------------------------------------------------------

    def get_existing_hash(
        self, collection: str, source_file: str
    ) -> Optional[str]:
        """Retorna o content_hash já indexado para um arquivo, ou None."""
        col = self.get_or_create_collection(collection)
        existing = col.get(
            where={"source_file": source_file},
            limit=1,
            include=["metadatas"],
        )
        metas = existing.get("metadatas") or []
        if metas:
            return metas[0].get("content_hash")
        return None

    def search(
        self,
        collection: str,
        query: str,
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        col = self.get_or_create_collection(collection)
        results = col.query(
            query_texts=[query],
            n_results=top_k,
            where=where or None,
        )
        return self._format_results(results, collection)

    def get_collection_stats(self, collection: str) -> Dict[str, Any]:
        col = self.get_or_create_collection(collection)
        return {"name": collection, "document_count": col.count()}

    def list_collections(self) -> List[str]:
        return [c.name for c in self.db.list_collections()]

    def delete_collection(self, collection: str) -> None:
        self.db.delete_collection(name=collection)
        self.collections.pop(collection, None)

    # --- helpers -----------------------------------------------------------

    @staticmethod
    def _format_results(
        results: Dict[str, Any], collection: str
    ) -> List[Dict[str, Any]]:
        formatted: List[Dict[str, Any]] = []
        ids = results.get("ids") or [[]]
        if not ids or not ids[0]:
            return formatted

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]

        for i, doc_id in enumerate(ids[0]):
            distance = dists[i] if i < len(dists) else None
            formatted.append(
                {
                    "id": doc_id,
                    "content": docs[i] if i < len(docs) else "",
                    "collection": collection,
                    "metadata": metas[i] if i < len(metas) else {},
                    "distance": distance,
                    "relevance_score": (
                        1 - distance if distance is not None else None
                    ),
                }
            )
        return formatted
