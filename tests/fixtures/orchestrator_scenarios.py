"""Cenários e fakes para os testes do Orquestrador (SPEC-008 §14).

Padrão: mocks dos agentes (TriageAgent, SynthesisAgent) + fakes in-memory das
memórias e do retriever. Smoke real com Ollama fica em testes marcados
`@pytest.mark.ollama` no test_spec_008.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.agents.synthesis.schemas import (
    NoEvidence,
    SynthesisOutput,
    SynthesisResult,
)
from src.agents.triage.schemas import (
    ClarificationNeeded,
    TriageOutput,
    TriageResult,
)
from src.memory.context_bundle import ContextBundle
from src.memory.episodic import ConversationRecord
from src.memory.semantic import Fact
from src.rag.retriever import RAGChunk


# ----------------------------------------------------------------- agentes


class FakeTriageAgent:
    """Devolve um output pré-configurado e contabiliza chamadas."""

    def __init__(self, output: TriageOutput, *, raise_exc: Optional[Exception] = None):
        self.output = output
        self.raise_exc = raise_exc
        self.calls = 0
        self.last_query: Optional[str] = None

    async def triage(self, query: str, clarification_round: int = 0) -> TriageOutput:
        self.calls += 1
        self.last_query = query
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.output


class FakeSynthesisAgent:
    def __init__(
        self,
        output: SynthesisOutput,
        *,
        raise_exc: Optional[Exception] = None,
    ):
        self.output = output
        self.raise_exc = raise_exc
        self.calls = 0
        self.last_bundle: Optional[ContextBundle] = None

    async def synthesize(
        self, query: str, bundle: ContextBundle
    ) -> SynthesisOutput:
        self.calls += 1
        self.last_bundle = bundle
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.output


# ------------------------------------------------------------- memórias fake


class FakeRetriever:
    """Mapa coleção -> chunks. `fail_collections` força exceções."""

    def __init__(
        self,
        chunks_by_collection: Optional[Dict[str, List[RAGChunk]]] = None,
        fail_collections: Optional[set] = None,
    ):
        self._chunks = chunks_by_collection or {}
        self._fail = fail_collections or set()
        self.calls: List[Tuple[str, str, int]] = []

    def retrieve(
        self,
        query: str,
        collection: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[RAGChunk]:
        self.calls.append((collection, query, top_k))
        if collection in self._fail:
            raise RuntimeError(f"coleção {collection} indisponível")
        return list(self._chunks.get(collection, []))[:top_k]


class FakeEpisodic:
    def __init__(self):
        self.records: List[Dict[str, Any]] = []
        self.fail_recent = False
        self.fail_semantic = False
        self.fail_add = False
        self.search_results: List[ConversationRecord] = []
        self.recent_results: List[ConversationRecord] = []

    def add_conversation(
        self,
        *,
        user_id: str,
        session_id: str,
        user_message: str,
        agent_response: str,
        pii_sanitized: bool,
        intent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        if self.fail_add:
            raise RuntimeError("episodic add falhou")
        cid = f"conv_{uuid.uuid4().hex}"
        self.records.append(
            {
                "id": cid,
                "user_id": user_id,
                "session_id": session_id,
                "user_message": user_message,
                "agent_response": agent_response,
                "pii_sanitized": pii_sanitized,
                "intent": intent,
                "metadata": metadata or {},
            }
        )
        return cid

    def get_recent(self, user_id: str, n: int = 5) -> List[ConversationRecord]:
        if self.fail_recent:
            raise RuntimeError("episodic recent falhou")
        return list(self.recent_results)[:n]

    def search_semantic(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        time_window: Optional[Tuple[datetime, datetime]] = None,
    ) -> List[ConversationRecord]:
        if self.fail_semantic:
            raise RuntimeError("episodic semantic falhou")
        return list(self.search_results)[:top_k]


class FakeSemantic:
    def __init__(self):
        self.results: List[Fact] = []
        self.fail = False

    def search(self, user_id: str, query: str, top_k: int = 3) -> List[Fact]:
        if self.fail:
            raise RuntimeError("semantic falhou")
        return list(self.results)[:top_k]


# ---------------------------------------------------------------- builders


def make_triage_result(
    intent: str = "diary_lookup",
    collections: Optional[List[str]] = None,
    tiers: Optional[List[str]] = None,
    confidence: float = 0.9,
    classification_method: str = "rules",
) -> TriageResult:
    return TriageResult(
        intent=intent,  # type: ignore[arg-type]
        target_rag_collections=collections or ["diario"],  # type: ignore[arg-type]
        target_memory_tiers=tiers or [],  # type: ignore[arg-type]
        confidence=confidence,
        classification_method=classification_method,  # type: ignore[arg-type]
        reasoning="test",
    )


def make_clarification(
    question: str = "Sobre qual fonte você quer saber?",
) -> ClarificationNeeded:
    return ClarificationNeeded(
        reason="low_confidence",
        question=question,
        detected_options=["diário", "cursos"],
        confidence=0.2,
    )


def make_synthesis_result(
    answer: str = "Você terminou o módulo 4 [chunk_de_001].",
    intent: str = "diary_lookup",
) -> SynthesisResult:
    return SynthesisResult(
        kind="synthesis_result",
        answer=answer,
        citations=[],
        confidence=0.85,
        used_intent=intent,
    )


def make_no_evidence(
    reason: str = "empty_bundle", intent: str = "diary_lookup"
) -> NoEvidence:
    return NoEvidence(
        reason=reason,  # type: ignore[arg-type]
        suggestion="sem evidência.",
        used_intent=intent,
    )


def make_chunk(
    chunk_id: str = "chunk_001",
    content: str = "Você terminou o módulo 4 do Data Engineer no dia 11.",
    collection: str = "diario",
    relevance_score: float = 0.78,
) -> RAGChunk:
    return RAGChunk(
        id=chunk_id,
        content=content,
        collection=collection,
        relevance_score=relevance_score,
        metadata={"source_file": "Dia 11.docx"},
    )


def make_conversation_record(
    user_message: str = "ontem o que fiz?",
    agent_response: str = "você terminou o módulo 4",
) -> ConversationRecord:
    return ConversationRecord(
        id=f"conv_{uuid.uuid4().hex}",
        user_id="luane",
        session_id="s_test",
        timestamp=datetime.now(timezone.utc),
        intent="diary_lookup",
        pii_sanitized=True,
        user_message=user_message,
        agent_response=agent_response,
    )


def make_fact_obj(
    content: str = "Prefere respostas curtas",
    confidence: float = 0.9,
) -> Fact:
    return Fact(
        fact_id=f"fact_{uuid.uuid4().hex}",
        user_id="luane",
        content=content,
        category="preference",
        source_conversation_id=None,
        confidence=confidence,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
