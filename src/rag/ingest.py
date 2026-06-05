"""Pipeline de ingestão end-to-end (SPEC-004 §2).

Discovery -> pré-processamento (-> .md+frontmatter) -> hash/change-detection ->
sanitização de PII por política -> chunking adaptativo -> persistência ChromaDB.

Observabilidade: por ora o pipeline produz um relatório estruturado por arquivo
(FileReport). A emissão de spans OTel (SPEC-004 §7.2) fica como follow-up para
quando o stack opentelemetry estiver instalado no ambiente.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..memory.guardrails import PIIGuardrails
from .chunking import Chunk, chunk_document
from .preprocessing import (
    SUPPORTED_SUFFIXES,
    Domain,
    build_frontmatter,
    load_document,
    profile_document,
    serialize_markdown,
)
from .preprocessing.domains import PIIPolicy
from .store import VectorStore

# Subconjunto de padrões usados na política "mascarar só contatos" (stakeholders).
_CONTACT_PATTERNS = {
    "email": PIIGuardrails.PATTERNS["email"],
    "phone": PIIGuardrails.PATTERNS["phone"],
}

DOMAIN_TO_COLLECTION = {
    "diario": "diario",
    "cursos": "cursos",
    "referencias": "referencias",
}


@dataclass
class FileReport:
    source_file: str
    domain: str
    doc_type: str
    category: Optional[str]
    status: str  # indexed | skipped | reindexed | error
    chunks_created: int = 0
    pii_types_found: List[str] = field(default_factory=list)
    content_hash: str = ""
    error: str = ""


@dataclass
class IngestionReport:
    files: List[FileReport] = field(default_factory=list)

    @property
    def total_chunks(self) -> int:
        return sum(f.chunks_created for f in self.files)

    def by_status(self, status: str) -> List[FileReport]:
        return [f for f in self.files if f.status == status]


def _mask_contacts(text: str) -> tuple[str, List[str]]:
    found: List[str] = []
    out = text
    for pii_type, pattern in _CONTACT_PATTERNS.items():
        if re.search(pattern, out, flags=re.IGNORECASE):
            found.append(pii_type)
        out = re.sub(
            pattern, f"[REDACTED_{pii_type.upper()}]", out, flags=re.IGNORECASE
        )
    return out, found


def _apply_pii(text: str, policy: PIIPolicy) -> tuple[str, List[str]]:
    """Aplica a política de PII e retorna (texto_sanitizado, tipos_encontrados)."""
    if not text:
        return text, []
    if policy == "mask_contacts_only":
        return _mask_contacts(text)
    # aggressive
    found = list(PIIGuardrails.extract_pii(text).keys())
    return PIIGuardrails.sanitize(text), found


class IngestionPipeline:
    def __init__(
        self,
        store: VectorStore,
        processed_root: str = "./data/processed",
        write_processed: bool = True,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ):
        self.store = store
        self.processed_root = Path(processed_root)
        self.write_processed = write_processed
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    # --- discovery ---------------------------------------------------------

    @staticmethod
    def discover(domain_root: Path) -> List[Path]:
        return sorted(
            p
            for p in domain_root.rglob("*")
            if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
        )

    # --- ingestão de um domínio -------------------------------------------

    def ingest_domain(
        self, domain: Domain, domain_root: Path, force: bool = False
    ) -> IngestionReport:
        report = IngestionReport()
        collection = DOMAIN_TO_COLLECTION[domain]

        for path in self.discover(domain_root):
            try:
                report.files.append(
                    self._ingest_file(domain, collection, path, force)
                )
            except Exception as exc:  # robustez: um arquivo ruim não para o lote
                report.files.append(
                    FileReport(
                        source_file=path.name,
                        domain=domain,
                        doc_type="?",
                        category=None,
                        status="error",
                        error=str(exc),
                    )
                )
        return report

    def _ingest_file(
        self, domain: Domain, collection: str, path: Path, force: bool
    ) -> FileReport:
        raw = load_document(path)
        profile = profile_document(path, domain)
        body = raw.body_markdown

        frontmatter = build_frontmatter(profile, path.name, body)
        content_hash = frontmatter["content_hash"]

        # Artefato canônico .md (faithful; PII removido só na indexação).
        if self.write_processed:
            self._write_processed(domain, path, frontmatter, body)

        # Change detection por hash (SPEC-004 §6).
        existing_hash = self.store.get_existing_hash(collection, path.name)
        if existing_hash == content_hash and not force:
            return FileReport(
                source_file=path.name,
                domain=domain,
                doc_type=profile.doc_type,
                category=profile.category,
                status="skipped",
                content_hash=content_hash,
            )

        reindexing = existing_hash is not None

        # Sanitização de PII conforme política do domínio (SPEC-004 §7).
        sanitized_body, pii_body = _apply_pii(body, profile.pii_policy)
        pii_found = set(pii_body)
        if raw.rows is not None:
            sanitized_rows = []
            for row in raw.rows:
                new_row = {}
                for col, value in row.items():
                    if isinstance(value, str):
                        new_val, pii = _apply_pii(value, profile.pii_policy)
                        new_row[col] = new_val
                        pii_found.update(pii)
                    else:
                        new_row[col] = value
                sanitized_rows.append(new_row)
            raw.rows = sanitized_rows

        # Metadata base (frontmatter achatado p/ ChromaDB — sem listas/None).
        base_metadata = _flatten_metadata(frontmatter)

        chunks: List[Chunk] = chunk_document(
            raw=raw,
            profile=profile,
            body=sanitized_body,
            base_metadata=base_metadata,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )

        if reindexing:
            self.store.delete_by_source(collection, path.name)

        ids = [f"{path.stem}__chunk_{i}" for i in range(len(chunks))]
        self.store.add_chunks(
            collection=collection,
            ids=ids,
            documents=[c.content for c in chunks],
            metadatas=[c.metadata for c in chunks],
        )

        return FileReport(
            source_file=path.name,
            domain=domain,
            doc_type=profile.doc_type,
            category=profile.category,
            status="reindexed" if reindexing else "indexed",
            chunks_created=len(chunks),
            pii_types_found=sorted(pii_found),
            content_hash=content_hash,
        )

    def _write_processed(
        self, domain: str, path: Path, frontmatter: Dict[str, Any], body: str
    ) -> None:
        out_dir = self.processed_root / domain
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{path.stem}.md"
        out_path.write_text(
            serialize_markdown(frontmatter, body), encoding="utf-8"
        )


def _flatten_metadata(frontmatter: Dict[str, Any]) -> Dict[str, Any]:
    """ChromaDB só aceita str/int/float/bool em metadata: achata listas, dropa None."""
    flat: Dict[str, Any] = {}
    for key, value in frontmatter.items():
        if value is None:
            continue
        if isinstance(value, list):
            flat[key] = ", ".join(str(v) for v in value)
        elif isinstance(value, (str, int, float, bool)):
            flat[key] = value
        else:
            flat[key] = str(value)
    return flat
