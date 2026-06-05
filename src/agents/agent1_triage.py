"""Agente 1 — Triagem (SPEC-005).

Orquestra três camadas:
    1. Regras determinísticas (`TriageRuleEngine`) — resolve a maioria offline.
    2. LLM fallback (`IntentLLM`, opcional) — quando as regras não bastam.
    3. Política de clarificação — confiança baixa ou diário sem janela temporal.

A detecção de janela temporal (`TemporalExtractor`) roda em paralelo lógico à
classificação e independe da camada que resolveu o intent.

Projeto para teste offline: se nenhum LLM é injetado, o agente degrada para
regras + dateparser e usa a política de clarificação/fallback para o resto.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol

from opentelemetry.trace import Tracer

from src.observability.tracer import get_tracer

from .triage.prompts import clarification_options, clarification_question
from .triage.routing import all_rag_collections, route_for_intent
from .triage.rules import RuleEvaluation, TriageRuleEngine, normalize
from .triage.schemas import (
    ClarificationNeeded,
    TemporalRange,
    TriageOutput,
    TriageResult,
)
from .triage.temporal import TemporalExtractor

# Marcadores que liberam diary_lookup sem janela temporal (SPEC-005 §5.3).
_ALL_MARKERS = ("tudo", "todos", "todas", "qualquer", "geral")


class IntentLLM(Protocol):
    """Contrato do classificador LLM (camada 2). Implementação usa Pydantic AI."""

    async def classify(self, query: str, rule_hint: RuleEvaluation) -> TriageResult: ...


@dataclass
class _Draft:
    """Classificação parcial mutável antes de virar TriageResult/Clarification."""

    intent: Optional[str]
    confidence: float
    target_rag_collections: list[str]
    target_memory_tiers: list[str]
    structured_filters: dict
    classification_method: str
    reasoning: str
    temporal_filter: Optional[TemporalRange] = field(default=None)


class TriageAgent:
    def __init__(
        self,
        rule_engine: Optional[TriageRuleEngine] = None,
        temporal_extractor: Optional[TemporalExtractor] = None,
        llm: Optional[IntentLLM] = None,
        *,
        rules_confidence_threshold: float = 0.7,
        clarify_confidence_threshold: float = 0.6,
        max_clarification_rounds: int = 2,
        tracer: Optional[Tracer] = None,
    ):
        self.rule_engine = rule_engine or TriageRuleEngine()
        self.temporal = temporal_extractor or TemporalExtractor()
        self.llm = llm
        self.rules_threshold = rules_confidence_threshold
        self.clarify_threshold = clarify_confidence_threshold
        self.max_rounds = max_clarification_rounds
        self._tracer = tracer or get_tracer()

    async def triage(self, query: str, clarification_round: int = 0) -> TriageOutput:
        with self._tracer.start_as_current_span("agent1.triage") as span:
            span.set_attribute("query_length", len(query or ""))
            span.set_attribute("clarification_round", clarification_round)

            # Query vazia: clarificação imediata, sem chamar regras/LLM.
            if not query or not query.strip():
                span.set_attribute("intent", "unclear")
                span.set_attribute("classification_method", "none")
                return self._clarification("low_confidence", confidence=0.0)

            draft = await self._classify(query, span)
            draft.temporal_filter = await self._extract_temporal(query, span)

            result = self._apply_clarification_policy(query, draft, clarification_round)

            span.set_attribute("intent", getattr(draft, "intent", None) or "unclear")
            span.set_attribute("confidence_final", draft.confidence)
            span.set_attribute("classification_method", draft.classification_method)
            span.set_attribute("output_kind", result.kind)
            return result

    # -------------------------------------------------------------- camadas 1-2

    async def _classify(self, query: str, parent_span) -> _Draft:
        with self._tracer.start_as_current_span("agent1.rules.evaluate") as rspan:
            rule_eval = self.rule_engine.evaluate(query)
            rspan.set_attribute("rules_fired", rule_eval.fired_rules)
            rspan.set_attribute("confidence", rule_eval.confidence)

        # Regras suficientes → não chama LLM.
        if rule_eval.intent is not None and rule_eval.confidence >= self.rules_threshold:
            return self._draft_from_rules(rule_eval, method="rules")

        # Camada 2: LLM fallback (se disponível).
        if self.llm is not None:
            with self._tracer.start_as_current_span("agent1.llm.classify") as lspan:
                try:
                    llm_result = await self.llm.classify(query, rule_eval)
                    lspan.set_attribute("intent", llm_result.intent)
                    lspan.set_attribute("confidence", llm_result.confidence)
                    method = "hybrid" if rule_eval.intent is not None else "llm"
                    return self._draft_from_llm(llm_result, method)
                except Exception as e:  # best-effort: cai para regras
                    lspan.set_attribute("error", str(e))
                    lspan.set_attribute("success", False)

        # Offline ou LLM falhou: usa o que as regras deram (pode ser intent None).
        return self._draft_from_rules(rule_eval, method="rules")

    def _draft_from_rules(self, rule_eval: RuleEvaluation, method: str) -> _Draft:
        return _Draft(
            intent=rule_eval.intent,
            confidence=rule_eval.confidence,
            target_rag_collections=rule_eval.target_rag_collections,
            target_memory_tiers=rule_eval.target_memory_tiers,
            structured_filters=rule_eval.structured_filters,
            classification_method=method,
            reasoning=rule_eval.reasoning,
        )

    def _draft_from_llm(self, llm_result: TriageResult, method: str) -> _Draft:
        # Re-deriva roteamento a partir do intent (mais confiável que o do 3B).
        collections, tiers = route_for_intent(llm_result.intent)
        return _Draft(
            intent=llm_result.intent,
            confidence=llm_result.confidence,
            target_rag_collections=collections or list(llm_result.target_rag_collections),
            target_memory_tiers=tiers or list(llm_result.target_memory_tiers),
            structured_filters=dict(llm_result.structured_filters),
            classification_method=method,
            reasoning=llm_result.reasoning or "classificado via LLM",
        )

    async def _extract_temporal(self, query: str, parent_span) -> Optional[TemporalRange]:
        with self._tracer.start_as_current_span("agent1.temporal.dateparser") as tspan:
            tr = await self.temporal.extract(query)
            tspan.set_attribute("found", tr is not None)
            if tr is not None:
                tspan.set_attribute("expression", tr.expression)
                tspan.set_attribute("detection_method", tr.detection_method)
            return tr

    # ---------------------------------------------------------- camada 3 (UX)

    def _apply_clarification_policy(
        self, query: str, draft: _Draft, clarification_round: int
    ) -> TriageOutput:
        can_clarify = clarification_round < self.max_rounds

        # (a) Sem intent ou confiança baixa.
        if draft.intent is None or draft.confidence < self.clarify_threshold:
            if can_clarify:
                return self._clarification("low_confidence", confidence=draft.confidence)
            return self._broad_fallback(draft)

        # (b) diary_lookup sem janela temporal (e sem marcador "tudo").
        if (
            draft.intent == "diary_lookup"
            and draft.temporal_filter is None
            and not self._has_all_marker(query)
            and can_clarify
        ):
            return self._clarification("missing_temporal", confidence=draft.confidence)

        return self._to_result(draft)

    def _to_result(self, draft: _Draft) -> TriageResult:
        return TriageResult(
            intent=draft.intent,  # garantido não-None neste ponto
            target_rag_collections=draft.target_rag_collections,
            target_memory_tiers=draft.target_memory_tiers,
            temporal_filter=draft.temporal_filter,
            structured_filters=draft.structured_filters,
            confidence=draft.confidence,
            classification_method=draft.classification_method,
            reasoning=draft.reasoning,
        )

    def _broad_fallback(self, draft: _Draft) -> TriageResult:
        """Fallback amplo após esgotar rodadas de clarificação (SPEC-005 §11)."""
        return TriageResult(
            intent="cross_domain",
            target_rag_collections=all_rag_collections(),
            target_memory_tiers=["episodic_recent"],
            temporal_filter=draft.temporal_filter,
            structured_filters={},
            confidence=draft.confidence,
            classification_method="fallback",
            reasoning="fallback amplo: clarificações esgotadas",
        )

    def _clarification(self, reason: str, confidence: float) -> ClarificationNeeded:
        return ClarificationNeeded(
            reason=reason,
            question=clarification_question(reason),
            detected_options=clarification_options(reason),
            confidence=confidence,
        )

    @staticmethod
    def _has_all_marker(query: str) -> bool:
        norm = normalize(query)
        return any(m in norm for m in _ALL_MARKERS)
