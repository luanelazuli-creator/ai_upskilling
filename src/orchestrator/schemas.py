"""Saída tipada do Orquestrador (SPEC-008 §8).

União discriminada por `kind` consumida pela CLI (hoje) e por UI/API (depois).
"""

from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, ConfigDict

from src.agents.synthesis.schemas import SynthesisOutput
from src.agents.triage.schemas import ClarificationNeeded


class AnswerResponse(BaseModel):
    """Resposta sintetizada (com ou sem evidência)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    kind: Literal["answer"] = "answer"
    synthesis: SynthesisOutput  # SynthesisResult | NoEvidence
    session_id: str
    turn: int
    elapsed_ms: int


class ClarificationResponse(BaseModel):
    """Pergunta de clarificação devolvida ao usuário."""

    kind: Literal["clarification"] = "clarification"
    triage: ClarificationNeeded
    session_id: str
    turn: int
    elapsed_ms: int


class MetaResponse(BaseModel):
    """Resposta canned para `intent=meta` (sem invocar LLM)."""

    kind: Literal["meta"] = "meta"
    message: str
    session_id: str
    turn: int
    elapsed_ms: int


class ErrorResponse(BaseModel):
    """Falha que escapou da política best-effort."""

    kind: Literal["error"] = "error"
    stage: Literal[
        "triage", "retrieval", "context", "synthesis", "persist", "unknown"
    ]
    message: str
    session_id: str
    turn: int
    elapsed_ms: int = 0


OrchestratorResponse = Union[
    AnswerResponse, ClarificationResponse, MetaResponse, ErrorResponse
]
