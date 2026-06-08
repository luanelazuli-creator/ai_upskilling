"""Diagnóstico rápido: o que está rolando entre o app e o Ollama?

Roda 3 checks isolados:
    1. Ollama vivo? quais modelos estão instalados?
    2. Endpoint OpenAI-compat (`/v1`) responde com o modelo configurado?
    3. O wrapper Pydantic AI da síntese consegue fazer uma chamada real?

Uso:  python diagnose_ollama.py
"""

from __future__ import annotations

import asyncio
import sys
import traceback

import httpx

from src.config import get_settings


async def check_ollama_alive(base_url: str) -> list[str]:
    print(f"\n[1] GET {base_url}/api/tags")
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{base_url}/api/tags")
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        print(f"    ✓ Ollama vivo. Modelos instalados: {models}")
        return models


async def check_openai_endpoint(base_url: str, model: str) -> None:
    print(f"\n[2] POST {base_url}/v1/chat/completions  (model={model})")
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{base_url}/v1/chat/completions",
            headers={"Authorization": "Bearer ollama"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": "responda apenas 'ok'"}],
                "stream": False,
            },
        )
        print(f"    status={r.status_code}")
        if r.status_code != 200:
            print(f"    body: {r.text[:500]}")
            r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        print(f"    ✓ Resposta: {content!r}")


async def check_pydantic_ai_wrapper() -> None:
    print("\n[3] PydanticAISynthesisLLM.synthesize(...)")
    from src.agents.synthesis.llm_classifier import build_default_synthesis_llm

    settings = get_settings()
    llm = build_default_synthesis_llm(settings)
    # Prompt minimalista só pra ver se o JSON estruturado sai.
    prompt = (
        "Pergunta: o que é teste?\n\n"
        "Contexto (chunk 1): 'teste é uma forma de verificar algo'.\n\n"
        "Responda em JSON com campos: answer, citations=[], confidence, used_intent='general'."
    )
    result = await llm.synthesize(prompt)
    print(f"    ✓ result.answer={result.answer!r}")
    print(f"      confidence={result.confidence}")


async def main():
    settings = get_settings()
    print(f"base_url = {settings.ollama_base_url}")
    print(f"synthesis_model = {settings.ollama_synthesis_model}")
    print(f"triage_model    = {settings.ollama_triage_model}")

    try:
        models = await check_ollama_alive(settings.ollama_base_url)
    except Exception as e:
        print(f"    ✗ Ollama não respondeu: {e!r}")
        return

    if settings.ollama_synthesis_model not in models:
        print(
            f"\n    ⚠ '{settings.ollama_synthesis_model}' NÃO está na lista de modelos.\n"
            f"      Opções:\n"
            f"        (a) ollama pull {settings.ollama_synthesis_model}\n"
            f"        (b) export OLLAMA_SYNTHESIS_MODEL=<um modelo que você tenha>\n"
            f"            (no Windows PS:  $env:OLLAMA_SYNTHESIS_MODEL='qwen2.5:3b')"
        )

    try:
        await check_openai_endpoint(
            settings.ollama_base_url, settings.ollama_synthesis_model
        )
    except Exception:
        print("    ✗ Falha na chamada OpenAI-compat:")
        traceback.print_exc()
        return

    try:
        await check_pydantic_ai_wrapper()
    except Exception:
        print("    ✗ Falha no wrapper Pydantic AI (esta é a causa do 'LLM indisponível'):")
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
