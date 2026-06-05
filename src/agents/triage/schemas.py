"""Schemas de saída da triagem (SPEC-005 §3).

União discriminada por `kind`:
    - TriageResult: classificação bem-sucedida com plano de busca.
    - ClarificationNeeded: confiança baixa ou ambiguidade → pergunta ao usuário.

O orquestrador (SPEC-008) despacha por `kind` sem `isinstance`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field

# Conjuntos fechados reutilizados como Literals e para validação.
IntentLiteral = Literal[
    "diary_lookup",
    "course_status",
    "reference_lookup",
    "golden_prompt_request",
    "user_profile",
    "conversation_recall",
    "cross_domain",
    "meta",
]

RagCollectionLiteral = Literal["diario", "cursos", "referencias"]

MemoryTierLiteral = Literal["episodic_recent", "episodic_semantic", "semantic"]


class TemporalRange(BaseModel):
    """Janela temporal detectada na query (SPEC-005 §5)."""

    start: datetime
    end: datetime
    expression: str  # trecho original: "semana passada", "junho de 2026"
    detection_method: Literal["dateparser", "llm", "explicit"]


class TriageResult(BaseModel):
    """Plano de busca tipado produzido pela triagem."""

    kind: Literal["triage_result"] = "triage_result"
    intent: IntentLiteral
    target_rag_collections: list[RagCollectionLiteral] = Field(default_factory=list)
    target_memory_tiers: list[MemoryTierLiteral] = Field(default_factory=list)
    temporal_filter: Optional[TemporalRange] = None
    structured_filters: dict = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    classification_method: Literal["rules", "llm", "hybrid", "fallback"]
    reasoning: str = ""  # humano-legível; vai para OTel


class ClarificationNeeded(BaseModel):
    """Interrompe o fluxo e devolve uma pergunta ao usuário (SPEC-005 §6)."""

    kind: Literal["clarification_needed"] = "clarification_needed"
    reason: Literal["low_confidence", "multiple_intents", "missing_temporal"]
    question: str
    detected_options: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


TriageOutput = Union[TriageResult, ClarificationNeeded]
