"""CLI de ingestão (SPEC-004).

Uso:
    python -m scripts.ingest --domain all
    python -m scripts.ingest --domain diario --force
    python -m scripts.ingest --domain referencias --no-write-processed
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Garante import de `src` ao rodar como script direto.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import settings  # noqa: E402
from src.rag.embedder import get_embedding_function  # noqa: E402
from src.rag.ingest import DOMAIN_TO_COLLECTION, IngestionPipeline  # noqa: E402
from src.rag.store import VectorStore  # noqa: E402

DOMAINS = ["diario", "cursos", "referencias"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingestão RAG local (SPEC-004)")
    parser.add_argument(
        "--domain",
        choices=[*DOMAINS, "all"],
        default="all",
        help="Domínio a ingerir (default: all)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reindexar mesmo que o hash não tenha mudado",
    )
    parser.add_argument(
        "--no-write-processed",
        action="store_true",
        help="Não escrever os .md processados em data/processed",
    )
    parser.add_argument(
        "--data-root",
        default=settings.data_root,
        help=f"Raiz dos dados brutos (default: {settings.data_root})",
    )
    args = parser.parse_args()

    embedding_fn = get_embedding_function(settings.embedding_model)
    store = VectorStore(
        db_path=settings.vectorstore_path, embedding_function=embedding_fn
    )
    pipeline = IngestionPipeline(
        store=store,
        processed_root=settings.processed_root,
        write_processed=not args.no_write_processed,
        chunk_size=settings.chunk_size_default,
        chunk_overlap=settings.chunk_overlap_default,
    )

    targets = DOMAINS if args.domain == "all" else [args.domain]
    data_root = Path(args.data_root)

    print(f"Embedding backend: {settings.embedding_model}")
    print(f"Vector store:      {settings.vectorstore_path}\n")

    grand_total = 0
    for domain in targets:
        domain_root = data_root / domain
        if not domain_root.exists():
            print(f"[{domain}] diretório não encontrado: {domain_root} — pulando")
            continue

        report = pipeline.ingest_domain(domain, domain_root, force=args.force)
        collection = DOMAIN_TO_COLLECTION[domain]
        print(f"=== {domain}  (coleção: {collection}) ===")
        for f in report.files:
            pii = f"pii={','.join(f.pii_types_found)}" if f.pii_types_found else ""
            extra = f"cat={f.category}" if f.category else ""
            print(
                f"  [{f.status:9}] {f.source_file:40} "
                f"chunks={f.chunks_created:<3} {extra} {pii}"
                + (f"  ERRO: {f.error}" if f.error else "")
            )
        print(f"  -> {report.total_chunks} chunks neste domínio\n")
        grand_total += report.total_chunks

    print(f"TOTAL: {grand_total} chunks indexados.")
    for domain in targets:
        col = DOMAIN_TO_COLLECTION[domain]
        try:
            stats = store.get_collection_stats(col)
            print(f"  coleção {col}: {stats['document_count']} documentos")
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
