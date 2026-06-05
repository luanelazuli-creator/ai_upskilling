"""Chunking adaptativo por domínio (SPEC-004 §4).

Estratégias:
    - whole_file:   diário e golden_prompts (1 arquivo = 1 chunk).
    - standard:     cursos/manuais longos (chunking por tamanho com overlap).
    - row_per_line: planilhas (1 linha = 1 chunk, colunas viram metadata).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .preprocessing.domains import DocumentProfile
from .preprocessing.loaders import RawDocument
from .vectorizer import DocumentChunker


@dataclass
class Chunk:
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


def chunk_document(
    raw: RawDocument,
    profile: DocumentProfile,
    body: str,
    base_metadata: Dict[str, Any],
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> List[Chunk]:
    """Aplica a estratégia de chunking adequada ao perfil do documento."""
    strategy = profile.chunk_strategy

    if strategy == "whole_file":
        return [_whole_file_chunk(body, base_metadata)]

    if strategy == "row_per_line":
        return _row_chunks(raw, base_metadata)

    # standard
    return _standard_chunks(body, base_metadata, chunk_size, chunk_overlap)


def _whole_file_chunk(body: str, base_metadata: Dict[str, Any]) -> Chunk:
    meta = {**base_metadata, "chunk_index": 0, "chunk_strategy": "whole_file"}
    return Chunk(content=body.strip(), metadata=meta)


def _standard_chunks(
    body: str, base_metadata: Dict[str, Any], chunk_size: int, chunk_overlap: int
) -> List[Chunk]:
    chunker = DocumentChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    raw_chunks = chunker.chunk_document(body, metadata={})
    chunks: List[Chunk] = []
    for i, rc in enumerate(raw_chunks):
        meta = {
            **base_metadata,
            "chunk_index": i,
            "chunk_strategy": "standard",
        }
        chunks.append(Chunk(content=rc["content"], metadata=meta))
    return chunks


def _row_chunks(raw: RawDocument, base_metadata: Dict[str, Any]) -> List[Chunk]:
    """Cada linha vira um chunk; colunas viram `field_<col>` em metadata."""
    chunks: List[Chunk] = []
    rows = raw.rows or []
    for i, row in enumerate(rows):
        # Conteúdo textual da linha: "Col: val. Col2: val2."
        parts = [
            f"{col}: {row.get(col, '')}".strip()
            for col in raw.columns
            if str(row.get(col, "")).strip()
        ]
        content = ". ".join(parts)
        if not content:
            continue
        meta = {
            **base_metadata,
            "chunk_index": i,
            "chunk_strategy": "row_per_line",
            "row_index": i,
        }
        for col in raw.columns:
            value = row.get(col, "")
            # ChromaDB só aceita escalares em metadata.
            if isinstance(value, (str, int, float, bool)):
                meta[f"field_{_slug(col)}"] = value
            else:
                meta[f"field_{_slug(col)}"] = str(value)
        chunks.append(Chunk(content=content, metadata=meta))
    return chunks


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text.lower()).strip("_")
