"""Stub do Agente 3 — persistência de turno em Episodic com sanitização PII.

Implementação enxuta da SPEC-008 §7 para destravar continuidade end-to-end
antes da SPEC-007 (Agente 3 real). A signature é compatível com a do agente
real: SPEC-007 substitui apenas a implementação.
"""

from __future__ import annotations

from typing import Optional

from opentelemetry.trace import Tracer

from src.memory.episodic import EpisodicMemory
from src.memory.guardrails import PIIGuardrails
from src.observability.tracer import get_tracer


async def persist_turn_stub(
    *,
    user_id: str,
    session_id: str,
    user_message: str,
    agent_response: str,
    intent: Optional[str],
    episodic_memory: EpisodicMemory,
    tracer: Optional[Tracer] = None,
) -> Optional[str]:
    """Sanitiza PII e grava em EpisodicMemory.

    NÃO extrai fatos para SemanticMemory (responsabilidade da SPEC-007 real).
    Best-effort: em qualquer erro, registra atributo OTel e retorna None.
    Retorna `conversation_id` em caso de sucesso.
    """
    tr = tracer or get_tracer()
    with tr.start_as_current_span("orchestrator.persist_turn_stub") as span:
        try:
            pii_found = PIIGuardrails.extract_pii(
                f"{user_message}\n{agent_response}"
            )
            clean_user = PIIGuardrails.sanitize(user_message)
            clean_agent = PIIGuardrails.sanitize(agent_response)
            conversation_id = episodic_memory.add_conversation(
                user_id=user_id,
                session_id=session_id,
                user_message=clean_user,
                agent_response=clean_agent,
                intent=intent,
                pii_sanitized=True,
            )
            span.set_attribute("success", True)
            span.set_attribute("pii_types_found", list(pii_found.keys()))
            span.set_attribute("conversation_id", conversation_id)
            return conversation_id
        except Exception as e:
            span.set_attribute("success", False)
            span.set_attribute("error", str(e))
            return None
