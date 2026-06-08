"""Demo conversacional — pipeline completo Triagem → RAG → Síntese.

Mini-orquestrador que amarra os dois agentes implementados (SPEC-005 + SPEC-006)
ao retriever RAG (SPEC-004), sem depender do orquestrador formal (SPEC-008).

Uso:
    python chat_demo.py                      # roda com Ollama (mistral + qwen2.5:3b)

Pré-requisitos:
    1. Ollama rodando com modelos instalados:
         ollama pull mistral        (síntese)
         ollama pull qwen2.5:3b    (triagem)
    2. Dados ingeridos:
         python -m scripts.ingest --domain all

Comandos dentro do REPL:
    /stats    — mostra estatísticas das coleções ChromaDB
    /bundle   — mostra o último ContextBundle montado
    /triage   — mostra o último resultado da triagem
    /quit     — sai
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.agents.agent1_triage import TriageAgent  # noqa: E402
from src.agents.agent2_synthesis import SynthesisAgent  # noqa: E402
from src.agents.synthesis.schemas import NoEvidence, SynthesisResult  # noqa: E402
from src.agents.triage.rules import TriageRuleEngine  # noqa: E402
from src.agents.triage.schemas import ClarificationNeeded, TriageResult  # noqa: E402
from src.agents.triage.temporal import TemporalExtractor  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.memory.context_bundle import ContextBundle  # noqa: E402
from src.rag.embedder import get_embedding_function  # noqa: E402
from src.rag.retriever import SemanticRetriever  # noqa: E402


# ------------------------------------------------------------------ setup


def _build_triage_agent(settings) -> TriageAgent:
    """Triagem com regras + dateparser + LLM Ollama."""
    llm = None
    temporal_llm = None
    try:
        from src.agents.triage.llm_classifier import build_default_llms
        llm, temporal_llm = build_default_llms(settings)
    except Exception as e:
        print(f"  ⚠ Triagem LLM indisponível ({e}); usando só regras.")

    return TriageAgent(
        rule_engine=TriageRuleEngine(),
        temporal_extractor=TemporalExtractor(llm=temporal_llm),
        llm=llm,
    )


def _build_synthesis_agent(settings) -> SynthesisAgent:
    """Síntese com Ollama (mistral)."""
    from src.agents.synthesis.llm_classifier import build_default_synthesis_llm
    llm = build_default_synthesis_llm(settings)
    return SynthesisAgent(llm=llm)


def _build_retriever(settings) -> SemanticRetriever:
    return SemanticRetriever(
        db_path=settings.vectorstore_path,
        embedding_function=get_embedding_function(settings.embedding_model),
    )


# ------------------------------------------------------------ retrieval


def _retrieve_for_triage(
    retriever: SemanticRetriever,
    query: str,
    triage: TriageResult,
    top_k: int = 5,
) -> ContextBundle:
    """Busca RAG guiada pela triagem e monta um ContextBundle."""
    chunks = []
    collections = triage.target_rag_collections or []
    for col in collections:
        try:
            found = retriever.retrieve(query, collection=col, top_k=top_k)
            chunks.extend(found)
        except Exception as e:
            print(f"  ⚠ coleção '{col}' falhou: {e}")

    # Se cross_domain sem coleções explícitas, busca em tudo.
    if not collections and triage.intent == "cross_domain":
        for col in ["diario", "cursos", "referencias"]:
            try:
                found = retriever.retrieve(query, collection=col, top_k=top_k)
                chunks.extend(found)
            except Exception:
                pass

    # Ordena por relevância e corta top 10.
    chunks.sort(key=lambda c: c.relevance_score or 0, reverse=True)
    chunks = chunks[:10]

    return ContextBundle(
        rag_chunks=chunks,
        metadata={
            "intent": triage.intent,
            "temporal_filter": (
                triage.temporal_filter.expression
                if triage.temporal_filter
                else None
            ),
        },
    )


# ---------------------------------------------------------------- render


def _render_triage(out) -> None:
    """Imprime resultado da triagem compactado."""
    if isinstance(out, TriageResult):
        temporal = ""
        if out.temporal_filter:
            tf = out.temporal_filter
            temporal = f" | temporal: {tf.start.date()}..{tf.end.date()}"
        print(
            f"  🔀 triagem: {out.intent} (conf={out.confidence:.2f}, "
            f"método={out.classification_method})"
            f"{temporal}"
        )
        if out.target_rag_collections:
            print(f"     coleções: {out.target_rag_collections}")
    elif isinstance(out, ClarificationNeeded):
        print(f"  ❓ {out.question}")
        if out.detected_options:
            for opt in out.detected_options:
                print(f"     • {opt}")


def _render_synthesis(out) -> None:
    """Imprime resposta da síntese."""
    if isinstance(out, SynthesisResult):
        print(f"\n  💬 {out.answer}")
        if out.citations:
            print()
            for c in out.citations:
                print(
                    f"     📎 [{c.chunk_id}] {c.source_file} "
                    f"({c.collection}, score={c.relevance_score:.2f})"
                )
        print(f"\n  (confidence={out.confidence:.2f})")
    elif isinstance(out, NoEvidence):
        print(f"\n  🤷 {out.suggestion}")
        print(f"     motivo: {out.reason}")


def _render_bundle_summary(bundle: ContextBundle) -> None:
    """Imprime resumo do bundle."""
    print(f"  📦 Bundle: {len(bundle.rag_chunks)} chunks RAG, "
          f"{len(bundle.semantic_facts)} facts, "
          f"{len(bundle.recent_episodic)} episodic, "
          f"{len(bundle.working)} working")
    for chunk in bundle.rag_chunks[:5]:
        score = chunk.relevance_score or 0
        src = (chunk.metadata or {}).get("source_file", "?")
        print(f"     [{chunk.id}] score={score:.2f} | {src}")
    if len(bundle.rag_chunks) > 5:
        print(f"     ... +{len(bundle.rag_chunks) - 5} mais")


# ------------------------------------------------------------------- main


async def main():
    settings = get_settings()

    print("╔══════════════════════════════════════════════════╗")
    print("║     Second Brain — Chat Demo                    ║")
    print("║     Triagem (SPEC-005) → RAG → Síntese (006)   ║")
    print("╚══════════════════════════════════════════════════╝")
    print(f"  Triagem LLM: {settings.ollama_triage_model}")
    print(f"  Síntese LLM: {settings.ollama_synthesis_model}")
    print(f"  Vector store: {settings.vectorstore_path}")

    triage_agent = _build_triage_agent(settings)
    synthesis_agent = _build_synthesis_agent(settings)
    retriever = _build_retriever(settings)

    # Mostra stats do ChromaDB.
    print()
    for col in ["diario", "cursos", "referencias"]:
        try:
            stats = retriever.get_statistics(col)
            print(f"  📊 {col}: {stats.get('document_count', 0)} chunks indexados")
        except Exception:
            print(f"  📊 {col}: (coleção não encontrada)")
    print()
    print("  Comandos: /stats /bundle /triage /quit")
    print("  Ctrl+C para sair.\n")

    last_triage: Optional[TriageResult] = None
    last_bundle: Optional[ContextBundle] = None

    while True:
        try:
            query = input("você > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\ntchau.")
            break

        if not query:
            continue

        # ----- slash commands -----
        if query == "/quit" or query == "/sair":
            break
        if query == "/stats":
            for col in ["diario", "cursos", "referencias"]:
                try:
                    stats = retriever.get_statistics(col)
                    print(f"  {col}: {stats}")
                except Exception as e:
                    print(f"  {col}: erro ({e})")
            print()
            continue
        if query == "/bundle":
            if last_bundle:
                _render_bundle_summary(last_bundle)
            else:
                print("  (nenhum bundle ainda)")
            print()
            continue
        if query == "/triage":
            if last_triage:
                _render_triage(last_triage)
            else:
                print("  (nenhuma triagem ainda)")
            print()
            continue

        # ===== PIPELINE: triagem → retrieval → síntese =====

        try:
            # 1. Triagem
            triage_out = await triage_agent.triage(query)

            # Se pede clarificação, mostra e espera próxima query.
            if isinstance(triage_out, ClarificationNeeded):
                _render_triage(triage_out)
                print()
                continue

            last_triage = triage_out
            _render_triage(triage_out)

            # 2. Retrieval → Bundle
            bundle = _retrieve_for_triage(retriever, query, triage_out)
            last_bundle = bundle
            _render_bundle_summary(bundle)

            # 3. Síntese
            print("  ⏳ sintetizando...")
            synthesis_out = await synthesis_agent.synthesize(query, bundle)
            _render_synthesis(synthesis_out)

        except Exception as e:
            print(f"\n  ❌ erro no pipeline: {e}\n")

        print()


if __name__ == "__main__":
    asyncio.run(main())
