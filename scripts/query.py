"""CLI de consulta para inspeção do RAG (SPEC-004 §10.5 / Cenário A de teste).

Uso:
    python -m scripts.query "atividades de junho" --collection diario
    python -m scripts.query "quem é stakeholder" --collection referencias --top-k 3
    python -m scripts.query "RAG" --collection referencias --filter category=glossario
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import settings  # noqa: E402
from src.rag.embedder import get_embedding_function  # noqa: E402
from src.rag.retriever import SemanticRetriever  # noqa: E402


def _parse_filters(raw: list[str]) -> dict:
    filters = {}
    for item in raw or []:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        filters[key.strip()] = value.strip()
    return filters


def main() -> int:
    parser = argparse.ArgumentParser(description="Consulta semântica ao RAG")
    parser.add_argument("query", help="Texto da consulta")
    parser.add_argument(
        "--collection",
        choices=["diario", "cursos", "referencias"],
        default="diario",
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--filter",
        action="append",
        default=[],
        help="Filtro de metadata, ex.: --filter category=stakeholders",
    )
    args = parser.parse_args()

    embedding_fn = get_embedding_function(settings.embedding_model)
    retriever = SemanticRetriever(
        db_path=settings.vectorstore_path, embedding_function=embedding_fn
    )

    filters = _parse_filters(args.filter) or None
    results = retriever.retrieve(
        query=args.query,
        collection=args.collection,
        top_k=args.top_k,
        filters=filters,
    )

    print(f'Query: "{args.query}"  | coleção: {args.collection}', end="")
    print(f"  | filtros: {filters}" if filters else "")
    print(f"{len(results)} resultado(s):\n")

    for i, chunk in enumerate(results, 1):
        score = (
            f"{chunk.relevance_score:.3f}"
            if chunk.relevance_score is not None
            else "n/a"
        )
        src = chunk.metadata.get("source_file", "?")
        print(f"[{i}] score={score}  fonte={src}")
        snippet = chunk.content.replace("\n", " ")
        print(f"    {snippet[:200]}{'...' if len(snippet) > 200 else ''}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
