"""Camada 2 da triagem — classificador LLM via Pydantic AI + Ollama (SPEC-005 §4.2).

Implementa os Protocols `IntentLLM` (classificação) e `TemporalLLM` (janela
temporal). Usa o endpoint OpenAI-compatível do Ollama (`/v1`).

Isolado de propósito: `agent1_triage` e `temporal` só dependem dos Protocols,
então todo o núcleo roda offline. Estas classes só são instanciadas quando há
Ollama disponível (caminho de smoke test / produção local).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from src.config import Settings

from .prompts import TEMPORAL_SYSTEM_PROMPT, TRIAGE_SYSTEM_PROMPT
from .rules import RuleEvaluation
from .schemas import TemporalRange, TriageResult


def _build_model(settings: Settings) -> OpenAIModel:
    """Modelo Ollama exposto via API OpenAI-compatível."""
    provider = OpenAIProvider(
        base_url=f"{settings.ollama_base_url}/v1",
        api_key="ollama",  # Ollama ignora; o SDK exige algo não-vazio.
    )
    return OpenAIModel(settings.ollama_triage_model, provider=provider)


class PydanticAITriageLLM:
    """Classificador de intent (camada 2)."""

    def __init__(self, settings: Settings):
        self._agent = Agent(
            _build_model(settings),
            output_type=TriageResult,
            system_prompt=TRIAGE_SYSTEM_PROMPT,
        )

    async def classify(self, query: str, rule_hint: RuleEvaluation) -> TriageResult:
        hint = ""
        if rule_hint.intent is not None:
            hint = (
                f"\n\nDica das regras determinísticas (pode estar incompleta): "
                f"intent provável = {rule_hint.intent} "
                f"(confiança {rule_hint.confidence:.2f})."
            )
        prompt = f"Mensagem do usuário: {query}{hint}"
        result = await self._agent.run(prompt)
        return result.output


class PydanticAITemporalLLM:
    """Extrator de janela temporal por LLM (camada B)."""

    def __init__(self, settings: Settings):
        self._settings = settings

    async def extract(self, query: str, now: datetime) -> Optional[TemporalRange]:
        agent = Agent(
            _build_model(self._settings),
            output_type=Optional[TemporalRange],
            system_prompt=TEMPORAL_SYSTEM_PROMPT.format(now=now.isoformat()),
        )
        result = await agent.run(f"Mensagem do usuário: {query}")
        return result.output


def build_default_llms(
    settings: Settings,
) -> tuple[PydanticAITriageLLM, PydanticAITemporalLLM]:
    """Factory dos dois classificadores LLM. Use no caminho com Ollama vivo."""
    return PydanticAITriageLLM(settings), PydanticAITemporalLLM(settings)
