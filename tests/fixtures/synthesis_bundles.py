"""Bundles mockados para os testes do Agente 2 (SPEC-006 §12).

Cada helper retorna um `ContextBundle` controlado, sem depender de ChromaDB
ou dados reais. Os testes unitários só precisam destes constructors.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from src.memory.context_bundle import ContextBundle
from src.memory.episodic import ConversationRecord
from src.memory.semantic import Fact
from src.memory.working import WorkingItem
from src.rag.retriever import RAGChunk

# -------------------------------------------------- builders de itens isolados


def make_chunk(
    chunk_id: str = "chunk_de_001",
    content: str = "Você terminou o módulo 4 do Data Engineer no dia 11.",
    collection: str = "diario",
    relevance_score: float = 0.78,
    source_file: str = "Dia 11.docx",
) -> RAGChunk:
    return RAGChunk(
        id=chunk_id,
        content=content,
        collection=collection,
        relevance_score=relevance_score,
        metadata={"source_file": source_file},
    )


def make_fact(
    fact_id: str = "f_42",
    content: str = "Prefiro respostas curtas e diretas.",
    category: str = "preference",
    confidence: float = 0.91,
    user_id: str = "luane",
) -> Fact:
    return Fact(
        fact_id=fact_id,
        user_id=user_id,
        content=content,
        category=category,
        source_conversation_id=None,
        confidence=confidence,
        timestamp=datetime(2026, 6, 1, tzinfo=timezone.utc).isoformat(),
    )


def make_conversation(
    conv_id: str = "conv_abc",
    user_message: str = "ontem comecei o módulo 5",
    agent_response: str = "anotado, módulo 5 iniciado",
    intent: Optional[str] = "diary_lookup",
) -> ConversationRecord:
    return ConversationRecord(
        id=conv_id,
        user_id="luane",
        session_id="s_test",
        timestamp=datetime(2026, 6, 10, 9, 0, tzinfo=timezone.utc),
        intent=intent,
        pii_sanitized=True,
        user_message=user_message,
        agent_response=agent_response,
    )


def make_working_item(
    content: str = "o que fiz no dia 11",
    importance: float = 1.0,
    source: str = "user",
) -> WorkingItem:
    return WorkingItem(
        content=content,
        importance=importance,
        source=source,  # type: ignore[arg-type]
        timestamp=datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------- bundles pré-configurados


def empty_bundle(intent: str = "diary_lookup") -> ContextBundle:
    """Bundle vazio: pré-check deve devolver NoEvidence(empty_bundle)."""
    return ContextBundle(metadata={"intent": intent})


def low_relevance_bundle(intent: str = "diary_lookup") -> ContextBundle:
    """Bundle com chunks de relevância abaixo do limiar default (0.25)."""
    return ContextBundle(
        rag_chunks=[
            make_chunk(chunk_id="chunk_lo_1", relevance_score=0.10),
            make_chunk(chunk_id="chunk_lo_2", relevance_score=0.18),
        ],
        metadata={"intent": intent},
    )


def diary_bundle(intent: str = "diary_lookup") -> ContextBundle:
    """Bundle típico de consulta ao diário com 2 chunks acima do limiar."""
    return ContextBundle(
        working=[make_working_item()],
        recent_episodic=[make_conversation()],
        semantic_facts=[make_fact()],
        rag_chunks=[
            make_chunk(
                chunk_id="chunk_de_001",
                content="Você terminou o módulo 4 do Data Engineer no dia 11.",
                relevance_score=0.78,
                source_file="Dia 11.docx",
            ),
            make_chunk(
                chunk_id="chunk_de_002",
                content="Pendência: revisar exercício do módulo 4.",
                relevance_score=0.62,
                source_file="Dia 11.docx",
            ),
        ],
        metadata={"intent": intent, "turn": 1, "session_id": "s_test"},
    )


def facts_only_bundle(intent: str = "user_profile") -> ContextBundle:
    """Bundle sem RAG, só fatos — caminho de personalização (user_profile)."""
    return ContextBundle(
        semantic_facts=[
            make_fact(fact_id="f_42", content="Prefiro respostas curtas."),
            make_fact(
                fact_id="f_43",
                content="Trabalho com Data Engineering há 3 anos.",
                category="background",
            ),
        ],
        metadata={"intent": intent},
    )
