"""Serialização do `ContextBundle` para o prompt do LLM (SPEC-006 §6).

Ordem das seções: RAG primeiro (evidência mais autoritativa), Episodic,
Semantic, Working (próximo da query — LLMs retêm melhor o que está perto
do final do prompt). IDs aparecem no INÍCIO de cada chunk para o LLM
aprender a referenciá-los inline.
"""

from __future__ import annotations

from typing import Iterable

from src.memory.context_bundle import ContextBundle
from src.memory.episodic import ConversationRecord
from src.memory.semantic import Fact
from src.memory.working import WorkingItem
from src.rag.retriever import RAGChunk


def fact_citation_id(fact_id: str) -> str:
    """Prefixa o ID de um Fact para distingui-lo de RAGChunks (§4.1)."""
    return f"fact:{fact_id}"


def collect_bundle_ids(bundle: ContextBundle) -> set[str]:
    """IDs citáveis presentes no bundle: rag_chunks + fact:{fact_id}.

    Usado pelo validador para detectar citações a IDs inexistentes.
    Episodic e Working NÃO são citáveis (SPEC-006 §2.2).
    """
    ids: set[str] = set()
    for chunk in bundle.rag_chunks:
        if chunk.id:
            ids.add(chunk.id)
    for fact in bundle.semantic_facts:
        if fact.fact_id:
            ids.add(fact_citation_id(fact.fact_id))
    return ids


# ----------------------------------------------------------------- formatters


def _format_rag_chunk(chunk: RAGChunk) -> str:
    """`[id] (collection=…, source=…, score=…) Conteúdo: …` (§6.2)."""
    source_file = ""
    if chunk.metadata:
        source_file = (
            chunk.metadata.get("source_file")
            or chunk.metadata.get("source")
            or ""
        )
    score = chunk.relevance_score if chunk.relevance_score is not None else 0.0
    header = f"[{chunk.id}] (collection={chunk.collection}, source={source_file}, score={score:.2f})"
    return f"{header}\nConteúdo: {chunk.content}"


def _format_fact(fact: Fact) -> str:
    """`[fact:id] (category=…, score=…) Conteúdo: …` (§6.3)."""
    cid = fact_citation_id(fact.fact_id)
    category = fact.category or "n/a"
    header = f"[{cid}] (category={category}, score={fact.confidence:.2f})"
    return f"{header}\nConteúdo: {fact.content}"


def _format_episodic(record: ConversationRecord) -> str:
    """Conversa anterior — não citável; apenas contextualiza."""
    ts = record.timestamp.isoformat() if record.timestamp else ""
    intent_part = f" intent={record.intent}" if record.intent else ""
    return (
        f"({ts}{intent_part})\n"
        f"usuário: {record.user_message}\n"
        f"agente: {record.agent_response}"
    )


def _format_working(item: WorkingItem) -> str:
    """Item da Working Memory — não citável; contexto da sessão atual."""
    return f"[{item.source}, importance={item.importance:.2f}] {item.content}"


def _block(title: str, body: str | None) -> str:
    if not body:
        body = "(vazio)"
    return f"[{title}]\n{body}"


def _join(items: Iterable[str]) -> str:
    return "\n\n".join(items)


# --------------------------------------------------------------------- public


def render_prompt(query: str, bundle: ContextBundle) -> str:
    """Monta o prompt de usuário a partir do bundle (SPEC-006 §6.1).

    O system prompt vive separado (passado ao `Agent`) — esta função produz
    apenas o conteúdo dependente do bundle e da query do turno.
    """
    rag_body = _join(_format_rag_chunk(c) for c in bundle.rag_chunks)
    episodic_body = _join(_format_episodic(r) for r in bundle.recent_episodic)
    facts_body = _join(_format_fact(f) for f in bundle.semantic_facts)
    working_body = _join(_format_working(w) for w in bundle.working)

    intent = bundle.metadata.get("intent", "unknown") if bundle.metadata else "unknown"

    sections = [
        _block("Documentos relevantes - RAG", rag_body),
        _block("Histórico recente da conversa", episodic_body),
        _block("Fatos sobre o usuário", facts_body),
        _block("Contexto da sessão atual", working_body),
        f"[Intent detectado]: {intent}",
        f"[Pergunta do usuário]: {query}",
    ]
    return "\n\n".join(sections)
