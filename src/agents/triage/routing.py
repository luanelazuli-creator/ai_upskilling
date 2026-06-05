"""Roteamento intent → coleções RAG + tiers de memória (SPEC-005 §2).

Tabela única consumida tanto pela camada de regras quanto para *backfill* da
saída do LLM. Centralizar aqui garante que regras e LLM roteiem de forma
idêntica para um mesmo intent.
"""

from __future__ import annotations

# intent -> (coleções RAG default, tiers de memória default)
_ROUTING: dict[str, tuple[list[str], list[str]]] = {
    "diary_lookup": (["diario"], []),
    "course_status": (["cursos"], []),
    "reference_lookup": (["referencias"], []),
    "golden_prompt_request": (["cursos"], []),
    "user_profile": ([], ["semantic"]),
    "conversation_recall": ([], ["episodic_recent", "episodic_semantic"]),
    "cross_domain": ([], []),  # preenchido dinamicamente pela resolução de regras
    "meta": ([], []),  # sem busca
}


def route_for_intent(intent: str) -> tuple[list[str], list[str]]:
    """Retorna (coleções RAG, tiers de memória) para um intent.

    Retorna cópias para evitar mutação acidental da tabela.
    """
    collections, tiers = _ROUTING.get(intent, ([], []))
    return list(collections), list(tiers)


def all_rag_collections() -> list[str]:
    """Todas as coleções RAG conhecidas (usado no fallback amplo da SPEC-008)."""
    return ["diario", "cursos", "referencias"]
