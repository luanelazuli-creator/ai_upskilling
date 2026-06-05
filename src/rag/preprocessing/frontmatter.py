"""Geração e parse de frontmatter YAML por domínio (SPEC-004 §3).

O hash de conteúdo (SPEC-004 §6) cobre APENAS o corpo, nunca o frontmatter —
assim mudanças em `ingested_at` não invalidam o cache de re-indexação.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Dict

import yaml

from .domains import DocumentProfile


def compute_content_hash(body: str) -> str:
    """SHA-256 do corpo (sem frontmatter). Prefixado para legibilidade."""
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _extract_tags(title: str) -> list[str]:
    """Heurística simples: tokens significativos do título viram tags."""
    stop = {"dia", "de", "do", "da", "the", "a", "o", "e", "-"}
    tokens = re.findall(r"[a-zA-ZÀ-ÿ]+", title.lower())
    return [t for t in tokens if t not in stop and len(t) > 2]


def build_frontmatter(
    profile: DocumentProfile, source_name: str, body: str
) -> Dict[str, Any]:
    """Monta o dict de frontmatter conforme o domínio/tipo do documento.

    Args:
        profile: classificação do documento (domínio, tipo, categoria...).
        source_name: nome do arquivo original (ex.: "Dia 11 - Keep Studying.docx").
        body: corpo já convertido para Markdown (sem frontmatter).
    """
    now = datetime.now(timezone.utc).isoformat()
    stem = source_name.rsplit(".", 1)[0] if "." in source_name else source_name
    content_hash = compute_content_hash(body)

    if profile.domain == "diario":
        return {
            "type": "diario",
            "date": profile.diary_date.isoformat() if profile.diary_date else None,
            "source_file": source_name,
            "tags": _extract_tags(stem),
            "ingested_at": now,
            "content_hash": content_hash,
        }

    if profile.domain == "cursos":
        return {
            "type": profile.doc_type,  # course | golden_prompt
            "course": stem,
            "source_file": source_name,
            "ingested_at": now,
            "content_hash": content_hash,
        }

    # referencias
    return {
        "type": "reference",
        "category": profile.category,
        "source_file": source_name,
        "ingested_at": now,
        "content_hash": content_hash,
    }


def serialize_markdown(frontmatter: Dict[str, Any], body: str) -> str:
    """Gera o arquivo .md final (frontmatter YAML + corpo)."""
    clean = {k: v for k, v in frontmatter.items() if v is not None}
    yaml_block = yaml.safe_dump(clean, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{yaml_block}\n---\n\n{body}\n"
