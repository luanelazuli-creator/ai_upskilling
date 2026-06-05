"""Módulo RAG - Vector Store, ingestão e busca semântica local (SPEC-004)."""

from .chunking import Chunk, chunk_document
from .embedder import get_embedding_function
from .ingest import FileReport, IngestionPipeline, IngestionReport
from .retriever import RAGChunk, SemanticRetriever
from .store import VectorStore
from .vectorizer import DocumentChunker

__all__ = [
    "VectorStore",
    "DocumentChunker",
    "SemanticRetriever",
    "RAGChunk",
    "IngestionPipeline",
    "IngestionReport",
    "FileReport",
    "Chunk",
    "chunk_document",
    "get_embedding_function",
]
