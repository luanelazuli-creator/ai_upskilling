"""Camada 1 da triagem — regras determinísticas (SPEC-005 §4.1).

Classifica por palavras-chave de domínio. Resolve a maioria das queries sem
chamar o LLM. Quando duas regras de domínios RAG distintos disparam, marca
`cross_domain` com confiança = média dos hits.

A normalização remove acentos e caixa, de modo que os padrões podem ser
escritos em ASCII minúsculo — robusto a usuários que omitem acentuação.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from statistics import mean
from typing import Optional

from .routing import route_for_intent


def normalize(text: str) -> str:
    """Minúsculas + remoção de acentos (NFKD) para casamento robusto."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


@dataclass(frozen=True)
class KeywordRule:
    name: str
    intent: str
    patterns: tuple[str, ...]  # regex já em ASCII minúsculo
    confidence: float
    structured_filters: dict = field(default_factory=dict)


# Tabela de regras (SPEC-005 §4.1). Padrões escritos sem acento (ver normalize()).
RULES: tuple[KeywordRule, ...] = (
    KeywordRule(
        "datas_explicitas",
        "diary_lookup",
        (r"\bdia \d+", r"\b\d{1,2}/\d{1,2}", r"\bontem\b", r"\bhoje\b", r"\banteontem\b"),
        0.9,
    ),
    KeywordRule(
        "termos_diario",
        "diary_lookup",
        (r"\bdiario\b", r"\batividade", r"\bimpedimento", r"\bpendencia"),
        0.85,
    ),
    KeywordRule(
        "termos_curso",
        "course_status",
        (r"\bcurso", r"\bcertificac", r"\btrilha\b", r"\baprendizado\b", r"onde parei"),
        0.85,
    ),
    KeywordRule(
        "termos_manual",
        "reference_lookup",
        (r"como fac", r"como pedir", r"\bmanual\b", r"\bprocedimento"),
        0.8,
    ),
    KeywordRule(
        "termos_stakeholder",
        "reference_lookup",
        (r"quem e\b", r"responsavel por", r"contato de"),
        0.85,
        {"category": "stakeholders"},
    ),
    KeywordRule(
        "termos_glossario",
        "reference_lookup",
        (r"o que significa", r"definicao de"),
        0.8,
        {"category": "glossario"},
    ),
    KeywordRule(
        "golden_prompt",
        "golden_prompt_request",
        (r"\btemplate\b", r"prompt para", r"qual prompt"),
        0.85,
        {"type": "golden_prompt"},
    ),
    KeywordRule(
        "auto_referencia",
        "user_profile",
        (r"minhas preferencias", r"o que sabe de mim", r"quem sou", r"sobre mim"),
        0.9,
    ),
    KeywordRule(
        "recall_conversacional",
        "conversation_recall",
        (r"\bvoltando\b", r"\blembra\b", r"como falei", r"antes voce disse"),
        0.85,
    ),
    KeywordRule(
        "meta_agente",
        "meta",
        (r"o que voce faz", r"o que voce sabe fazer", r"o que voce pode fazer",
         r"\bcomandos\b", r"\bajuda\b", r"\bhelp\b"),
        0.85,
    ),
)


@dataclass
class RuleHit:
    rule_name: str
    intent: str
    confidence: float
    structured_filters: dict


@dataclass
class RuleEvaluation:
    """Resultado consolidado da camada de regras.

    `intent is None` significa "nenhuma regra disparou" — a camada LLM (ou a
    política de clarificação) decide.
    """

    intent: Optional[str]
    confidence: float
    target_rag_collections: list[str]
    target_memory_tiers: list[str]
    structured_filters: dict
    is_cross_domain: bool
    fired_rules: list[str]
    reasoning: str


class TriageRuleEngine:
    """Avalia a tabela `RULES` contra uma query normalizada."""

    def __init__(self, rules: tuple[KeywordRule, ...] = RULES):
        self._rules = rules

    def evaluate(self, query: str) -> RuleEvaluation:
        normalized = normalize(query)
        hits = [
            RuleHit(r.name, r.intent, r.confidence, dict(r.structured_filters))
            for r in self._rules
            if any(re.search(p, normalized) for p in r.patterns)
        ]
        return self._resolve(hits)

    # ------------------------------------------------------------------ resolve

    def _resolve(self, hits: list[RuleHit]) -> RuleEvaluation:
        if not hits:
            return RuleEvaluation(
                intent=None,
                confidence=0.0,
                target_rag_collections=[],
                target_memory_tiers=[],
                structured_filters={},
                is_cross_domain=False,
                fired_rules=[],
                reasoning="nenhuma regra disparou",
            )

        # Mantém o hit de maior confiança por intent.
        by_intent: dict[str, RuleHit] = {}
        for h in hits:
            if h.intent not in by_intent or h.confidence > by_intent[h.intent].confidence:
                by_intent[h.intent] = h

        fired = [h.rule_name for h in hits]

        # Coleções RAG distintas implicadas pelos intents que dispararam.
        rag_intents = [i for i in by_intent if route_for_intent(i)[0]]
        distinct_collections = sorted(
            {c for i in by_intent for c in route_for_intent(i)[0]}
        )

        if len(rag_intents) >= 2 and len(distinct_collections) >= 2:
            return self._resolve_cross_domain(by_intent, rag_intents, distinct_collections, fired)

        return self._resolve_single(by_intent, fired)

    def _resolve_single(
        self, by_intent: dict[str, RuleHit], fired: list[str]
    ) -> RuleEvaluation:
        primary = max(by_intent.values(), key=lambda h: h.confidence)
        collections, tiers = route_for_intent(primary.intent)
        return RuleEvaluation(
            intent=primary.intent,
            confidence=primary.confidence,
            target_rag_collections=collections,
            target_memory_tiers=tiers,
            structured_filters=primary.structured_filters,
            is_cross_domain=False,
            fired_rules=fired,
            reasoning=f"regra '{primary.rule_name}' → {primary.intent}",
        )

    def _resolve_cross_domain(
        self,
        by_intent: dict[str, RuleHit],
        rag_intents: list[str],
        distinct_collections: list[str],
        fired: list[str],
    ) -> RuleEvaluation:
        contributing = [by_intent[i] for i in rag_intents]
        merged_filters: dict = {}
        for h in contributing:
            merged_filters.update(h.structured_filters)
        # tiers de memória de eventuais intents não-RAG que também dispararam
        merged_tiers: list[str] = []
        for i in by_intent:
            for t in route_for_intent(i)[1]:
                if t not in merged_tiers:
                    merged_tiers.append(t)
        return RuleEvaluation(
            intent="cross_domain",
            confidence=round(mean(h.confidence for h in contributing), 3),
            target_rag_collections=distinct_collections,
            target_memory_tiers=merged_tiers,
            structured_filters=merged_filters,
            is_cross_domain=True,
            fired_rules=fired,
            reasoning=f"cross_domain: {', '.join(sorted(by_intent))}",
        )
