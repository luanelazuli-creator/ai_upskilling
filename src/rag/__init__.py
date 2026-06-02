"""
Módulo RAG - Vector Store e busca semântica local
"""

from .store import VectorStore
from .vectorizer import DocumentChunker
from .retriever import SemanticRetriever

__all__ = [
    "VectorStore",
    "DocumentChunker",
    "SemanticRetriever",
]
