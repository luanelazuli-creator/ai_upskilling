from src.memory.guardrails import PIIGuardrails
from src.rag.vectorizer import DocumentChunker
from src.memory.semantic import SemanticMemory
import tempfile, os

print("✓ PIIGuardrails:", PIIGuardrails.sanitize("Email: test@example.com"))
print("✓ DocumentChunker:", len(DocumentChunker().chunk_by_size("A"*500)))
mem = SemanticMemory(storage_path=f"{tempfile.gettempdir()}/mem.json")
mem.add_fact("f1", "Teste", keywords=["test"])
print("✓ SemanticMemory:", len(mem.search_by_keyword("test")))
print("\n✅ Todos os módulos funcionando!")