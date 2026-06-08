"""Schemas de saída da síntese (SPEC-006 §3).

União discriminada por `kind`:
    - SynthesisResult: resposta ancorada com citações inline `[id]`.
    - NoEvidence: bundle não cobre a query; agente prefere dizer "não sei".

O orquestrador (SPEC-008) e os evals (SPEC-009) despacham por `kind` sem
`isinstance`. A LLM nunca emite `NoEvidence` diretamente — esse caminho é
controlado pelo pré-check e pelo validador (§5, §8).
"""

from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, Field

NoEvidenceReason = Literal[
    "empty_bundle",
    "low_relevance",
    "off_topic",
]


class Citation(BaseModel):
    """Metadado de um chunk citado inline (SPEC-006 §4.2)."""

    chunk_id: str  # `chunk_de_001` ou `fact:f_42`
    source_file: str
    collection: str  # diario | cursos | referencias | user_facts
    relevance_score: float


class SynthesisResult(BaseModel):
    """Resposta sintetizada com ancoragem em fontes do bundle."""

    kind: Literal["synthesis_result"] = "synthesis_result"
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    used_intent: str  # ecoado do bundle para auditoria


class NoEvidence(BaseModel):
    """Resposta de "não sei" — preferida à alucinação (SPEC-006 §5)."""

    kind: Literal["no_evidence"] = "no_evidence"
    reason: NoEvidenceReason
    suggestion: str
    used_intent: str


SynthesisOutput = Union[SynthesisResult, NoEvidence]
