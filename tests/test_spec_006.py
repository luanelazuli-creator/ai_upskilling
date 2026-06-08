"""Testes do Agente 2 — Síntese (SPEC-006).

Núcleo determinístico (pré-check + renderer + validador) testado 100%
offline. A camada LLM é exercitada via FakeSynthesisLLM controlado.

Async é exercitado via `run()` (asyncio.run) — o projeto não usa
pytest-asyncio (gotcha herdado da SPEC-005).
"""

from __future__ import annotations

import asyncio
from typing import Optional

import pytest

from src.agents.agent2_synthesis import SynthesisAgent, SynthesisLLM
from src.agents.synthesis.renderer import (
    collect_bundle_ids,
    fact_citation_id,
    render_prompt,
)
from src.agents.synthesis.schemas import (
    Citation,
    NoEvidence,
    SynthesisResult,
)
from src.agents.synthesis.validator import (
    extract_inline_ids,
    validate,
)
from tests.fixtures.synthesis_bundles import (
    diary_bundle,
    empty_bundle,
    facts_only_bundle,
    low_relevance_bundle,
    make_chunk,
    make_fact,
)


# ----------------------------------------------------------------- utilitários


def run(coro):
    return asyncio.run(coro)


def _isolated_tracer():
    """Tracer com provider próprio SEM exporter — spans funcionam mas não vão
    para o exporter JSON global (evita poluir observability/dashboards)."""
    from opentelemetry.sdk.trace import TracerProvider

    return TracerProvider().get_tracer("test-isolated")


def _in_memory_tracer():
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter


class FakeSynthesisLLM:
    """LLM determinístico para exercitar o caminho da camada 2."""

    def __init__(self, result: SynthesisResult):
        self.result = result
        self.calls = 0
        self.last_prompt: Optional[str] = None

    async def synthesize(self, prompt: str) -> SynthesisResult:
        self.calls += 1
        self.last_prompt = prompt
        return self.result


class BoomSynthesisLLM:
    """LLM que sempre falha — exercita o fallback de erro."""

    async def synthesize(self, prompt: str) -> SynthesisResult:
        raise RuntimeError("ollama down")


def make_agent(
    llm: Optional[SynthesisLLM] = None,
    *,
    min_relevance_score: Optional[float] = None,
    tracer=None,
) -> SynthesisAgent:
    return SynthesisAgent(
        llm=llm,
        min_relevance_score=min_relevance_score,
        tracer=tracer or _isolated_tracer(),
    )


# ============================================================================
# §12.1 — Pré-check (sem LLM)
# ============================================================================


def test_empty_bundle_returns_no_evidence():
    out = run(make_agent().synthesize("o que fiz", empty_bundle()))
    assert isinstance(out, NoEvidence)
    assert out.reason == "empty_bundle"
    assert out.used_intent == "diary_lookup"
    assert "diário" in out.suggestion.lower() or "diario" in out.suggestion.lower()


def test_low_relevance_returns_no_evidence():
    out = run(make_agent().synthesize("o que fiz", low_relevance_bundle()))
    assert isinstance(out, NoEvidence)
    assert out.reason == "low_relevance"


def test_threshold_configurable_via_constructor():
    # Threshold 0.05 => bundle low_relevance (max=0.18) deve passar do pré-check.
    # Sem LLM injetado, o agente devolve NoEvidence(off_topic) — não
    # NoEvidence(low_relevance) — provando que o threshold foi obedecido.
    agent = make_agent(min_relevance_score=0.05)
    out = run(agent.synthesize("o que fiz", low_relevance_bundle()))
    assert isinstance(out, NoEvidence)
    assert out.reason == "off_topic"  # LLM ausente, mas pré-check passou


def test_empty_query_short_circuits_without_llm():
    fake = FakeSynthesisLLM(
        SynthesisResult(
            answer="nunca deveria rodar",
            citations=[],
            confidence=0.9,
            used_intent="diary_lookup",
        )
    )
    out = run(make_agent(llm=fake).synthesize("   ", diary_bundle()))
    assert isinstance(out, NoEvidence)
    assert fake.calls == 0


def test_facts_only_bundle_passes_precheck():
    """user_profile sem rag_chunks NÃO deve disparar low_relevance."""
    out = run(make_agent().synthesize("quais minhas preferências", facts_only_bundle()))
    # Sem LLM injetado, cai em off_topic; o ponto é que NÃO virou empty_bundle.
    assert isinstance(out, NoEvidence)
    assert out.reason == "off_topic"
    assert out.used_intent == "user_profile"


def test_none_bundle_raises_type_error():
    with pytest.raises(TypeError):
        run(make_agent().synthesize("?", None))  # type: ignore[arg-type]


# ============================================================================
# §12.2 — Renderer
# ============================================================================


def test_rag_chunks_appear_first_in_prompt():
    bundle = diary_bundle()
    prompt = render_prompt("o que fiz", bundle)
    rag_idx = prompt.find("[Documentos relevantes - RAG]")
    hist_idx = prompt.find("[Histórico recente da conversa]")
    facts_idx = prompt.find("[Fatos sobre o usuário]")
    sess_idx = prompt.find("[Contexto da sessão atual]")
    query_idx = prompt.find("[Pergunta do usuário]")
    # Ordem das seções: RAG → Episodic → Facts → Working → Intent → Query.
    assert rag_idx < hist_idx < facts_idx < sess_idx < query_idx
    assert rag_idx >= 0


def test_chunk_id_appears_at_start_of_serialization():
    bundle = diary_bundle()
    prompt = render_prompt("q", bundle)
    # ID no início da serialização: linha começa com `[chunk_id]`.
    assert "[chunk_de_001]" in prompt
    # Linha do chunk deve ter o id como primeiro token na linha.
    for line in prompt.splitlines():
        if "chunk_de_001" in line and "Conteúdo:" not in line:
            assert line.lstrip().startswith("[chunk_de_001]")
            break


def test_fact_id_uses_fact_prefix():
    bundle = diary_bundle()
    prompt = render_prompt("q", bundle)
    assert "[fact:f_42]" in prompt


def test_intent_and_query_appear_in_prompt():
    bundle = diary_bundle(intent="diary_lookup")
    prompt = render_prompt("o que fiz no dia 11", bundle)
    assert "[Intent detectado]: diary_lookup" in prompt
    assert "[Pergunta do usuário]: o que fiz no dia 11" in prompt


def test_collect_bundle_ids_combines_rag_and_facts():
    bundle = diary_bundle()
    ids = collect_bundle_ids(bundle)
    assert "chunk_de_001" in ids
    assert "chunk_de_002" in ids
    assert fact_citation_id("f_42") in ids
    # Episodic não é citável.
    assert "conv_abc" not in ids


def test_empty_sections_render_as_vazio():
    prompt = render_prompt("q", empty_bundle())
    assert "(vazio)" in prompt


# ============================================================================
# §12.3 — Validador (sem LLM real, mocka output)
# ============================================================================


def test_extract_inline_ids_handles_concatenated_citations():
    ids = extract_inline_ids("texto [a_1][fact:b_2] mais texto [c_3]")
    assert ids == ["a_1", "fact:b_2", "c_3"]


def test_validator_no_evidence_returns_unchanged():
    bundle = diary_bundle()
    ne = NoEvidence(
        reason="empty_bundle", suggestion="x", used_intent="diary_lookup"
    )
    out = validate(ne, bundle)
    assert out is ne


def test_citation_to_unknown_id_returns_no_evidence():
    bundle = diary_bundle()
    result = SynthesisResult(
        answer="você fez X [chunk_inexistente_999].",
        citations=[
            Citation(
                chunk_id="chunk_inexistente_999",
                source_file="?",
                collection="diario",
                relevance_score=0.5,
            )
        ],
        confidence=0.9,
        used_intent="diary_lookup",
    )
    out = validate(result, bundle)
    assert isinstance(out, NoEvidence)
    assert out.reason == "off_topic"
    assert out.used_intent == "diary_lookup"


def test_long_answer_without_citation_drops_confidence():
    bundle = diary_bundle()
    # >30 palavras, sem citações inline e sem citations[].
    long_answer = " ".join(["palavra"] * 60)
    result = SynthesisResult(
        answer=long_answer,
        citations=[],
        confidence=0.8,
        used_intent="diary_lookup",
    )
    out = validate(result, bundle)
    assert isinstance(out, SynthesisResult)
    assert out.confidence == pytest.approx(0.4)


def test_short_answer_without_citation_keeps_confidence():
    bundle = diary_bundle()
    result = SynthesisResult(
        answer="ok, anotado.",
        citations=[],
        confidence=0.7,
        used_intent="meta",
    )
    out = validate(result, bundle)
    assert isinstance(out, SynthesisResult)
    assert out.confidence == 0.7


def test_inline_citation_within_bundle_passes():
    bundle = diary_bundle()
    result = SynthesisResult(
        answer="Você terminou o módulo 4 [chunk_de_001].",
        citations=[
            Citation(
                chunk_id="chunk_de_001",
                source_file="Dia 11.docx",
                collection="diario",
                relevance_score=0.78,
            )
        ],
        confidence=0.88,
        used_intent="diary_lookup",
    )
    out = validate(result, bundle)
    assert isinstance(out, SynthesisResult)
    assert out.confidence == 0.88


def test_fact_citation_recognized_by_validator():
    bundle = diary_bundle()
    result = SynthesisResult(
        answer="Sua preferência é receber respostas curtas [fact:f_42].",
        citations=[
            Citation(
                chunk_id="fact:f_42",
                source_file="user_facts",
                collection="user_facts",
                relevance_score=0.91,
            )
        ],
        confidence=0.85,
        used_intent="user_profile",
    )
    out = validate(result, bundle)
    assert isinstance(out, SynthesisResult)


# ============================================================================
# §12.4 — Integração (com fake LLM)
# ============================================================================


def test_synthesize_full_pipeline_with_fake_llm():
    bundle = diary_bundle()
    fake = FakeSynthesisLLM(
        SynthesisResult(
            answer="Você terminou o módulo 4 [chunk_de_001].",
            citations=[
                Citation(
                    chunk_id="chunk_de_001",
                    source_file="Dia 11.docx",
                    collection="diario",
                    relevance_score=0.78,
                )
            ],
            confidence=0.9,
            used_intent="diary_lookup",
        )
    )
    out = run(make_agent(llm=fake).synthesize("o que fiz no dia 11", bundle))
    assert fake.calls == 1
    assert isinstance(out, SynthesisResult)
    assert "chunk_de_001" in out.answer
    assert out.used_intent == "diary_lookup"


def test_used_intent_overwritten_from_bundle():
    """LLM pode ecoar intent errado; o agente força o intent do bundle."""
    bundle = diary_bundle(intent="diary_lookup")
    fake = FakeSynthesisLLM(
        SynthesisResult(
            answer="resposta [chunk_de_001].",
            citations=[],
            confidence=0.7,
            used_intent="meta",  # errado de propósito
        )
    )
    out = run(make_agent(llm=fake).synthesize("q", bundle))
    assert isinstance(out, SynthesisResult)
    assert out.used_intent == "diary_lookup"


def test_llm_failure_returns_no_evidence():
    out = run(
        make_agent(llm=BoomSynthesisLLM()).synthesize(
            "o que fiz", diary_bundle()
        )
    )
    assert isinstance(out, NoEvidence)
    assert out.reason == "off_topic"


def test_llm_hallucinated_id_becomes_no_evidence():
    bundle = diary_bundle()
    fake = FakeSynthesisLLM(
        SynthesisResult(
            answer="você fez X [chunk_que_nao_existe].",
            citations=[],
            confidence=0.95,
            used_intent="diary_lookup",
        )
    )
    out = run(make_agent(llm=fake).synthesize("o que fiz", bundle))
    assert isinstance(out, NoEvidence)
    assert out.reason == "off_topic"


def test_no_llm_injection_falls_back_to_no_evidence():
    out = run(make_agent().synthesize("o que fiz", diary_bundle()))
    assert isinstance(out, NoEvidence)
    assert out.reason == "off_topic"


def test_prompt_passed_to_llm_contains_bundle_serialization():
    bundle = diary_bundle()
    fake = FakeSynthesisLLM(
        SynthesisResult(
            answer="ok [chunk_de_001].",
            citations=[],
            confidence=0.7,
            used_intent="diary_lookup",
        )
    )
    run(make_agent(llm=fake).synthesize("o que fiz no dia 11", bundle))
    assert fake.last_prompt is not None
    assert "[chunk_de_001]" in fake.last_prompt
    assert "[Pergunta do usuário]: o que fiz no dia 11" in fake.last_prompt


# ============================================================================
# §12.5 — Instrumentação OTel
# ============================================================================


def test_otel_spans_emitted_per_phase_precheck_only():
    tracer, exporter = _in_memory_tracer()
    agent = make_agent(tracer=tracer)
    run(agent.synthesize("o que fiz", empty_bundle()))
    names = {s.name for s in exporter.get_finished_spans()}
    assert "agent2.synthesize" in names
    assert "agent2.precheck" in names
    # Sem LLM, não há span de generate.
    assert "agent2.llm.generate" not in names


def test_otel_spans_emitted_per_phase_full_pipeline():
    tracer, exporter = _in_memory_tracer()
    fake = FakeSynthesisLLM(
        SynthesisResult(
            answer="resposta [chunk_de_001].",
            citations=[],
            confidence=0.8,
            used_intent="diary_lookup",
        )
    )
    agent = make_agent(llm=fake, tracer=tracer)
    run(agent.synthesize("o que fiz", diary_bundle()))
    names = {s.name for s in exporter.get_finished_spans()}
    assert "agent2.synthesize" in names
    assert "agent2.precheck" in names
    assert "agent2.llm.generate" in names
    assert "agent2.validate" in names


def test_otel_parent_span_has_output_kind_attribute():
    tracer, exporter = _in_memory_tracer()
    agent = make_agent(tracer=tracer)
    run(agent.synthesize("o que fiz", empty_bundle()))
    parent = next(
        s for s in exporter.get_finished_spans() if s.name == "agent2.synthesize"
    )
    assert parent.attributes["output_kind"] == "no_evidence"
    assert parent.attributes["intent"] == "diary_lookup"


def test_otel_validate_span_records_hallucination():
    tracer, exporter = _in_memory_tracer()
    fake = FakeSynthesisLLM(
        SynthesisResult(
            answer="texto [chunk_inexistente].",
            citations=[],
            confidence=0.9,
            used_intent="diary_lookup",
        )
    )
    agent = make_agent(llm=fake, tracer=tracer)
    run(agent.synthesize("q", diary_bundle()))
    vspan = next(
        s for s in exporter.get_finished_spans() if s.name == "agent2.validate"
    )
    assert vspan.attributes["synthesis.hallucinated_ids"] >= 1


# ============================================================================
# Casos de borda do collect_bundle_ids / fact_citation_id
# ============================================================================


def test_fact_citation_id_prefix():
    assert fact_citation_id("xyz") == "fact:xyz"


def test_collect_ids_with_only_facts():
    from src.memory.context_bundle import ContextBundle

    bundle = ContextBundle(semantic_facts=[make_fact(fact_id="abc")])
    assert collect_bundle_ids(bundle) == {"fact:abc"}


def test_collect_ids_with_only_chunks():
    from src.memory.context_bundle import ContextBundle

    bundle = ContextBundle(rag_chunks=[make_chunk(chunk_id="only_one")])
    assert collect_bundle_ids(bundle) == {"only_one"}
