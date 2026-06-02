"""
Document Chunker - Estratégia de chunking para documentos
"""

from typing import List, Dict, Any, Optional


class DocumentChunker:
    """
    Divide documentos em chunks com overlapping.
    
    Útil para:
    - Indexar documentos grandes em pedaços menores
    - Manter contexto entre chunks
    - Melhorar precisão de busca semântica
    """
    
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        separator: str = "\n\n"
    ):
        """
        Inicializar chunker.
        
        Args:
            chunk_size: Tamanho máximo de cada chunk (caracteres)
            chunk_overlap: Sobreposição entre chunks (caracteres)
            separator: Separador preferido para dividir (ex: parágrafo)
        """
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap deve ser menor que chunk_size")
        
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separator = separator
    
    def chunk_document(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Dividir documento em chunks com overlapping.
        
        Args:
            content: Conteúdo do documento
            metadata: Metadados do documento original
        
        Returns:
            Lista de chunks com metadata
        """
        if metadata is None:
            metadata = {}
        
        chunks = []
        
        # Tentar dividir por separador primeiro
        paragraphs = content.split(self.separator)
        current_chunk = ""
        chunk_index = 0
        
        for para in paragraphs:
            # Se adicionar o parágrafo ultrapassaria o tamanho
            if len(current_chunk) + len(para) > self.chunk_size and current_chunk:
                # Salvar chunk atual
                chunk_metadata = {
                    **metadata,
                    "chunk_index": chunk_index,
                    "chunk_size": len(current_chunk),
                    "chunk_start_char": len(self.separator.join(
                        [p for p in paragraphs[:paragraphs.index(para)]]
                    ))
                }
                chunks.append({
                    "content": current_chunk.strip(),
                    "metadata": chunk_metadata
                })
                
                # Começar novo chunk com overlapping
                overlap_size = 0
                overlap_content = ""
                for j in range(len(current_chunk) - 1, -1, -1):
                    if overlap_size >= self.chunk_overlap:
                        break
                    overlap_content = current_chunk[j] + overlap_content
                    overlap_size += 1
                
                current_chunk = overlap_content + self.separator + para
                chunk_index += 1
            else:
                if current_chunk:
                    current_chunk += self.separator + para
                else:
                    current_chunk = para
        
        # Adicionar último chunk
        if current_chunk:
            chunk_metadata = {
                **metadata,
                "chunk_index": chunk_index,
                "chunk_size": len(current_chunk),
                "is_last": True
            }
            chunks.append({
                "content": current_chunk.strip(),
                "metadata": chunk_metadata
            })
        
        return chunks
    
    def chunk_by_size(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Chunking simples por tamanho fixo (sem separador).
        
        Args:
            content: Conteúdo do documento
            metadata: Metadados do documento
        
        Returns:
            Lista de chunks
        """
        if metadata is None:
            metadata = {}
        
        chunks = []
        step = self.chunk_size - self.chunk_overlap
        
        for i in range(0, len(content), step):
            chunk_text = content[i:i + self.chunk_size]
            chunk_metadata = {
                **metadata,
                "chunk_index": i // step,
                "chunk_start": i,
                "chunk_end": min(i + self.chunk_size, len(content)),
                "chunk_size": len(chunk_text)
            }
            chunks.append({
                "content": chunk_text,
                "metadata": chunk_metadata
            })
        
        return chunks
    
    def get_chunk_statistics(self, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Obter estatísticas dos chunks.
        
        Args:
            chunks: Lista de chunks
        
        Returns:
            Dicionário com estatísticas
        """
        if not chunks:
            return {
                "total_chunks": 0,
                "total_chars": 0,
                "avg_chunk_size": 0,
                "min_chunk_size": 0,
                "max_chunk_size": 0
            }
        
        sizes = [len(c["content"]) for c in chunks]
        
        return {
            "total_chunks": len(chunks),
            "total_chars": sum(sizes),
            "avg_chunk_size": sum(sizes) // len(sizes),
            "min_chunk_size": min(sizes),
            "max_chunk_size": max(sizes)
        }
