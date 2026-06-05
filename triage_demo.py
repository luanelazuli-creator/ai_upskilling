"""Demo interativa do Agente 1 — Triagem (SPEC-005).

Uso:
    python triage_demo.py              # só regras + dateparser (offline)
    python triage_demo.py --llm        # regras + dateparser + LLM (requer Ollama)

Mostra para cada query: intent, confiança, coleções, tiers, janela temporal,
método de classificação e regras disparadas.
"""

import asyncio
import sys

from src.agents.agent1_triage import TriageAgent
from src.agents.triage.rules import TriageRuleEngine
from src.agents.triage.schemas import ClarificationNeeded, TriageResult
from src.agents.triage.temporal import TemporalExtractor
from src.config import settings


def build_agent(use_llm: bool) -> TriageAgent:
    llm = None
    temporal_llm = None
    if use_llm:
        try:
            from src.agents.triage.llm_classifier import build_default_llms
            llm, temporal_llm = build_default_llms(settings)
            print(f"  LLM: {settings.ollama_triage_model} em {settings.ollama_base_url}")
        except Exception as e:
            print(f"  LLM indisponivel ({e}); usando so regras.")

    return TriageAgent(
        rule_engine=TriageRuleEngine(),
        temporal_extractor=TemporalExtractor(llm=temporal_llm),
        llm=llm,
    )


def render(out) -> None:
    if isinstance(out, TriageResult):
        print(f"\n  intent:       {out.intent}")
        print(f"  confianca:    {out.confidence:.2f}")
        print(f"  metodo:       {out.classification_method}")
        print(f"  colecoes RAG: {out.target_rag_collections or '(nenhuma)'}")
        print(f"  tiers mem:    {out.target_memory_tiers or '(nenhum)'}")
        if out.temporal_filter:
            tf = out.temporal_filter
            print(f"  temporal:     {tf.start.date()} .. {tf.end.date()} ({tf.expression!r}, {tf.detection_method})")
        else:
            print(f"  temporal:     (nenhuma)")
        if out.structured_filters:
            print(f"  filtros:      {out.structured_filters}")
        print(f"  reasoning:    {out.reasoning}")
    elif isinstance(out, ClarificationNeeded):
        print(f"\n  [clarificacao] {out.question}")
        print(f"  motivo:  {out.reason}")
        print(f"  opcoes:  {out.detected_options}")
        print(f"  conf:    {out.confidence:.2f}")
    print()


async def main():
    use_llm = "--llm" in sys.argv
    print("=== Triagem Demo (SPEC-005) ===")
    print(f"  Modo: {'regras + LLM' if use_llm else 'so regras + dateparser (offline)'}")
    agent = build_agent(use_llm)
    print("  Ctrl+C para sair.\n")

    while True:
        try:
            query = input("voce > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\ntchau.")
            break
        if not query:
            continue
        if query in ("/quit", "/sair"):
            break

        try:
            out = await agent.triage(query)
            render(out)
        except Exception as e:
            print(f"\n  [erro] {e}\n")


if __name__ == "__main__":
    asyncio.run(main())
