"""Second Brain — REPL formal (SPEC-008 §10).

Substitui o `chat_demo.py` (que vira referência descartável) por um REPL
fino que delega tudo ao `Orchestrator.handle_turn`.

Uso:
    python chat.py

Pré-requisitos:
    1. Ollama rodando com modelos:
         ollama pull mistral      (síntese)
         ollama pull qwen2.5:3b   (triagem)
    2. Dados ingeridos:
         python -m scripts.ingest --domain all

Slash-commands:
    /wm       — imprime estado atual da Working Memory
    /session  — session_id, turn_count, last_intent
    /clear    — reseta Working Memory (mantém a sessão)
    /quit     — sai
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import get_settings  # noqa: E402
from src.orchestrator import (  # noqa: E402
    AnswerResponse,
    ClarificationResponse,
    ErrorResponse,
    MetaResponse,
    Orchestrator,
    OrchestratorResponse,
)
from src.agents.synthesis.schemas import NoEvidence, SynthesisResult  # noqa: E402


def _render(r: OrchestratorResponse) -> None:
    if isinstance(r, AnswerResponse):
        synth = r.synthesis
        if isinstance(synth, SynthesisResult):
            print(f"\n[turno {r.turn}] {synth.answer}")
            for c in synth.citations:
                print(
                    f"  └ [{c.chunk_id}] {c.source_file} "
                    f"(score {c.relevance_score:.2f})"
                )
            print(f"  (confidence={synth.confidence:.2f}, {r.elapsed_ms}ms)\n")
        elif isinstance(synth, NoEvidence):
            print(f"\n[turno {r.turn}] {synth.suggestion}")
            print(f"  (motivo: {synth.reason}, {r.elapsed_ms}ms)\n")
    elif isinstance(r, ClarificationResponse):
        print(f"\n[turno {r.turn}] {r.triage.question}")
        for opt in r.triage.detected_options:
            print(f"  • {opt}")
        print()
    elif isinstance(r, MetaResponse):
        print(f"\n[turno {r.turn}] {r.message}\n")
    elif isinstance(r, ErrorResponse):
        print(f"\n[erro/{r.stage}] {r.message}\n")


def _handle_slash(orch: Orchestrator, query: str) -> bool:
    """Retorna True se foi um slash-command (consumido); False caso contrário."""
    cmd = query.strip().lower()
    if cmd in ("/quit", "/sair", "/exit"):
        print("tchau.")
        sys.exit(0)
    if cmd == "/wm":
        print()
        print(orch.session.working_memory.to_context_block())
        print()
        return True
    if cmd == "/session":
        s = orch.session
        print(
            f"\n  session_id={s.session_id[:8]}…  "
            f"turn={s.turn_count}  last_intent={s.last_intent}\n"
        )
        return True
    if cmd == "/clear":
        orch.session.working_memory.clear()
        print("\n  working memory limpa.\n")
        return True
    return False


async def main() -> None:
    settings = get_settings()
    print("╔══════════════════════════════════════════════════╗")
    print("║     Second Brain — Orquestrador (SPEC-008)      ║")
    print("╚══════════════════════════════════════════════════╝")
    print(f"  Triagem LLM: {settings.ollama_triage_model}")
    print(f"  Síntese LLM: {settings.ollama_synthesis_model}")
    print(f"  Vector store: {settings.vectorstore_path}")
    print()

    orch = Orchestrator.from_settings(settings)
    print(
        f"  Sessão {orch.session.session_id[:8]}… iniciada. "
        f"Slash: /wm /session /clear /quit. Ctrl+C para sair.\n"
    )

    while True:
        try:
            query = input("você > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\ntchau.")
            break
        if not query:
            continue
        if query.startswith("/") and _handle_slash(orch, query):
            continue

        response = await orch.handle_turn(query)
        _render(response)


if __name__ == "__main__":
    asyncio.run(main())
