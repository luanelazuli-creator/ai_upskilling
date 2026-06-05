"""
Testes de integração para SPEC-003-1 (Observabilidade e Setup Avançado)
"""

import pytest
import tempfile
import os
import sys
from pathlib import Path

# Adicionar src ao path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestObservabilityModule:
    """Testes para módulo de observabilidade."""
    
    def test_pii_guardrails_sanitization(self):
        """Testar sanitização de PII."""
        from src.memory.guardrails import PIIGuardrails
        
        text = "CPF: 123.456.789-10, Email: test@example.com"
        sanitized = PIIGuardrails.sanitize(text)

        assert "[REDACTED_" in sanitized
        assert "123.456.789-10" not in sanitized
        assert "test@example.com" not in sanitized
    
    def test_pii_extraction(self):
        """Testar extração de PII."""
        from src.memory.guardrails import PIIGuardrails
        
        text = "CPF: 123.456.789-10, Email: test@example.com, Phone: (11) 98765-4321"
        pii = PIIGuardrails.extract_pii(text)
        
        assert "cpf" in pii
        assert "email" in pii
        assert "phone" in pii
    
    def test_pii_has_pii(self):
        """Testar detecção de PII."""
        from src.memory.guardrails import PIIGuardrails
        
        with_pii = "My email is test@example.com"
        without_pii = "This is just plain text"
        
        assert PIIGuardrails.has_pii(with_pii)
        assert not PIIGuardrails.has_pii(without_pii)


class TestRAGModule:
    """Testes para módulo RAG."""
    
    def test_document_chunker_basic(self):
        """Testar chunking básico de documento."""
        from src.rag.vectorizer import DocumentChunker
        
        chunker = DocumentChunker(chunk_size=100, chunk_overlap=20)
        text = "Este é um texto longo que será dividido em chunks. " * 3
        chunks = chunker.chunk_by_size(text, {"source": "test"})
        
        assert len(chunks) > 1
        assert all("content" in c for c in chunks)
        assert all("metadata" in c for c in chunks)
    
    def test_document_chunker_statistics(self):
        """Testar estatísticas de chunking."""
        from src.rag.vectorizer import DocumentChunker
        
        chunker = DocumentChunker()
        text = "A" * 5000
        chunks = chunker.chunk_by_size(text)
        stats = chunker.get_chunk_statistics(chunks)
        
        assert stats["total_chunks"] > 0
        assert stats["total_chars"] >= len(text)
        assert stats["avg_chunk_size"] > 0
    
    def test_semantic_retriever_initialization(self):
        """Testar inicialização de retriever semântico."""
        from src.rag.retriever import SemanticRetriever
        
        # ignore_cleanup_errors: o ChromaDB mantém chroma.sqlite3 aberto e o
        # Windows não permite remover o tempdir enquanto isso (WinError 32).
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            # SPEC-004 §8: SemanticRetriever é retrieval-only; o chunking vive
            # na IngestionPipeline. Por isso não há mais `chunker` aqui.
            retriever = SemanticRetriever(db_path=tmpdir)
            assert retriever is not None
            assert retriever.vector_store is not None


# TestMemoryModule (SemanticMemory) foi removido: a API antiga
# (storage_path, keywords, search_by_keyword, total_concepts) foi substituída
# pela SPEC-003-2 e a cobertura vive em tests/test_spec_003_2.py.


class TestIntegration:
    """Testes de integração end-to-end."""
    
    def test_full_pipeline(self):
        """Pipeline mínimo (PII + chunking) sem SemanticMemory.

        Após SPEC-003-2, SemanticMemory exige um VectorStore (ChromaDB),
        portanto não cabe mais neste teste de smoke. O encaixe completo
        sanitização -> chunking -> persistência vive em test_spec_003_2.py
        e test_spec_004.py.
        """
        from src.memory.guardrails import PIIGuardrails
        from src.rag.vectorizer import DocumentChunker

        raw_text = "Usuário: João Silva, CPF: 123.456.789-10, Email: joao@example.com"
        sanitized = PIIGuardrails.sanitize(raw_text)
        assert "[REDACTED_" in sanitized

        chunker = DocumentChunker(chunk_size=200, chunk_overlap=50)
        chunks = chunker.chunk_by_size(sanitized)
        assert len(chunks) > 0
    
    def test_modules_independent(self):
        """Testar que módulos funcionam independentemente."""
        # Importar cada módulo
        from src.memory.guardrails import PIIGuardrails
        from src.memory.semantic import SemanticMemory
        from src.memory.episodic import EpisodicMemory
        from src.rag.vectorizer import DocumentChunker
        from src.rag.retriever import SemanticRetriever
        
        # Todos devem estar importáveis
        assert PIIGuardrails is not None
        assert DocumentChunker is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
