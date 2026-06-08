"""Wrapper Pydantic AI + Ollama para a síntese (SPEC-006 §9.1).

Implementa o Protocol `SynthesisLLM` declarado em `agent2_synthesis`. Isolado
em arquivo próprio para que o núcleo do agente continue rodando offline (basta
não injetar este wrapper).

Convenção de modelo (alinhada com SPEC-005 / agent1):
    Ollama via endpoint OpenAI-compatível (`/v1`), api_key="ollama".
"""

from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from src.config import Settings

from .prompts import SYNTHESIS_SYSTEM_PROMPT
from .schemas import SynthesisResult


def _build_model(settings: Settings) -> OpenAIModel:
    provider = OpenAIProvider(
        base_url=f"{settings.ollama_base_url}/v1",
        api_key="ollama",  # Ollama ignora; SDK exige algo não-vazio.
    )
    return OpenAIModel(settings.ollama_synthesis_model, provider=provider)


class PydanticAISynthesisLLM:
    """Gera `SynthesisResult` a partir do prompt renderizado.

    `NoEvidence` é decidido por código (pré-check + validador) — não pela LLM —
    para manter o caminho determinístico e fora do JSON livre do modelo.
    """

    def __init__(self, settings: Settings):
        self._agent = Agent(
            _build_model(settings),
            output_type=SynthesisResult,
            system_prompt=SYNTHESIS_SYSTEM_PROMPT,
        )

    async def synthesize(self, prompt: str) -> SynthesisResult:
        result = await self._agent.run(prompt)
        return result.output


def build_default_synthesis_llm(settings: Settings) -> PydanticAISynthesisLLM:
    """Factory do classificador LLM. Use no caminho com Ollama vivo."""
    return PydanticAISynthesisLLM(settings)
