"""Agente 2 — Síntese e Resposta Ancorada (SPEC-006).

Orquestra três etapas:
    1. Pré-check: se o bundle vem vazio ou com relevância máxima abaixo do
       limiar, devolve `NoEvidence` SEM chamar o LLM.
    2. LLM (`SynthesisLLM`, opcional/injetável) — Pydantic AI + Ollama.
    3. Validador determinístico (`validator.validate`) — faithfulness leve.

Projeto para teste offline: se nenhum LLM é injetado, o agente devolve
`NoEvidence(reason="off_topic")` para evitar invenção. Os testes injetam
um `FakeSynthesisLLM` controlado.

`SynthesisAgent.synthesize(query, bundle)` é a única superfície pública.
"""

from __future__ import annotations

from typing import Optional, Protocol

from opentelemetry.trace import Tracer

from src.config import Settings, get_settings
from src.memory.context_bundle import ContextBundle
from src.observability.tracer import get_tracer

from .synthesis.prompts import suggestion_for_intent
from .synthesis.renderer import render_prompt
from .synthesis.schemas import NoEvidence, SynthesisOutput, SynthesisResult
from .synthesis.validator import validate


class SynthesisLLM(Protocol):
    """Contrato do classificador LLM (camada 2). Implementação: Pydantic AI."""

    async def synthesize(self, prompt: str) -> SynthesisResult: ...


class SynthesisAgent:
    """Stateless: trabalha apenas com o que recebe via parâmetros (SPEC-006 §1)."""

    def __init__(
        self,
        llm: Optional[SynthesisLLM] = None,
        *,
        settings: Optional[Settings] = None,
        min_relevance_score: Optional[float] = None,
        tracer: Optional[Tracer] = None,
    ):
        self._settings = settings or get_settings()
        self._llm = llm
        self._min_relevance = (
            min_relevance_score
            if min_relevance_score is not None
            else self._settings.synthesis_min_relevance_score
        )
        self._tracer = tracer or get_tracer()

    # ------------------------------------------------------------------ public

    async def synthesize(
        self, query: str, bundle: ContextBundle
    ) -> SynthesisOutput:
        if bundle is None:
            raise TypeError("bundle não pode ser None")
        intent = self._intent_of(bundle)

        with self._tracer.start_as_current_span("agent2.synthesize") as span:
            span.set_attribute("bundle_size_chunks", len(bundle.rag_chunks))
            span.set_attribute("bundle_size_facts", len(bundle.semantic_facts))
            span.set_attribute("max_relevance", self._max_relevance(bundle))
            span.set_attribute("intent", intent)
            span.set_attribute("query_length", len(query or ""))

            # Query vazia: NoEvidence imediato, sem LLM (SPEC-006 §13).
            if not query or not query.strip():
                out = NoEvidence(
                    reason="empty_bundle",
                    suggestion="Faça uma pergunta para que eu possa pesquisar.",
                    used_intent=intent,
                )
                span.set_attribute("output_kind", out.kind)
                return out

            # Fase 1 — Pré-check determinístico (sem LLM).
            pre = self._precheck(bundle, intent, span)
            if pre is not None:
                span.set_attribute("output_kind", pre.kind)
                return pre

            # Fase 2 — LLM (se disponível).
            if self._llm is None:
                # Sem LLM injetado: degrada para NoEvidence em vez de inventar.
                out = NoEvidence(
                    reason="off_topic",
                    suggestion="Síntese offline indisponível neste ambiente.",
                    used_intent=intent,
                )
                span.set_attribute("output_kind", out.kind)
                span.set_attribute("llm_present", False)
                return out

            prompt = render_prompt(query, bundle)
            llm_result = await self._run_llm(prompt, intent, span)
            if isinstance(llm_result, NoEvidence):
                span.set_attribute("output_kind", llm_result.kind)
                return llm_result

            # Garante que `used_intent` reflete o bundle, não o que a LLM ecoou.
            if llm_result.used_intent != intent:
                llm_result = llm_result.model_copy(update={"used_intent": intent})

            # Fase 3 — Validador determinístico.
            with self._tracer.start_as_current_span("agent2.validate") as vspan:
                final = validate(llm_result, bundle, span=vspan)
            span.set_attribute("output_kind", final.kind)
            return final

    # ----------------------------------------------------------------- fase 1

    def _precheck(
        self, bundle: ContextBundle, intent: str, parent_span
    ) -> Optional[NoEvidence]:
        with self._tracer.start_as_current_span("agent2.precheck") as span:
            empty = not bundle.rag_chunks and not bundle.semantic_facts
            span.set_attribute("empty_bundle", empty)
            if empty:
                return NoEvidence(
                    reason="empty_bundle",
                    suggestion=suggestion_for_intent(intent),
                    used_intent=intent,
                )

            max_rel = self._max_relevance(bundle)
            span.set_attribute("max_relevance", max_rel)
            span.set_attribute("min_relevance_threshold", self._min_relevance)
            if bundle.rag_chunks and max_rel < self._min_relevance:
                # Só aplica low_relevance quando há rag_chunks: facts-only é
                # personalização (não comparável ao score de RAG).
                return NoEvidence(
                    reason="low_relevance",
                    suggestion=suggestion_for_intent(intent),
                    used_intent=intent,
                )
        return None

    # ----------------------------------------------------------------- fase 2

    async def _run_llm(
        self, prompt: str, intent: str, parent_span
    ) -> SynthesisOutput:
        with self._tracer.start_as_current_span("agent2.llm.generate") as span:
            span.set_attribute("model", self._settings.ollama_synthesis_model)
            try:
                result = await self._llm.synthesize(prompt)  # type: ignore[union-attr]
                span.set_attribute("success", True)
                return result
            except Exception as e:
                # Best-effort: timeout, JSON inválido, qualquer erro do LLM
                # vira NoEvidence(off_topic) (SPEC-006 §9.2 / §13).
                span.set_attribute("success", False)
                span.set_attribute("error", str(e))
                return NoEvidence(
                    reason="off_topic",
                    suggestion="LLM indisponível no momento.",
                    used_intent=intent,
                )

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _max_relevance(bundle: ContextBundle) -> float:
        scores = [
            c.relevance_score
            for c in bundle.rag_chunks
            if c.relevance_score is not None
        ]
        return max(scores) if scores else 0.0

    @staticmethod
    def _intent_of(bundle: ContextBundle) -> str:
        if not bundle.metadata:
            return "unknown"
        return str(bundle.metadata.get("intent") or "unknown")
