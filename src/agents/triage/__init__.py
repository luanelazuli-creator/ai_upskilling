"""Agente 1 — Triagem e Contexto Temporal (SPEC-005).

Transforma uma query em linguagem natural em um plano de busca tipado:
intent, janela temporal, coleções RAG e tiers de memória.

Exports públicos:
    - TriageAgent: orquestra as 3 camadas (regras → LLM → clarificação).
    - TriageResult, ClarificationNeeded, TriageOutput, TemporalRange: schemas.
    - TriageRuleEngine: camada determinística (regras de palavra-chave).
    - TemporalExtractor: detecção de janela temporal (dateparser + LLM).
"""

from __future__ import annotations

from .schemas import (
    ClarificationNeeded,
    TemporalRange,
    TriageOutput,
    TriageResult,
)

__all__ = [
    "ClarificationNeeded",
    "TemporalRange",
    "TriageOutput",
    "TriageResult",
]
