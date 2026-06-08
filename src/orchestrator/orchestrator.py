"""Orquestrador MVP — coordenador único do turno (SPEC-008).

Pipeline em 7 fases:
    1. Pré: increment turn_count + WM.add(query)
    2. Triagem (safe_triage)
    3. Despacho por kind (clarification curto-circuita; meta responde canned)
    4. Retrieval multi-fonte (RAG + Episodic + Semantic), best-effort por fonte
    5. ContextBuilder.build() com orçamento de tokens
    6. Síntese (safe_synthesize)
    7. Pós: WM.add(resposta) + persist_turn_stub

`Orchestrator.handle_turn()` é a única superfície pública para a UI/CLI.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from opentelemetry.trace import Tracer

from src.agents.agent1_triage import TriageAgent
from src.agents.agent2_synthesis import SynthesisAgent
from src.agents.agent3_stub import persist_turn_stub
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
from src.config import Settings, get_settings
from src.memory.context_bundle import ContextBundle
from src.memory.episodic import EpisodicMemory
from src.memory.guardrails import PIIGuardrails
from src.memory.semantic import SemanticMemory
from src.memory.working import WorkingMemory
from src.observability.tracer import get_tracer
from src.rag.retriever import SemanticRetriever

from .context_builder import ContextBuilder
from .degradation import (
    safe_episodic_recent,
    safe_episodic_semantic,
    safe_rag_search,
    safe_semantic_search,
    safe_synthesize,
    safe_triage,
    temporal_to_filters,
    temporal_to_time_window,
)
from .schemas import (
    AnswerResponse,
    ClarificationResponse,
    ErrorResponse,
    MetaResponse,
    OrchestratorResponse,
)


@dataclass
class SessionState:
    session_id: str
    user_id: str
    started_at: datetime
    working_memory: WorkingMemory
    turn_count: int = 0
    last_intent: Optional[str] = None


class Orchestrator:
    """Coordenador único do turno. Stateful (dono da SessionState)."""

    def __init__(
        self,
        *,
        triage_agent: TriageAgent,
        synthesis_agent: SynthesisAgent,
        retriever: SemanticRetriever,
        episodic: EpisodicMemory,
        semantic: SemanticMemory,
        settings: Optional[Settings] = None,
        tracer: Optional[Tracer] = None,
        session_id: Optional[str] = None,
    ):
        if triage_agent is None or synthesis_agent is None:
            raise ValueError("triage_agent e synthesis_agent são obrigatórios")
        if retriever is None or episodic is None or semantic is None:
            raise ValueError("retriever, episodic e semantic são obrigatórios")

        self.settings = settings or get_settings()
        self._tracer = tracer or get_tracer()
        self.triage_agent = triage_agent
        self.synthesis_agent = synthesis_agent
        self.retriever = retriever
        self.episodic = episodic
        self.semantic = semantic
        self.context_builder = ContextBuilder(tracer=self._tracer)

        self.session = SessionState(
            session_id=session_id or uuid.uuid4().hex,
            user_id=self.settings.session_user_id,
            started_at=datetime.now(timezone.utc),
            working_memory=WorkingMemory(
                capacity=self.settings.working_memory_capacity
            ),
        )

    # ------------------------------------------------------------- factory

    @classmethod
    def from_settings(cls, settings: Optional[Settings] = None) -> "Orchestrator":
        """Instancia dependências reais (espelha o setup do chat_demo.py)."""
        s = settings or get_settings()

        # Triagem
        from src.agents.triage.rules import TriageRuleEngine
        from src.agents.triage.temporal import TemporalExtractor

        triage_llm = None
        temporal_llm = None
        try:
            from src.agents.triage.llm_classifier import build_default_llms

            triage_llm, temporal_llm = build_default_llms(s)
        except Exception:
            pass
        triage_agent = TriageAgent(
            rule_engine=TriageRuleEngine(),
            temporal_extractor=TemporalExtractor(llm=temporal_llm),
            llm=triage_llm,
            rules_confidence_threshold=s.triage_rules_confidence_threshold,
            clarify_confidence_threshold=s.triage_clarify_confidence_threshold,
            max_clarification_rounds=s.triage_max_clarification_rounds,
        )

        # Síntese
        from src.agents.synthesis.llm_classifier import (
            build_default_synthesis_llm,
        )

        synthesis_llm = build_default_synthesis_llm(s)
        synthesis_agent = SynthesisAgent(llm=synthesis_llm, settings=s)

        # RAG + memórias
        from src.rag.embedder import get_embedding_function
        from src.rag.store import VectorStore

        embedding = get_embedding_function(s.embedding_model)
        retriever = SemanticRetriever(
            db_path=s.vectorstore_path, embedding_function=embedding
        )
        store = VectorStore(db_path=s.vectorstore_path, embedding_function=embedding)
        episodic = EpisodicMemory(
            vector_store=store, sqlite_path=s.episodic_metadata_db
        )
        semantic = SemanticMemory(vector_store=store)

        return cls(
            triage_agent=triage_agent,
            synthesis_agent=synthesis_agent,
            retriever=retriever,
            episodic=episodic,
            semantic=semantic,
            settings=s,
        )

    # ------------------------------------------------------------ handle_turn

    async def handle_turn(self, query: str) -> OrchestratorResponse:
        start = time.perf_counter()
        self.session.turn_count += 1
        turn = self.session.turn_count
        sid = self.session.session_id

        with self._tracer.start_as_current_span("orchestrator.handle_turn") as span:
            span.set_attribute("session_id", sid)
            span.set_attribute("turn", turn)
            span.set_attribute("user_id", self.session.user_id)
            span.set_attribute("query_length", len(query or ""))

            # Query vazia → clarificação trivial sem chamar agentes (§15).
            if not query or not query.strip():
                resp = ClarificationResponse(
                    triage=ClarificationNeeded(
                        reason="low_confidence",
                        question="Pode me dizer o que você quer pesquisar?",
                        detected_options=[],
                        confidence=0.0,
                    ),
                    session_id=sid,
                    turn=turn,
                    elapsed_ms=self._ms(start),
                )
                span.set_attribute("response_kind", resp.kind)
                return resp

            try:
                # === Fase 1 — Pré ===
                pii_in = PIIGuardrails.has_pii(query)
                self.session.working_memory.add(
                    content=query,
                    importance=1.0,
                    source="user",
                    contains_pii=pii_in,
                )

                # === Fase 2 — Triagem ===
                triage_out = await safe_triage(
                    self.triage_agent,
                    query,
                    timeout_s=self.settings.ollama_triage_timeout_s,
                    tracer=self._tracer,
                )

                # === Fase 3 — Despacho ===
                if isinstance(triage_out, ClarificationNeeded):
                    return await self._handle_clarification(
                        triage_out, query, sid, turn, span, start
                    )

                triage_result: TriageResult = triage_out  # type: ignore[assignment]
                self.session.last_intent = triage_result.intent
                self.session.working_memory.add(
                    content=f"intent={triage_result.intent}",
                    importance=0.8,
                    source="router",
                )
                if triage_result.temporal_filter is not None:
                    self.session.working_memory.add(
                        content=f"janela={triage_result.temporal_filter.expression}",
                        importance=0.7,
                        source="router",
                    )

                if triage_result.intent == "meta":
                    return await self._handle_meta(query, sid, turn, span, start)

                # === Fase 4 — Retrieval ===
                rag_chunks, failed_collections = self._retrieve_rag(
                    query, triage_result
                )
                recent_ep = []
                if "episodic_recent" in triage_result.target_memory_tiers:
                    recent_ep = safe_episodic_recent(
                        self.episodic,
                        user_id=self.session.user_id,
                        n=self.settings.episodic_recent_n,
                        tracer=self._tracer,
                    )
                if "episodic_semantic" in triage_result.target_memory_tiers:
                    recent_ep = recent_ep + safe_episodic_semantic(
                        self.episodic,
                        user_id=self.session.user_id,
                        query=query,
                        top_k=self.settings.episodic_semantic_top_k,
                        time_window=temporal_to_time_window(
                            triage_result.temporal_filter
                        ),
                        tracer=self._tracer,
                    )
                semantic_facts = []
                if "semantic" in triage_result.target_memory_tiers:
                    semantic_facts = safe_semantic_search(
                        self.semantic,
                        user_id=self.session.user_id,
                        query=query,
                        top_k=self.settings.semantic_top_k,
                        tracer=self._tracer,
                    )

                # === Fase 5 — ContextBuilder ===
                bundle = self.context_builder.build(
                    query=query,
                    triage=triage_result,
                    working=self.session.working_memory.get_top_k(),
                    recent_episodic=recent_ep,
                    semantic_facts=semantic_facts,
                    rag_chunks=rag_chunks,
                    token_budget=self.settings.max_context_tokens,
                    session_id=sid,
                    turn=turn,
                    failed_collections=failed_collections,
                )

                # === Fase 6 — Síntese ===
                synthesis_out = await safe_synthesize(
                    self.synthesis_agent,
                    query,
                    bundle,
                    timeout_s=self.settings.ollama_synthesis_timeout_s,
                    used_intent=triage_result.intent,
                    tracer=self._tracer,
                )

                # === Fase 7 — Pós ===
                display_text = self._display_text(synthesis_out)
                self.session.working_memory.add(
                    content=display_text[:500],
                    importance=0.9,
                    source="agent",
                    contains_pii=PIIGuardrails.has_pii(display_text),
                )
                await persist_turn_stub(
                    user_id=self.session.user_id,
                    session_id=sid,
                    user_message=query,
                    agent_response=display_text,
                    intent=triage_result.intent,
                    episodic_memory=self.episodic,
                    tracer=self._tracer,
                )

                resp = AnswerResponse(
                    synthesis=synthesis_out,
                    session_id=sid,
                    turn=turn,
                    elapsed_ms=self._ms(start),
                )
                span.set_attribute("response_kind", resp.kind)
                span.set_attribute("elapsed_ms", resp.elapsed_ms)
                return resp

            except Exception as e:
                with self._tracer.start_as_current_span(
                    "orchestrator.handle_turn.unhandled"
                ) as s:
                    s.set_attribute("error", str(e))
                return ErrorResponse(
                    stage="unknown",
                    message=f"Algo deu errado: {e.__class__.__name__}. Tente novamente.",
                    session_id=sid,
                    turn=turn,
                    elapsed_ms=self._ms(start),
                )

    # ------------------------------------------------------- handlers especiais

    async def _handle_clarification(
        self,
        clar: ClarificationNeeded,
        query: str,
        sid: str,
        turn: int,
        span,
        start: float,
    ) -> ClarificationResponse:
        self.session.working_memory.add(
            content=f"clarif: {clar.question}",
            importance=0.8,
            source="system",
        )
        await persist_turn_stub(
            user_id=self.session.user_id,
            session_id=sid,
            user_message=query,
            agent_response=clar.question,
            intent=None,
            episodic_memory=self.episodic,
            tracer=self._tracer,
        )
        resp = ClarificationResponse(
            triage=clar, session_id=sid, turn=turn, elapsed_ms=self._ms(start)
        )
        span.set_attribute("response_kind", resp.kind)
        return resp

    async def _handle_meta(
        self, query: str, sid: str, turn: int, span, start: float
    ) -> MetaResponse:
        msg = self.settings.meta_intent_response
        self.session.working_memory.add(
            content=msg[:500], importance=0.9, source="agent"
        )
        await persist_turn_stub(
            user_id=self.session.user_id,
            session_id=sid,
            user_message=query,
            agent_response=msg,
            intent="meta",
            episodic_memory=self.episodic,
            tracer=self._tracer,
        )
        resp = MetaResponse(
            message=msg, session_id=sid, turn=turn, elapsed_ms=self._ms(start)
        )
        span.set_attribute("response_kind", resp.kind)
        return resp

    # ------------------------------------------------------------ retrieval

    def _retrieve_rag(self, query: str, triage: TriageResult):
        all_chunks = []
        failed = []
        filters = temporal_to_filters(
            triage.temporal_filter, triage.structured_filters
        )
        for col in triage.target_rag_collections:
            chunks, ok = safe_rag_search(
                self.retriever,
                collection=col,
                query=query,
                top_k=self.settings.rag_top_k_per_collection,
                filters=filters,
                tracer=self._tracer,
            )
            if not ok:
                failed.append(col)
            all_chunks.extend(chunks)
        return all_chunks, failed

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _display_text(out: SynthesisOutput) -> str:
        if isinstance(out, SynthesisResult):
            return out.answer
        if isinstance(out, NoEvidence):
            return out.suggestion
        return str(out)

    @staticmethod
    def _ms(start: float) -> int:
        return int((time.perf_counter() - start) * 1000)
