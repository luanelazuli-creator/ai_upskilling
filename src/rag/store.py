"""
Vector Store - Gerenciador de índices e busca com ChromaDB
"""

from typing import List, Dict, Optional, Any
from pathlib import Path

try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    chromadb = None

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None


class VectorStore:
    """
    Vector store local usando ChromaDB e sentence-transformers.
    
    Responsável por:
    - Armazenar e recuperar embeddings
    - Gerenciar coleções de documentos
    - Realizar busca semântica
    """
    
    def __init__(
        self,
        db_path: str = "./data/vectorstore",
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    ):
        """
        Inicializar Vector Store.
        
        Args:
            db_path: Caminho para o banco de dados ChromaDB
            embedding_model: Modelo de embedding a utilizar
        """
        if chromadb is None:
            raise ImportError("chromadb não está instalado. Execute: pip install chromadb")
        if SentenceTransformer is None:
            raise ImportError("sentence-transformers não está instalado. Execute: pip install sentence-transformers")
        
        Path(db_path).mkdir(parents=True, exist_ok=True)
        
        # ChromaDB persistent client
        self.db = chromadb.PersistentClient(path=db_path)
        
        # Modelo de embedding
        self.embedding_model = SentenceTransformer(embedding_model)
        self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()
        
        # Cache de coleções
        self.collections: Dict[str, Any] = {}
    
    def get_or_create_collection(self, name: str) -> Any:
        """
        Obter ou criar coleção.
        
        Args:
            name: Nome da coleção
        
        Returns:
            Objeto da coleção ChromaDB
        """
        if name not in self.collections:
            self.collections[name] = self.db.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"}
            )
        return self.collections[name]
    
    def index_document(
        self,
        collection: str,
        doc_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Indexar documento com embeddings.
        
        Args:
            collection: Nome da coleção
            doc_id: ID único do documento
            content: Conteúdo do documento
            metadata: Metadados associados ao documento
        """
        if metadata is None:
            metadata = {}
        
        # Gerar embedding
        embedding = self.embedding_model.encode(content).tolist()
        
        # Obter coleção e adicionar documento
        collection_obj = self.get_or_create_collection(collection)
        collection_obj.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[content],
            metadatas=[metadata]
        )
    
    def search(
        self,
        collection: str,
        query: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Buscar documentos relevantes.
        
        Args:
            collection: Nome da coleção
            query: Texto da consulta
            top_k: Número máximo de resultados
        
        Returns:
            Lista de documentos relevantes com metadata
        """
        # Gerar embedding da query
        query_embedding = self.embedding_model.encode(query).tolist()
        
        # Obter coleção e buscar
        collection_obj = self.get_or_create_collection(collection)
        results = collection_obj.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        
        return self._format_results(results)
    
    def delete_document(self, collection: str, doc_id: str) -> None:
        """
        Deletar documento da coleção.
        
        Args:
            collection: Nome da coleção
            doc_id: ID do documento
        """
        collection_obj = self.get_or_create_collection(collection)
        collection_obj.delete(ids=[doc_id])
    
    def get_collection_stats(self, collection: str) -> Dict[str, Any]:
        """
        Obter estatísticas da coleção.
        
        Args:
            collection: Nome da coleção
        
        Returns:
            Dicionário com estatísticas
        """
        collection_obj = self.get_or_create_collection(collection)
        count = collection_obj.count()
        
        return {
            "name": collection,
            "document_count": count,
            "embedding_dimension": self.embedding_dim
        }
    
    def list_collections(self) -> List[str]:
        """
        Listar todas as coleções.
        
        Returns:
            Lista de nomes de coleções
        """
        return list(self.db.list_collections())
    
    def delete_collection(self, collection: str) -> None:
        """
        Deletar coleção inteira.
        
        Args:
            collection: Nome da coleção
        """
        self.db.delete_collection(name=collection)
        if collection in self.collections:
            del self.collections[collection]
    
    def _format_results(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Formatar resultados da busca.
        
        Args:
            results: Resultados brutos do ChromaDB
        
        Returns:
            Lista formatada de resultados
        """
        formatted = []
        
        if not results["ids"] or len(results["ids"]) == 0:
            return formatted
        
        # ChromaDB retorna resultados em listas aninhadas
        ids_list = results["ids"][0]
        docs_list = results["documents"][0]
        metadata_list = results["metadatas"][0]
        distances_list = results.get("distances", [[]])[0]
        
        for i, doc_id in enumerate(ids_list):
            formatted.append({
                "id": doc_id,
                "content": docs_list[i] if i < len(docs_list) else "",
                "metadata": metadata_list[i] if i < len(metadata_list) else {},
                "distance": distances_list[i] if i < len(distances_list) else None,
                "relevance_score": 1 - distances_list[i] if i < len(distances_list) else None
            })
        
        return formatted
