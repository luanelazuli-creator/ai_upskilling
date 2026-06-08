"""ContextBuilder — montagem do ContextBundle com orçamento de tokens.

SPEC-008 §5.5 / SPEC-MEM §5.2. Heurística simples (`len // 4`), alocação por
seção e rollover de sobra Working → RAG.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from opentelemetry.trace import Tracer

from src.agents.triage.schemas import TriageResult
from src.memory.context_bundle import ContextBundle
from src.memory.episodic import ConversationRecord
from src.memory.semantic import Fact
from src.memory.working import WorkingItem
from src.observability.tracer import get_tracer
from src.rag.retriever import RAGChunk

# Alocação por seção (SPEC-MEM §5.2 / SPEC-008 §5.5.1 passo 2).
SECTION_RATIOS = {
    "working": 0.10,
    "episodic": 0.20,
    "semantic": 0.20,
    "rag": 0.40,
    "reserva": 0.10,
}


def _approx_tokens(text: str) -> int:
    """Heurística PT-BR (§5.5.1): tokens ≈ len // 4. Aceita ±15% no MVP."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _episodic_text(rec: ConversationRecord) -> str:
    return f"{rec.user_message} {rec.agent_response}"


class ContextBuilder:
    def __init__(self, tracer: Optional[Tracer] = None):
        self._tracer = tracer or get_tracer()

    def build(
        self,
        *,
        query: str,
        triage: TriageResult,
        working: Sequence[WorkingItem],
        recent_episodic: Sequence[ConversationRecord],
        semantic_facts: Sequence[Fact],
        rag_chunks: Sequence[RAGChunk],
        token_budget: int,
        session_id: str,
        turn: int,
        failed_collections: Optional[List[str]] = None,
    ) -> ContextBundle:
        with self._tracer.start_as_current_span("orchestrator.build_context") as span:
            span.set_attribute("token_budget", token_budget)
            span.set_attribute("input_working", len(working))
            span.set_attribute("input_episodic", len(recent_episodic))
            span.set_attribute("input_semantic", len(semantic_facts))
            span.set_attribute("input_rag", len(rag_chunks))

            budgets = {
                k: int(token_budget * v) for k, v in SECTION_RATIOS.items()
            }

            kept_working, used_w, dropped_w = self._fit_working(
                working, budgets["working"]
            )
            kept_episodic, used_e, dropped_e = self._fit_episodic(
                recent_episodic, budgets["episodic"]
            )
            kept_semantic, used_s, dropped_s = self._fit_semantic(
                semantic_facts, budgets["semantic"]
            )

            # Rollover: sobra de Working entra no RAG (§5.5.1 passo 4).
            # Episodic/Semantic não cedem para RAG.
            rag_budget = budgets["rag"] + (budgets["working"] - used_w)
            kept_rag, used_r, dropped_r = self._fit_rag(rag_chunks, rag_budget)

            tokens_per_section = {
                "working": used_w,
                "episodic": used_e,
                "semantic": used_s,
                "rag": used_r,
            }
            dropped_per_section = {
                "working": dropped_w,
                "episodic": dropped_e,
                "semantic": dropped_s,
                "rag": dropped_r,
            }
            tokens_estimated = sum(tokens_per_section.values())

            span.set_attribute("tokens_estimated", tokens_estimated)
            for k, v in tokens_per_section.items():
                span.set_attribute(f"tokens.{k}", v)
            for k, v in dropped_per_section.items():
                span.set_attribute(f"dropped.{k}", v)

            metadata: Dict[str, Any] = {
                "intent": triage.intent,
                "temporal_filter": triage.temporal_filter,
                "tokens_estimated": tokens_estimated,
                "tokens_per_section": tokens_per_section,
                "dropped_per_section": dropped_per_section,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "session_id": session_id,
                "turn": turn,
            }
            if failed_collections:
                metadata["failed_collections"] = list(failed_collections)

            return ContextBundle(
                working=list(kept_working),
                recent_episodic=list(kept_episodic),
                semantic_facts=list(kept_semantic),
                rag_chunks=list(kept_rag),
                metadata=metadata,
            )

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _fit_generic(
        items: Sequence[Any],
        key_fn,
        text_fn,
        budget: int,
    ):
        """Ordena desc por `key_fn` e mantém até estourar o budget."""
        ordered = sorted(items, key=key_fn, reverse=True)
        kept = []
        used = 0
        dropped = 0
        for it in ordered:
            t = _approx_tokens(text_fn(it))
            if used + t <= budget:
                kept.append(it)
                used += t
            else:
                dropped += 1
        return kept, used, dropped

    def _fit_working(self, items, budget):
        return self._fit_generic(
            items,
            key_fn=lambda it: (it.importance, it.timestamp),
            text_fn=lambda it: it.content,
            budget=budget,
        )

    def _fit_episodic(self, items, budget):
        return self._fit_generic(
            items,
            key_fn=lambda r: r.timestamp,
            text_fn=_episodic_text,
            budget=budget,
        )

    def _fit_semantic(self, items, budget):
        return self._fit_generic(
            items,
            key_fn=lambda f: f.confidence,
            text_fn=lambda f: f.content,
            budget=budget,
        )

    def _fit_rag(self, items, budget):
        return self._fit_generic(
            items,
            key_fn=lambda c: (c.relevance_score or 0.0),
            text_fn=lambda c: c.content,
            budget=budget,
        )
