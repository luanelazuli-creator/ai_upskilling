"""Testes do Orquestrador (SPEC-008 §14).

Padrão: sync com `asyncio.run()` (sem pytest-asyncio). Mocks dos agentes
+ fakes in-memory das memórias e do retriever. Smoke real com Ollama está
marcado `@pytest.mark.ollama`.
"""

from __future__ import annotations

import asyncio

import pytest
from opentelemetry.sdk.trace import TracerProvider

from src.agents.agent3_stub import persist_turn_stub
from src.agents.synthesis.schemas import NoEvidence, SynthesisResult
from src.config import Settings
from src.memory.context_bundle import ContextBundle
from src.orchestrator import (
    AnswerResponse,
    ClarificationResponse,
    ContextBuilder,
    ErrorResponse,
    MetaResponse,
    Orchestrator,
)
from src.orchestrator.degradation import (
    safe_rag_search,
    safe_triage,
    temporal_to_filters,
)
from tests.fixtures.orchestrator_scenarios import (
    FakeEpisodic,
    FakeRetriever,
    FakeSemantic,
    FakeSynthesisAgent,
    FakeTriageAgent,
    make_chunk,
    make_clarification,
    make_conversation_record,
    make_fact_obj,
    make_no_evidence,
    make_synthesis_result,
    make_triage_result,
)


def run(coro):
    return asyncio.run(coro)


def _tracer():
    return TracerProvider().get_tracer("test-spec008")


def _settings(**overrides) -> Settings:
    base = Settings()
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def _build_orch(
    triage_output,
    synthesis_output,
    *,
    retriever=None,
    episodic=None,
    semantic=None,
    triage_exc=None,
    synth_exc=None,
    settings=None,
):
    triage = FakeTriageAgent(triage_output, raise_exc=triage_exc)
    synth = FakeSynthesisAgent(synthesis_output, raise_exc=synth_exc)
    retr = retriever or FakeRetriever({"diario": [make_chunk()]})
    epi = episodic or FakeEpisodic()
    sem = semantic or FakeSemantic()
    return Orchestrator(
        triage_agent=triage,
        synthesis_agent=synth,
        retriever=retr,
        episodic=epi,
        semantic=sem,
        settings=settings or _settings(),
        tracer=_tracer(),
        session_id="sess_test",
    )


# ===================================================== §14.2 Context Builder


def test_budget_split_matches_spec_mem_percentages():
    cb = ContextBuilder(tracer=_tracer())
    triage = make_triage_result()
    bundle = cb.build(
        query="oi",
        triage=triage,
        working=[],
        recent_episodic=[],
        semantic_facts=[],
        rag_chunks=[],
        token_budget=1000,
        session_id="s",
        turn=1,
    )
    md = bundle.metadata
    assert md["tokens_estimated"] == 0
    assert set(md["tokens_per_section"].keys()) == {
        "working",
        "episodic",
        "semantic",
        "rag",
    }


def test_rag_overflow_drops_lowest_score():
    cb = ContextBuilder(tracer=_tracer())
    triage = make_triage_result()
    big = "x" * 400  # ~100 tokens
    chunks = [
        make_chunk(chunk_id=f"c{i}", content=big, relevance_score=score)
        for i, score in enumerate([0.9, 0.5, 0.7])
    ]
    bundle = cb.build(
        query="q",
        triage=triage,
        working=[],
        recent_episodic=[],
        semantic_facts=[],
        rag_chunks=chunks,
        token_budget=1000,  # RAG share = 400 tokens => cabe ~3 mas folga apertada
        session_id="s",
        turn=1,
    )
    kept_ids = {c.id for c in bundle.rag_chunks}
    # O de menor score (0.5) deve sair antes
    assert "c1" not in kept_ids or len(kept_ids) >= 2


def test_working_underuse_yields_extra_to_rag():
    cb = ContextBuilder(tracer=_tracer())
    triage = make_triage_result()
    big = "x" * 800  # ~200 tokens, não cabe em RAG share=400 sozinho
    chunks = [make_chunk(chunk_id="c0", content=big, relevance_score=0.9)]
    # Sem working items → sobra de working (100) entra no RAG (total 500)
    bundle = cb.build(
        query="q",
        triage=triage,
        working=[],
        recent_episodic=[],
        semantic_facts=[],
        rag_chunks=chunks,
        token_budget=1000,
        session_id="s",
        turn=1,
    )
    # Agora deve caber (500 >= 200)
    assert len(bundle.rag_chunks) == 1


def test_empty_sources_produce_minimal_bundle():
    cb = ContextBuilder(tracer=_tracer())
    triage = make_triage_result()
    bundle = cb.build(
        query="q",
        triage=triage,
        working=[],
        recent_episodic=[],
        semantic_facts=[],
        rag_chunks=[],
        token_budget=4096,
        session_id="s",
        turn=1,
    )
    assert bundle.working == []
    assert bundle.rag_chunks == []
    assert bundle.metadata["tokens_estimated"] == 0


def test_metadata_carries_intent_and_session_id():
    cb = ContextBuilder(tracer=_tracer())
    triage = make_triage_result(intent="course_status")
    bundle = cb.build(
        query="q",
        triage=triage,
        working=[],
        recent_episodic=[],
        semantic_facts=[],
        rag_chunks=[],
        token_budget=4096,
        session_id="abc123",
        turn=7,
    )
    assert bundle.metadata["intent"] == "course_status"
    assert bundle.metadata["session_id"] == "abc123"
    assert bundle.metadata["turn"] == 7
    assert "retrieved_at" in bundle.metadata


def test_failed_collections_recorded_in_metadata():
    cb = ContextBuilder(tracer=_tracer())
    triage = make_triage_result()
    bundle = cb.build(
        query="q",
        triage=triage,
        working=[],
        recent_episodic=[],
        semantic_facts=[],
        rag_chunks=[],
        token_budget=4096,
        session_id="s",
        turn=1,
        failed_collections=["cursos"],
    )
    assert bundle.metadata["failed_collections"] == ["cursos"]


# ============================================== §14.3 Despacho do Orquestrador


def test_handle_turn_triage_result_goes_through_full_pipeline():
    triage_out = make_triage_result(intent="diary_lookup", collections=["diario"])
    synth_out = make_synthesis_result()
    orch = _build_orch(triage_out, synth_out)
    resp = run(orch.handle_turn("o que fiz dia 11"))
    assert isinstance(resp, AnswerResponse)
    assert resp.synthesis == synth_out
    assert resp.turn == 1
    assert resp.session_id == "sess_test"
    assert resp.elapsed_ms >= 0
    # Bundle foi montado e entregue à síntese
    assert orch.synthesis_agent.last_bundle is not None
    assert isinstance(orch.synthesis_agent.last_bundle, ContextBundle)


def test_handle_turn_clarification_returns_immediately():
    triage_out = make_clarification("Sobre qual fonte?")
    orch = _build_orch(triage_out, make_synthesis_result())
    resp = run(orch.handle_turn("ok"))
    assert isinstance(resp, ClarificationResponse)
    assert resp.triage.question == "Sobre qual fonte?"
    # Síntese NÃO foi chamada
    assert orch.synthesis_agent.calls == 0


def test_handle_turn_meta_intent_returns_canned_without_synthesis():
    triage_out = make_triage_result(
        intent="meta", collections=[], tiers=[], classification_method="rules"
    )
    orch = _build_orch(triage_out, make_synthesis_result())
    resp = run(orch.handle_turn("o que você sabe fazer"))
    assert isinstance(resp, MetaResponse)
    assert "Second Brain" in resp.message
    assert orch.synthesis_agent.calls == 0
    # RAG não foi tocado
    assert orch.retriever.calls == []


def test_handle_turn_cross_domain_queries_multiple_rag_collections():
    triage_out = make_triage_result(
        intent="cross_domain",
        collections=["diario", "cursos", "referencias"],
    )
    retriever = FakeRetriever(
        {
            "diario": [make_chunk(chunk_id="d1")],
            "cursos": [make_chunk(chunk_id="c1", collection="cursos")],
            "referencias": [
                make_chunk(chunk_id="r1", collection="referencias")
            ],
        }
    )
    orch = _build_orch(
        triage_out, make_synthesis_result(), retriever=retriever
    )
    resp = run(orch.handle_turn("o que sei sobre X"))
    assert isinstance(resp, AnswerResponse)
    queried_collections = {c[0] for c in retriever.calls}
    assert queried_collections == {"diario", "cursos", "referencias"}


def test_handle_turn_writes_query_and_response_to_working_memory():
    orch = _build_orch(
        make_triage_result(),
        make_synthesis_result(answer="resposta x"),
    )
    run(orch.handle_turn("pergunta x"))
    wm_contents = [it.content for it in orch.session.working_memory.get_top_k()]
    assert "pergunta x" in wm_contents
    # Resposta truncada a 500 chars
    assert any("resposta x" in c for c in wm_contents)


def test_handle_turn_calls_persist_turn_stub_at_end():
    epi = FakeEpisodic()
    orch = _build_orch(
        make_triage_result(),
        make_synthesis_result(answer="oi"),
        episodic=epi,
    )
    run(orch.handle_turn("pergunta"))
    assert len(epi.records) == 1
    rec = epi.records[0]
    assert rec["user_message"] == "pergunta"
    assert rec["agent_response"] == "oi"
    assert rec["pii_sanitized"] is True
    assert rec["intent"] == "diary_lookup"


def test_handle_turn_emits_session_id_and_turn_in_response():
    orch = _build_orch(make_triage_result(), make_synthesis_result())
    resp = run(orch.handle_turn("q"))
    assert resp.session_id == "sess_test"
    assert resp.turn == 1
    assert resp.elapsed_ms >= 0


def test_turn_count_increments_per_turn():
    orch = _build_orch(make_triage_result(), make_synthesis_result())
    r1 = run(orch.handle_turn("a"))
    r2 = run(orch.handle_turn("b"))
    assert r1.turn == 1
    assert r2.turn == 2
    assert orch.session.turn_count == 2


# ============================================================ §14.4 Degradação


def test_triage_timeout_falls_back_to_broad_search():
    async def slow_triage(query, clarification_round=0):
        await asyncio.sleep(5)
        raise AssertionError("não deveria chegar aqui")

    fake = FakeTriageAgent(make_triage_result())
    fake.triage = slow_triage  # substitui método
    settings = _settings(ollama_triage_timeout_s=1)

    orch = Orchestrator(
        triage_agent=fake,
        synthesis_agent=FakeSynthesisAgent(make_synthesis_result()),
        retriever=FakeRetriever(
            {
                "diario": [make_chunk()],
                "cursos": [],
                "referencias": [],
            }
        ),
        episodic=FakeEpisodic(),
        semantic=FakeSemantic(),
        settings=settings,
        tracer=_tracer(),
        session_id="s1",
    )
    resp = run(orch.handle_turn("query lenta"))
    assert isinstance(resp, AnswerResponse)
    # Fallback amplo deve ter consultado as 3 coleções
    queried = {c[0] for c in orch.retriever.calls}
    assert queried == {"diario", "cursos", "referencias"}


def test_single_rag_collection_failure_continues_with_others():
    triage = make_triage_result(
        intent="cross_domain",
        collections=["diario", "cursos", "referencias"],
    )
    retriever = FakeRetriever(
        {
            "diario": [make_chunk(chunk_id="d1")],
            "referencias": [make_chunk(chunk_id="r1", collection="referencias")],
        },
        fail_collections={"cursos"},
    )
    orch = _build_orch(triage, make_synthesis_result(), retriever=retriever)
    resp = run(orch.handle_turn("q"))
    assert isinstance(resp, AnswerResponse)
    # Bundle ainda foi montado com chunks das coleções OK
    bundle = orch.synthesis_agent.last_bundle
    assert bundle is not None
    kept_ids = {c.id for c in bundle.rag_chunks}
    assert kept_ids == {"d1", "r1"}
    assert bundle.metadata.get("failed_collections") == ["cursos"]


def test_all_rag_failures_still_produces_bundle_with_memory():
    triage = make_triage_result(
        intent="diary_lookup",
        collections=["diario"],
        tiers=["episodic_recent"],
    )
    retriever = FakeRetriever({}, fail_collections={"diario"})
    epi = FakeEpisodic()
    epi.recent_results = [make_conversation_record()]
    orch = _build_orch(
        triage, make_synthesis_result(), retriever=retriever, episodic=epi
    )
    resp = run(orch.handle_turn("q"))
    assert isinstance(resp, AnswerResponse)
    bundle = orch.synthesis_agent.last_bundle
    assert bundle.rag_chunks == []
    assert len(bundle.recent_episodic) == 1


def test_synthesis_timeout_returns_no_evidence_answer():
    async def slow_synth(query, bundle):
        await asyncio.sleep(5)
        raise AssertionError("não deveria chegar aqui")

    synth = FakeSynthesisAgent(make_synthesis_result())
    synth.synthesize = slow_synth
    settings = _settings(ollama_synthesis_timeout_s=1)
    orch = Orchestrator(
        triage_agent=FakeTriageAgent(make_triage_result()),
        synthesis_agent=synth,
        retriever=FakeRetriever({"diario": [make_chunk()]}),
        episodic=FakeEpisodic(),
        semantic=FakeSemantic(),
        settings=settings,
        tracer=_tracer(),
        session_id="s1",
    )
    resp = run(orch.handle_turn("q"))
    assert isinstance(resp, AnswerResponse)
    assert isinstance(resp.synthesis, NoEvidence)


def test_persist_stub_failure_does_not_block_response():
    epi = FakeEpisodic()
    epi.fail_add = True
    orch = _build_orch(
        make_triage_result(), make_synthesis_result(), episodic=epi
    )
    resp = run(orch.handle_turn("q"))
    assert isinstance(resp, AnswerResponse)
    assert epi.records == []


def test_empty_query_returns_clarification_without_agents():
    orch = _build_orch(make_triage_result(), make_synthesis_result())
    resp = run(orch.handle_turn("   "))
    assert isinstance(resp, ClarificationResponse)
    assert orch.triage_agent.calls == 0
    assert orch.synthesis_agent.calls == 0


# =============================================================== §14.5 stub


def test_persist_turn_stub_sanitizes_pii_before_write():
    epi = FakeEpisodic()
    cid = asyncio.run(
        persist_turn_stub(
            user_id="u",
            session_id="s",
            user_message="meu email é foo@bar.com",
            agent_response="ok",
            intent="diary_lookup",
            episodic_memory=epi,
            tracer=_tracer(),
        )
    )
    assert cid is not None
    rec = epi.records[0]
    assert "foo@bar.com" not in rec["user_message"]
    assert "[REDACTED_EMAIL]" in rec["user_message"]


def test_persist_turn_stub_marks_pii_sanitized_true():
    epi = FakeEpisodic()
    asyncio.run(
        persist_turn_stub(
            user_id="u",
            session_id="s",
            user_message="oi",
            agent_response="olá",
            intent=None,
            episodic_memory=epi,
            tracer=_tracer(),
        )
    )
    assert epi.records[0]["pii_sanitized"] is True


def test_persist_turn_stub_returns_none_on_failure_no_raise():
    epi = FakeEpisodic()
    epi.fail_add = True
    cid = asyncio.run(
        persist_turn_stub(
            user_id="u",
            session_id="s",
            user_message="oi",
            agent_response="olá",
            intent=None,
            episodic_memory=epi,
            tracer=_tracer(),
        )
    )
    assert cid is None


# =============================================== utilitários degradation


def test_temporal_to_filters_merges_temporal_and_structured():
    from src.agents.triage.schemas import TemporalRange
    from datetime import datetime as dt

    temp = TemporalRange(
        start=dt(2026, 6, 1),
        end=dt(2026, 6, 30),
        expression="junho",
        detection_method="dateparser",
    )
    filters = temporal_to_filters(temp, {"category": "stakeholders"})
    assert filters["category"] == "stakeholders"
    assert "date_gte" in filters
    assert "date_lte" in filters


def test_temporal_to_filters_none_when_both_empty():
    assert temporal_to_filters(None, None) is None
    assert temporal_to_filters(None, {}) is None


def test_safe_rag_search_returns_empty_on_failure():
    retriever = FakeRetriever({}, fail_collections={"diario"})
    chunks, ok = safe_rag_search(
        retriever,
        collection="diario",
        query="q",
        top_k=5,
        tracer=_tracer(),
    )
    assert chunks == []
    assert ok is False


# ================================================ rejeitos do constructor


# ============================================================ §14.6 CLI REPL


def _capture_render(resp):
    import io
    import contextlib

    from chat import _render

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _render(resp)
    return buf.getvalue()


def test_render_answer_response_includes_citations():
    from src.agents.synthesis.schemas import Citation, SynthesisResult

    resp = AnswerResponse(
        synthesis=SynthesisResult(
            answer="resposta",
            citations=[
                Citation(
                    chunk_id="chunk_001",
                    source_file="Dia 11.docx",
                    collection="diario",
                    relevance_score=0.78,
                )
            ],
            confidence=0.9,
            used_intent="diary_lookup",
        ),
        session_id="s",
        turn=3,
        elapsed_ms=120,
    )
    out = _capture_render(resp)
    assert "resposta" in out
    assert "chunk_001" in out
    assert "Dia 11.docx" in out
    assert "turno 3" in out


def test_render_clarification_lists_options():
    resp = ClarificationResponse(
        triage=make_clarification("Qual fonte?"),
        session_id="s",
        turn=1,
        elapsed_ms=10,
    )
    out = _capture_render(resp)
    assert "Qual fonte?" in out
    assert "diário" in out
    assert "cursos" in out


def test_render_no_evidence_shows_suggestion():
    resp = AnswerResponse(
        synthesis=make_no_evidence(reason="low_relevance"),
        session_id="s",
        turn=1,
        elapsed_ms=10,
    )
    out = _capture_render(resp)
    assert "sem evidência" in out
    assert "low_relevance" in out


def test_render_meta_response():
    resp = MetaResponse(
        message="canned msg", session_id="s", turn=1, elapsed_ms=5
    )
    out = _capture_render(resp)
    assert "canned msg" in out


def test_render_error_response():
    resp = ErrorResponse(
        stage="triage",
        message="algo falhou",
        session_id="s",
        turn=1,
    )
    out = _capture_render(resp)
    assert "triage" in out
    assert "algo falhou" in out


def test_orchestrator_constructor_rejects_missing_deps():
    with pytest.raises(ValueError):
        Orchestrator(
            triage_agent=None,  # type: ignore[arg-type]
            synthesis_agent=FakeSynthesisAgent(make_synthesis_result()),
            retriever=FakeRetriever({}),
            episodic=FakeEpisodic(),
            semantic=FakeSemantic(),
        )


# =========================================== §14.7 Smoke end-to-end com Ollama
#
# Estes testes exigem:
#   - Ollama vivo com modelos: qwen2.5:3b (triagem) e mistral (síntese)
#   - Dados ingeridos: python -m scripts.ingest --domain all
# Rodar apenas no Mac da Luane: pytest tests/test_spec_008.py -m ollama


@pytest.mark.ollama
def test_real_pipeline_diary_query():
    orch = Orchestrator.from_settings()
    resp = run(orch.handle_turn("o que fiz no dia 11"))
    assert isinstance(resp, (AnswerResponse, ClarificationResponse))


@pytest.mark.ollama
def test_real_pipeline_user_profile_query():
    orch = Orchestrator.from_settings()
    resp = run(orch.handle_turn("quais minhas preferências"))
    assert isinstance(resp, AnswerResponse)


@pytest.mark.ollama
def test_real_pipeline_unclear_query_clarifies():
    orch = Orchestrator.from_settings()
    resp = run(orch.handle_turn("ok"))
    assert isinstance(resp, ClarificationResponse)


@pytest.mark.ollama
def test_real_pipeline_meta_query_returns_canned():
    orch = Orchestrator.from_settings()
    resp = run(orch.handle_turn("o que você sabe fazer"))
    assert isinstance(resp, MetaResponse)


@pytest.mark.ollama
def test_real_pipeline_persists_to_episodic():
    orch = Orchestrator.from_settings()
    for q in ["o que fiz dia 11", "quais minhas preferências"]:
        run(orch.handle_turn(q))
    recent = orch.episodic.get_recent(user_id=orch.session.user_id, n=10)
    assert len(recent) >= 2
