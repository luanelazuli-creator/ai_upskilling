"""Testes do Agente 1 — Triagem (SPEC-005).

Núcleo determinístico (regras + dateparser) testado 100% offline, sem Ollama.
Async é exercitado via `run()` (asyncio.run) — o projeto não usa pytest-asyncio.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from src.agents.agent1_triage import IntentLLM, TriageAgent
from src.agents.triage.rules import TriageRuleEngine, normalize
from src.agents.triage.routing import route_for_intent
from src.agents.triage.schemas import (
    ClarificationNeeded,
    TemporalRange,
    TriageResult,
)
from src.agents.triage.temporal import TemporalExtractor

FIXED_NOW = datetime(2026, 6, 15, 10, 0, 0)


def run(coro):
    return asyncio.run(coro)


def _isolated_tracer():
    """Tracer de provider próprio SEM exporter — spans funcionam mas não vão
    para o exporter JSON global (evita poluir observability/dashboards)."""
    from opentelemetry.sdk.trace import TracerProvider

    return TracerProvider().get_tracer("test-isolated")


def make_agent(llm: IntentLLM | None = None, **kwargs) -> TriageAgent:
    """Agente offline com `now` fixo para temporalidade determinística."""
    kwargs.setdefault("tracer", _isolated_tracer())
    return TriageAgent(
        rule_engine=TriageRuleEngine(),
        temporal_extractor=TemporalExtractor(now_fn=lambda: FIXED_NOW),
        llm=llm,
        **kwargs,
    )


# --- normalização --------------------------------------------------------


def test_normalize_strips_accents_and_lowercases():
    assert normalize("Diário PENDÊNCIA Ação") == "diario pendencia acao"


# --- camada 1: regras (§4.1) --------------------------------------------


def test_rules_classify_diary_with_explicit_date():
    e = TriageRuleEngine().evaluate("o que fiz no dia 11")
    assert e.intent == "diary_lookup"
    assert e.confidence >= 0.9
    assert "datas_explicitas" in e.fired_rules


def test_rules_classify_course_status():
    e = TriageRuleEngine().evaluate("onde parei no curso de Data Engineer")
    assert e.intent == "course_status"
    assert e.target_rag_collections == ["cursos"]


def test_rules_stakeholder_sets_category_filter():
    e = TriageRuleEngine().evaluate("quem é responsável pelo time X")
    assert e.intent == "reference_lookup"
    assert e.structured_filters == {"category": "stakeholders"}


def test_rules_golden_prompt_sets_type_filter():
    e = TriageRuleEngine().evaluate("qual prompt usar para isso")
    assert e.intent == "golden_prompt_request"
    assert e.structured_filters == {"type": "golden_prompt"}


def test_rules_no_match_returns_none_intent():
    e = TriageRuleEngine().evaluate("ok")
    assert e.intent is None
    assert e.confidence == 0.0


def test_cross_domain_detection_two_rag_domains():
    e = TriageRuleEngine().evaluate("minha pendência no diário sobre o manual de férias")
    assert e.intent == "cross_domain"
    assert e.is_cross_domain is True
    assert e.target_rag_collections == ["diario", "referencias"]
    assert 0.8 <= e.confidence <= 0.85  # média dos dois hits


def test_user_profile_routes_to_semantic_tier():
    e = TriageRuleEngine().evaluate("quais minhas preferências")
    assert e.intent == "user_profile"
    assert e.target_memory_tiers == ["semantic"]
    assert e.target_rag_collections == []


# --- camada 5: temporal (§5) --------------------------------------------


def test_temporal_explicit_dia_n_resolves_to_past_day():
    te = TemporalExtractor(now_fn=lambda: FIXED_NOW)
    tr = run(te.extract("o que fiz no dia 11"))
    assert tr is not None
    assert tr.start.date() == datetime(2026, 6, 11).date()
    assert tr.end.hour == 23 and tr.end.minute == 59
    assert tr.detection_method == "explicit"


def test_temporal_dia_n_future_rolls_to_previous_month():
    te = TemporalExtractor(now_fn=lambda: FIXED_NOW)
    tr = run(te.extract("dia 20"))  # 20 > 15 => mês anterior
    assert tr.start.date() == datetime(2026, 5, 20).date()


def test_temporal_relative_week_is_seven_day_range():
    te = TemporalExtractor(now_fn=lambda: FIXED_NOW)
    tr = run(te.extract("o que fiz semana passada"))
    assert tr is not None
    assert (tr.end.date() - tr.start.date()).days == 6  # segunda → domingo


def test_temporal_month_expands_to_full_month():
    te = TemporalExtractor(now_fn=lambda: FIXED_NOW)
    tr = run(te.extract("atividades de junho"))
    assert tr.start.day == 1
    assert tr.end.day == 30  # junho tem 30 dias


def test_temporal_absent_returns_none():
    te = TemporalExtractor(now_fn=lambda: FIXED_NOW)
    assert run(te.extract("onde parei no curso")) is None


def test_temporal_slash_format_is_explicit():
    te = TemporalExtractor(now_fn=lambda: FIXED_NOW)
    tr = run(te.extract("o que fiz em 11/06"))
    assert tr.start.date() == datetime(2026, 6, 11).date()
    assert tr.detection_method == "explicit"


# --- camada 3: clarificação (§6) ----------------------------------------


def test_empty_query_clarifies_without_calling_layers():
    out = run(make_agent().triage("   "))
    assert isinstance(out, ClarificationNeeded)
    assert out.reason == "low_confidence"


def test_low_confidence_triggers_clarification():
    out = run(make_agent().triage("isso aí"))
    assert isinstance(out, ClarificationNeeded)
    assert out.reason == "low_confidence"
    assert out.detected_options  # oferece opções ao usuário


def test_missing_temporal_in_diary_query_clarifies():
    out = run(make_agent().triage("o que fiz no diário"))
    assert isinstance(out, ClarificationNeeded)
    assert out.reason == "missing_temporal"


def test_all_marker_skips_temporal_clarification():
    out = run(make_agent().triage("me mostra tudo do diário"))
    assert isinstance(out, TriageResult)
    assert out.intent == "diary_lookup"
    assert out.temporal_filter is None


def test_diary_with_temporal_does_not_clarify():
    out = run(make_agent().triage("o que fiz no dia 11"))
    assert isinstance(out, TriageResult)
    assert out.intent == "diary_lookup"
    assert out.temporal_filter is not None


def test_clarification_round_limit_forces_broad_fallback():
    # 2ª rodada (== max) sem clareza: cai para fallback amplo, não clarifica.
    out = run(make_agent().triage("isso aí", clarification_round=2))
    assert isinstance(out, TriageResult)
    assert out.classification_method == "fallback"
    assert out.intent == "cross_domain"
    assert set(out.target_rag_collections) == {"diario", "cursos", "referencias"}


# --- camada 2: LLM fallback (com fake) ----------------------------------


class _FakeLLM:
    """IntentLLM determinístico para exercitar o caminho da camada 2."""

    def __init__(self, result: TriageResult):
        self.result = result
        self.calls = 0

    async def classify(self, query, rule_hint) -> TriageResult:
        self.calls += 1
        return self.result


def test_llm_called_when_rules_below_threshold():
    fake = _FakeLLM(
        TriageResult(
            intent="course_status",
            confidence=0.82,
            classification_method="llm",
            reasoning="fake",
        )
    )
    # Query sem nenhuma keyword de domínio → regras retornam intent None → LLM.
    out = run(make_agent(llm=fake).triage("me explica isso melhor por favor"))
    assert fake.calls == 1
    assert isinstance(out, TriageResult)
    assert out.intent == "course_status"
    # roteamento re-derivado do intent, não confiando no LLM
    assert out.target_rag_collections == ["cursos"]
    assert out.classification_method in {"llm", "hybrid"}


def test_llm_not_called_when_rules_confident():
    fake = _FakeLLM(
        TriageResult(intent="meta", confidence=0.99, classification_method="llm")
    )
    out = run(make_agent(llm=fake).triage("onde parei no curso de Data Engineer"))
    assert fake.calls == 0
    assert out.intent == "course_status"
    assert out.classification_method == "rules"


def test_llm_failure_degrades_to_rules():
    class _BoomLLM:
        async def classify(self, query, rule_hint):
            raise RuntimeError("ollama down")

    out = run(make_agent(llm=_BoomLLM()).triage("isso aí"))
    # rules deram None → sem LLM utilizável → clarificação
    assert isinstance(out, ClarificationNeeded)


# --- roteamento ----------------------------------------------------------


def test_route_for_intent_returns_copies():
    a = route_for_intent("diary_lookup")
    a[0].append("x")
    assert route_for_intent("diary_lookup")[0] == ["diario"]  # não mutou a tabela


# --- OTel (§8) -----------------------------------------------------------


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


def test_otel_spans_emitted_per_layer():
    tracer, exporter = _in_memory_tracer()
    agent = make_agent(tracer=tracer)
    run(agent.triage("o que fiz no dia 11"))
    names = {s.name for s in exporter.get_finished_spans()}
    assert "agent1.triage" in names
    assert "agent1.rules.evaluate" in names
    assert "agent1.temporal.dateparser" in names


def test_otel_llm_span_present_when_llm_used():
    tracer, exporter = _in_memory_tracer()
    fake = _FakeLLM(
        TriageResult(intent="meta", confidence=0.8, classification_method="llm")
    )
    agent = make_agent(llm=fake, tracer=tracer)
    run(agent.triage("me fala algo vago aí sobre tudo"))
    names = {s.name for s in exporter.get_finished_spans()}
    assert "agent1.llm.classify" in names


def test_otel_parent_span_has_output_kind_attribute():
    tracer, exporter = _in_memory_tracer()
    agent = make_agent(tracer=tracer)
    run(agent.triage("ok"))
    parent = next(s for s in exporter.get_finished_spans() if s.name == "agent1.triage")
    assert parent.attributes["output_kind"] == "clarification_needed"


# --- integração: golden dataset (§10.3) ---------------------------------


def _load_golden():
    path = Path(__file__).parent / "fixtures" / "triage_golden.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def golden():
    return _load_golden()


def test_golden_dataset_intent_accuracy(golden):
    agent = make_agent()
    correct = 0
    total = 0
    failures = []
    for case in golden:
        if "expected_intent" not in case:
            continue
        total += 1
        out = run(agent.triage(case["query"]))
        got = out.intent if isinstance(out, TriageResult) else f"<{out.kind}>"
        if got == case["expected_intent"]:
            correct += 1
        else:
            failures.append((case["query"], case["expected_intent"], got))
    accuracy = correct / total
    assert accuracy >= 0.8, f"acurácia {accuracy:.0%} < 80%; falhas: {failures}"


def test_golden_dataset_clarification_cases(golden):
    agent = make_agent()
    for case in golden:
        if case.get("expected_kind") != "clarification_needed":
            continue
        out = run(agent.triage(case["query"]))
        assert isinstance(out, ClarificationNeeded), case["query"]
        assert out.reason == case["expected_reason"], case["query"]


def test_golden_dataset_routing_and_filters(golden):
    agent = make_agent()
    for case in golden:
        if "expected_intent" not in case:
            continue
        out = run(agent.triage(case["query"]))
        if not isinstance(out, TriageResult):
            continue
        if "expected_collections" in case:
            assert sorted(out.target_rag_collections) == sorted(
                case["expected_collections"]
            ), case["query"]
        if "expected_tiers" in case:
            assert sorted(out.target_memory_tiers) == sorted(
                case["expected_tiers"]
            ), case["query"]
        if "expected_filters" in case:
            for k, v in case["expected_filters"].items():
                assert out.structured_filters.get(k) == v, case["query"]
        if case.get("expected_temporal") is True:
            assert out.temporal_filter is not None, case["query"]
