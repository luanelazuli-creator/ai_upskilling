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
        
        assert "[REDACTED]" in sanitized
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
        
        with tempfile.TemporaryDirectory() as tmpdir:
            retriever = SemanticRetriever(db_path=tmpdir)
            assert retriever is not None
            assert retriever.vector_store is not None
            assert retriever.chunker is not None


class TestMemoryModule:
    """Testes para módulo de memória."""
    
    def test_semantic_memory_add_fact(self):
        """Testar adição de fatos."""
        from src.memory.semantic import SemanticMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = SemanticMemory(storage_path=os.path.join(tmpdir, "mem.json"))
            
            memory.add_fact(
                "fact_1",
                "Python é versátil",
                keywords=["python", "programming"],
                confidence=0.95
            )
            
            fact = memory.get_fact("fact_1")
            assert fact is not None
            assert fact["content"] == "Python é versátil"
    
    def test_semantic_memory_search(self):
        """Testar busca de fatos."""
        from src.memory.semantic import SemanticMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = SemanticMemory(storage_path=os.path.join(tmpdir, "mem.json"))
            
            memory.add_fact("f1", "IA é o futuro", keywords=["ai", "future"])
            memory.add_fact("f2", "Machine learning", keywords=["ml", "learning"])
            
            results = memory.search_by_keyword("ai")
            assert len(results) == 1
            assert results[0]["id"] == "f1"
    
    def test_semantic_memory_statistics(self):
        """Testar estatísticas de memória."""
        from src.memory.semantic import SemanticMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = SemanticMemory(storage_path=os.path.join(tmpdir, "mem.json"))
            
            memory.add_fact("f1", "Fato 1", keywords=["key1"])
            memory.add_fact("f2", "Fato 2", keywords=["key2", "key3"])
            
            stats = memory.get_statistics()
            assert stats["total_facts"] == 2
            assert stats["total_concepts"] == 3


class TestIntegration:
    """Testes de integração end-to-end."""
    
    def test_full_pipeline(self):
        """Testar pipeline completo de processamento."""
        from src.memory.guardrails import PIIGuardrails
        from src.rag.vectorizer import DocumentChunker
        from src.memory.semantic import SemanticMemory
        
        # 1. Sanitizar texto
        raw_text = "Usuário: João Silva, CPF: 123.456.789-10, Email: joao@example.com"
        sanitized = PIIGuardrails.sanitize(raw_text)
        assert "[REDACTED]" in sanitized
        
        # 2. Chunking
        chunker = DocumentChunker(chunk_size=200)
        chunks = chunker.chunk_by_size(sanitized)
        assert len(chunks) > 0
        
        # 3. Memória semântica
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = SemanticMemory(storage_path=os.path.join(tmpdir, "mem.json"))
            
            for i, chunk in enumerate(chunks):
                memory.add_fact(
                    f"chunk_{i}",
                    chunk["content"],
                    keywords=["processed", "sanitized"],
                    confidence=0.9
                )
            
            results = memory.search_by_keyword("processed")
            assert len(results) == len(chunks)
    
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
