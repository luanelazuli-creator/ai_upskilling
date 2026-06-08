"""Demo interativa do Agente 2 — Síntese (SPEC-006).

Dois modos:
    python synthesis_demo.py             → offline (FakeLLM controlado)
    python synthesis_demo.py --llm       → com Ollama local (modelo mistral)
    python synthesis_demo.py --llm --real-rag  → Ollama + busca real no ChromaDB

Uso no outro ambiente:
    1. Garanta que o venv está ativado e o Ollama rodando com `mistral`.
    2. Se quiser testar com dados reais, rode a ingestão antes:
         python -m scripts.ingest --domain all
    3. Depois:
         python synthesis_demo.py --llm --real-rag

Exemplo rápido (offline):
    python synthesis_demo.py
    > o que fiz no dia 11
    → resposta fake com citações

Exemplo com Ollama + RAG real:
    python synthesis_demo.py --llm --real-rag
    > o que fiz no dia 11
    → busca no ChromaDB → monta bundle real → Ollama sintetiza com citações
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Garante import de `src` ao rodar como script direto.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.agents.agent2_synthesis import SynthesisAgent, SynthesisLLM  # noqa: E402
from src.agents.synthesis.schemas import (  # noqa: E402
    Citation,
    NoEvidence,
    SynthesisResult,
)
from src.config import get_settings  # noqa: E402
from src.memory.context_bundle import ContextBundle  # noqa: E402
from tests.fixtures.synthesis_bundles import diary_bundle, facts_only_bundle  # noqa: E402


# ------------------------------------------------------------------ Fake LLM


class _FakeLLM:
    """LLM determinístico para demo offline."""

    async def synthesize(self, prompt: str) -> SynthesisResult:
        # Extrai os ids de chunk do prompt para simular citação real.
        import re
        ids = re.findall(r"\[(chunk_\w+)\]", prompt)
        fact_ids = re.findall(r"\[(fact:\w+)\]", prompt)
        all_ids = ids + fact_ids

        if not all_ids:
            return SynthesisResult(
                answer="Não encontrei informação suficiente no bundle fornecido.",
                citations=[],
                confidence=0.3,
                used_intent="unknown",
            )

        # Gera resposta fake mas plausível
        cite_str = "".join(f"[{cid}]" for cid in all_ids[:3])
        answer = f"Com base nas fontes, posso afirmar o seguinte {cite_str}."
        citations = [
            Citation(
                chunk_id=cid,
                source_file="demo",
                collection="diario",
                relevance_score=0.8,
            )
            for cid in all_ids[:3]
        ]
        return SynthesisResult(
            answer=answer,
            citations=citations,
            confidence=0.85,
            used_intent="diary_lookup",
        )


# ------------------------------------------------------------ bundle de RAG real


def _build_real_bundle(query: str, settings) -> ContextBundle:
    """Monta um ContextBundle consultando o ChromaDB real."""
    from src.rag.embedder import get_embedding_function
    from src.rag.retriever import SemanticRetriever

    retriever = SemanticRetriever(
        db_path=settings.vectorstore_path,
        embedding_function=get_embedding_function(settings.embedding_model),
    )

    # Busca nas 3 coleções RAG (simula o que o orquestrador faria).
    chunks = []
    for collection in ["diario", "cursos", "referencias"]:
        try:
            found = retriever.retrieve(query, collection=collection, top_k=5)
            chunks.extend(found)
        except Exception as e:
            print(f"  ⚠ coleção '{collection}' falhou: {e}")

    chunks.sort(key=lambda c: c.relevance_score or 0, reverse=True)

    return ContextBundle(
        rag_chunks=chunks[:10],
        metadata={
            "intent": "cross_domain",
            "session_id": "demo",
            "turn": 1,
        },
    )


# ------------------------------------------------------------------ renderer


def _render(out):
    if out.kind == "synthesis_result":
        print(f"\n  Resposta: {out.answer}")
        if out.citations:
            for c in out.citations:
                print(f"    └ [{c.chunk_id}] {c.source_file} "
                      f"({c.collection}, score={c.relevance_score:.2f})")
        print(f"  (confidence={out.confidence:.2f}, intent={out.used_intent})")
    else:
        print(f"\n  ❌ NoEvidence: {out.reason}")
        print(f"  Sugestão: {out.suggestion}")
        print(f"  (intent={out.used_intent})")
    print()


# ------------------------------------------------------------------ main


async def _interactive(agent: SynthesisAgent, use_real_rag: bool, settings):
    """Loop REPL interativo."""
    print("──────────────────────────────────────────────────")
    print("  Synthesis Agent Demo (SPEC-006)")
    mode = "Ollama" if agent._llm is not None else "offline (FakeLLM)"
    rag = " + RAG real" if use_real_rag else " + bundle mockado"
    print(f"  Modo: {mode}{rag}")
    print("  Digite sua pergunta. Ctrl+C para sair.")
    print("  Comandos: /diary  /facts  /empty  (troca bundle)")
    print("──────────────────────────────────────────────────\n")

    current_bundle_fn = "diary"

    while True:
        try:
            query = input("você > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\ntchau.")
            break

        if not query:
            continue

        # Slash commands para trocar bundle.
        if query == "/diary":
            current_bundle_fn = "diary"
            print("  → bundle: diary_bundle()\n")
            continue
        if query == "/facts":
            current_bundle_fn = "facts"
            print("  → bundle: facts_only_bundle()\n")
            continue
        if query == "/empty":
            current_bundle_fn = "empty"
            print("  → bundle: empty_bundle()\n")
            continue

        # Monta bundle.
        if use_real_rag:
            print("  🔍 buscando no ChromaDB...")
            bundle = _build_real_bundle(query, settings)
            print(f"  → {len(bundle.rag_chunks)} chunks recuperados")
        elif current_bundle_fn == "facts":
            bundle = facts_only_bundle()
        elif current_bundle_fn == "empty":
            from tests.fixtures.synthesis_bundles import empty_bundle
            bundle = empty_bundle()
        else:
            bundle = diary_bundle()

        out = await agent.synthesize(query, bundle)
        _render(out)


def main():
    parser = argparse.ArgumentParser(description="Demo do Agente de Síntese (SPEC-006)")
    parser.add_argument("--llm", action="store_true", help="Usar Ollama real (mistral)")
    parser.add_argument("--real-rag", action="store_true",
                        help="Buscar no ChromaDB real em vez de bundle mockado")
    args = parser.parse_args()

    settings = get_settings()

    llm: SynthesisLLM
    if args.llm:
        from src.agents.synthesis.llm_classifier import build_default_synthesis_llm
        llm = build_default_synthesis_llm(settings)
        print(f"✓ LLM: {settings.ollama_synthesis_model} via Ollama")
    else:
        llm = _FakeLLM()
        print("✓ LLM: FakeLLM (offline)")

    agent = SynthesisAgent(llm=llm)
    asyncio.run(_interactive(agent, args.real_rag, settings))


if __name__ == "__main__":
    main()
