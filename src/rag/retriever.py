"""
Semantic Retriever - Sistema de busca semântica integrado
"""

from typing import List, Dict, Any, Optional
from .store import VectorStore
from .vectorizer import DocumentChunker


class SemanticRetriever:
    """
    Sistema de busca semântica integrado que combina:
    - Chunking de documentos
    - Indexação com embeddings
    - Busca por similaridade
    """
    
    def __init__(
        self,
        db_path: str = "./data/vectorstore",
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ):
        """
        Inicializar retriever.
        
        Args:
            db_path: Caminho para o vector store
            chunk_size: Tamanho dos chunks
            chunk_overlap: Overlapping entre chunks
        """
        self.vector_store = VectorStore(db_path=db_path)
        self.chunker = DocumentChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
    
    def index_document(
        self,
        doc_id: str,
        content: str,
        collection: str = "default",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Indexar documento inteiro (com chunking automático).
        
        Args:
            doc_id: ID único do documento
            content: Conteúdo do documento
            collection: Coleção onde armazenar
            metadata: Metadados do documento
        
        Returns:
            Estatísticas de indexação
        """
        if metadata is None:
            metadata = {}
        
        # Chunking
        chunks = self.chunker.chunk_document(content, metadata)
        
        # Indexar cada chunk
        for chunk in chunks:
            chunk_id = f"{doc_id}_chunk_{chunk['metadata']['chunk_index']}"
            chunk_metadata = {
                **chunk['metadata'],
                "source_doc_id": doc_id
            }
            
            self.vector_store.index_document(
                collection=collection,
                doc_id=chunk_id,
                content=chunk['content'],
                metadata=chunk_metadata
            )
        
        stats = self.chunker.get_chunk_statistics(chunks)
        stats['collection'] = collection
        stats['source_doc_id'] = doc_id
        
        return stats
    
    def retrieve(
        self,
        query: str,
        collection: str = "default",
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Buscar documentos mais relevantes.
        
        Args:
            query: Consulta em linguagem natural
            collection: Coleção onde buscar
            top_k: Número máximo de resultados
        
        Returns:
            Lista de documentos relevantes
        """
        results = self.vector_store.search(
            collection=collection,
            query=query,
            top_k=top_k
        )
        
        return results
    
    def retrieve_by_source(
        self,
        query: str,
        collection: str = "default",
        top_k: int = 5,
        group_by_source: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Buscar documentos agrupados por documento origem.
        
        Args:
            query: Consulta em linguagem natural
            collection: Coleção onde buscar
            top_k: Número máximo de resultados
            group_by_source: Se True, agrupa por documento origem
        
        Returns:
            Lista de resultados, opcionalmente agrupados
        """
        results = self.retrieve(query, collection, top_k)
        
        if not group_by_source:
            return results
        
        # Agrupar por documento fonte
        grouped = {}
        for result in results:
            source_id = result['metadata'].get('source_doc_id', 'unknown')
            if source_id not in grouped:
                grouped[source_id] = []
            grouped[source_id].append(result)
        
        # Flattear de volta mantendo agrupamento
        grouped_results = []
        for source_id, group_results in grouped.items():
            grouped_results.append({
                "source_document": source_id,
                "chunks": group_results,
                "count": len(group_results)
            })
        
        return grouped_results
    
    def get_statistics(self, collection: str = "default") -> Dict[str, Any]:
        """
        Obter estatísticas da coleção.
        
        Args:
            collection: Nome da coleção
        
        Returns:
            Dicionário com estatísticas
        """
        return self.vector_store.get_collection_stats(collection)
