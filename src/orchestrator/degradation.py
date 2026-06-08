"""Wrappers best-effort com avisos OTel (SPEC-008 §9).

Toda função `safe_*` captura exceções, emite atributo OTel e devolve um
valor de fallback. Nenhuma silencia em silêncio.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from opentelemetry.trace import Tracer

from src.agents.triage.schemas import (
    ClarificationNeeded,
    TemporalRange,
    TriageOutput,
    TriageResult,
)
from src.agents.synthesis.schemas import NoEvidence, SynthesisOutput
from src.memory.episodic import ConversationRecord, EpisodicMemory
from src.memory.semantic import Fact, SemanticMemory
from src.observability.tracer import get_tracer
from src.rag.retriever import RAGChunk, SemanticRetriever


# -------------------------------------------------------------------- triagem


def _broad_fallback(query_len: int) -> TriageResult:
    return TriageResult(
        intent="cross_domain",
        target_rag_collections=["diario", "cursos", "referencias"],
        target_memory_tiers=["episodic_recent"],
        temporal_filter=None,
        structured_filters={},
        confidence=0.0,
        classification_method="fallback",
        reasoning="fallback amplo: triagem falhou",
    )


async def safe_triage(
    triage_agent,
    query: str,
    *,
    timeout_s: float = 10.0,
    tracer: Optional[Tracer] = None,
) -> TriageOutput:
    tr = tracer or get_tracer()
    try:
        return await asyncio.wait_for(
            triage_agent.triage(query, clarification_round=0), timeout=timeout_s
        )
    except asyncio.TimeoutError:
        with tr.start_as_current_span("orchestrator.triage.timeout_fallback") as s:
            s.set_attribute("timeout_s", timeout_s)
        return _broad_fallback(len(query or ""))
    except Exception as e:
        with tr.start_as_current_span(
            "orchestrator.triage.invalid_output_fallback"
        ) as s:
            s.set_attribute("error", str(e))
        return _broad_fallback(len(query or ""))


# ------------------------------------------------------ adapter de filtros


def temporal_to_filters(
    temporal: Optional[TemporalRange],
    structured_filters: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Converte temporal+structured em um único `filters: dict` para o retriever.

    O `SemanticRetriever.retrieve(...)` aceita `filters` como `where` do Chroma.
    Chaves temporais ficam em `date_gte`/`date_lte` (convenção do MVP). Se a
    coleção alvo não indexa essas chaves, o filtro é silenciosamente ignorado
    pelo Chroma — comportamento aceitável para best-effort.
    """
    filters: Dict[str, Any] = {}
    if structured_filters:
        filters.update(structured_filters)
    if temporal is not None:
        filters["date_gte"] = temporal.start.isoformat()
        filters["date_lte"] = temporal.end.isoformat()
    return filters or None


# ------------------------------------------------------------------ retrieval


def safe_rag_search(
    retriever: SemanticRetriever,
    collection: str,
    query: str,
    top_k: int,
    filters: Optional[Dict[str, Any]] = None,
    *,
    tracer: Optional[Tracer] = None,
) -> Tuple[List[RAGChunk], bool]:
    """Retorna (chunks, ok). `ok=False` quando a coleção falhou."""
    tr = tracer or get_tracer()
    with tr.start_as_current_span("orchestrator.retrieval.rag") as span:
        span.set_attribute("collection", collection)
        try:
            chunks = retriever.retrieve(
                query=query, collection=collection, top_k=top_k, filters=filters
            )
            span.set_attribute("chunks", len(chunks))
            return chunks, True
        except Exception as e:
            # Best-effort: alguns filtros invalidam where do Chroma; tenta sem.
            try:
                chunks = retriever.retrieve(
                    query=query, collection=collection, top_k=top_k, filters=None
                )
                span.set_attribute("chunks", len(chunks))
                span.set_attribute("filter_dropped", True)
                span.set_attribute("error", str(e))
                return chunks, True
            except Exception as e2:
                span.set_attribute("chunks", 0)
                span.set_attribute("success", False)
                span.set_attribute("error", str(e2))
                with tr.start_as_current_span(
                    "orchestrator.retrieval.rag_collection_failed"
                ) as s2:
                    s2.set_attribute("collection", collection)
                    s2.set_attribute("error", str(e2))
                return [], False


def safe_episodic_recent(
    episodic: EpisodicMemory,
    user_id: str,
    n: int,
    *,
    tracer: Optional[Tracer] = None,
) -> List[ConversationRecord]:
    tr = tracer or get_tracer()
    with tr.start_as_current_span("orchestrator.retrieval.episodic") as span:
        span.set_attribute("mode", "recent")
        try:
            recs = episodic.get_recent(user_id=user_id, n=n)
            span.set_attribute("records", len(recs))
            return recs
        except Exception as e:
            span.set_attribute("success", False)
            span.set_attribute("error", str(e))
            return []


def safe_episodic_semantic(
    episodic: EpisodicMemory,
    user_id: str,
    query: str,
    top_k: int,
    time_window: Optional[Tuple[datetime, datetime]] = None,
    *,
    tracer: Optional[Tracer] = None,
) -> List[ConversationRecord]:
    tr = tracer or get_tracer()
    with tr.start_as_current_span("orchestrator.retrieval.episodic") as span:
        span.set_attribute("mode", "semantic")
        try:
            recs = episodic.search_semantic(
                user_id=user_id, query=query, top_k=top_k, time_window=time_window
            )
            span.set_attribute("records", len(recs))
            return recs
        except Exception as e:
            span.set_attribute("success", False)
            span.set_attribute("error", str(e))
            return []


def safe_semantic_search(
    semantic: SemanticMemory,
    user_id: str,
    query: str,
    top_k: int,
    *,
    tracer: Optional[Tracer] = None,
) -> List[Fact]:
    tr = tracer or get_tracer()
    with tr.start_as_current_span("orchestrator.retrieval.semantic") as span:
        try:
            facts = semantic.search(user_id=user_id, query=query, top_k=top_k)
            span.set_attribute("facts", len(facts))
            return facts
        except Exception as e:
            span.set_attribute("success", False)
            span.set_attribute("error", str(e))
            return []


# -------------------------------------------------------------------- síntese


async def safe_synthesize(
    synthesis_agent,
    query: str,
    bundle,
    *,
    timeout_s: float = 30.0,
    used_intent: str = "unknown",
    tracer: Optional[Tracer] = None,
) -> SynthesisOutput:
    tr = tracer or get_tracer()
    try:
        return await asyncio.wait_for(
            synthesis_agent.synthesize(query, bundle), timeout=timeout_s
        )
    except asyncio.TimeoutError:
        with tr.start_as_current_span("orchestrator.synthesis.timeout") as s:
            s.set_attribute("timeout_s", timeout_s)
        return NoEvidence(
            reason="off_topic",
            suggestion="LLM indisponível no momento.",
            used_intent=used_intent,
        )


def temporal_to_time_window(
    temporal: Optional[TemporalRange],
) -> Optional[Tuple[datetime, datetime]]:
    """Conversão direta para o `time_window` aceito por `search_semantic`."""
    if temporal is None:
        return None
    return (temporal.start, temporal.end)
