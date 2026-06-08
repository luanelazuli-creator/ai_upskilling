"""Agente 2 — Síntese e Resposta Ancorada (SPEC-006).

Transforma um `ContextBundle` + query em `SynthesisResult` (com citações
inline obrigatórias) ou `NoEvidence` quando o bundle não cobre a pergunta.

Exports públicos:
    - SynthesisResult, NoEvidence, SynthesisOutput, Citation: schemas Pydantic.
    - NoEvidenceReason: literais permitidos de motivo.
"""

from __future__ import annotations

from .schemas import (
    Citation,
    NoEvidence,
    NoEvidenceReason,
    SynthesisOutput,
    SynthesisResult,
)

__all__ = [
    "Citation",
    "NoEvidence",
    "NoEvidenceReason",
    "SynthesisOutput",
    "SynthesisResult",
]
