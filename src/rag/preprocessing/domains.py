"""Conhecimento de domínio para a ingestão (SPEC-004 §3 e §4).

Centraliza as regras que dependem do domínio (diário/cursos/referências):
detecção de tipo de documento, categoria, estratégia de chunking e política de PII.
Mantido em um só lugar para que as regras sejam testáveis e ajustáveis sem
mexer no pipeline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal, Optional

Domain = Literal["diario", "cursos", "referencias"]
ChunkStrategy = Literal["whole_file", "standard", "row_per_line"]
PIIPolicy = Literal["aggressive", "mask_contacts_only"]

# Mapa source_file -> category para referências (SPEC-004 §3.3).
# Chave é comparada em lower-case e sem acento de forma tolerante.
_REFERENCE_CATEGORY_MAP = {
    "acessos sistemas": "manuais",
    "atestados": "manuais",
    "glossario": "glossario",
    "links uteis": "procedimentos",
    "pessoas importantes": "stakeholders",
    "thoughtworks contacts": "stakeholders",
}

TABULAR_SUFFIXES = {".xlsx", ".csv"}
DOC_SUFFIXES = {".docx"}
MARKDOWN_SUFFIXES = {".md"}
SUPPORTED_SUFFIXES = TABULAR_SUFFIXES | DOC_SUFFIXES | MARKDOWN_SUFFIXES


@dataclass
class DocumentProfile:
    """Resultado da classificação de um arquivo dentro do seu domínio."""

    domain: Domain
    doc_type: str  # diario | course | golden_prompt | reference
    category: Optional[str]  # só para referências
    chunk_strategy: ChunkStrategy
    pii_policy: PIIPolicy
    diary_date: Optional[date] = None


def _normalize(text: str) -> str:
    """Lower-case sem acentos comuns, para casar nomes de arquivo."""
    table = str.maketrans("áàâãéêíóôõúüç", "aaaaeeiooouuc")
    return text.lower().translate(table).strip()


def _detect_diary_date(path: Path) -> Optional[date]:
    """Extrai a data do diário do nome do arquivo e/ou da estrutura YYYY/MM.

    Suporta nomes como "Dia 11 - Keep Studying.docx" combinados com o caminho
    .../2026/06/ . Retorna None se não conseguir inferir com confiança.
    """
    year = month = day = None

    # Ano e mês a partir do caminho .../YYYY/MM/...
    parts = [p for p in path.parts]
    for i, part in enumerate(parts):
        if re.fullmatch(r"20\d{2}", part):
            year = int(part)
            if i + 1 < len(parts) and re.fullmatch(r"0[1-9]|1[0-2]", parts[i + 1]):
                month = int(parts[i + 1])
            break

    # Dia a partir de "Dia DD"
    m = re.search(r"dia\s*(\d{1,2})", _normalize(path.stem))
    if m:
        day = int(m.group(1))

    # Data completa no nome (DD/MM/YYYY ou YYYY-MM-DD)
    m2 = re.search(r"(20\d{2})[-_](\d{1,2})[-_](\d{1,2})", path.stem)
    if m2:
        year, month, day = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))

    if year and month and day:
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


def _reference_category(path: Path) -> str:
    norm = _normalize(path.stem)
    for key, category in _REFERENCE_CATEGORY_MAP.items():
        if key in norm:
            return category
    # Default conservador: planilha desconhecida -> procedimentos; doc -> manuais
    if path.suffix.lower() in TABULAR_SUFFIXES:
        return "procedimentos"
    return "manuais"


def profile_document(path: Path, domain: Domain) -> DocumentProfile:
    """Classifica um arquivo dentro do seu domínio, decidindo tipo/chunking/PII."""
    suffix = path.suffix.lower()

    if domain == "diario":
        return DocumentProfile(
            domain="diario",
            doc_type="diario",
            category=None,
            chunk_strategy="whole_file",  # 1 dia = 1 chunk (SPEC-004 §4)
            pii_policy="aggressive",
            diary_date=_detect_diary_date(path),
        )

    if domain == "cursos":
        is_golden = "golden prompt" in _normalize(str(path.parent))
        if is_golden:
            return DocumentProfile(
                domain="cursos",
                doc_type="golden_prompt",
                category=None,
                chunk_strategy="whole_file",  # prompt = unidade atômica
                pii_policy="aggressive",
            )
        return DocumentProfile(
            domain="cursos",
            doc_type="course",
            category=None,
            chunk_strategy="row_per_line" if suffix in TABULAR_SUFFIXES else "standard",
            pii_policy="aggressive",
        )

    # referencias
    category = _reference_category(path)
    if suffix in TABULAR_SUFFIXES:
        chunk_strategy: ChunkStrategy = "row_per_line"
    else:
        chunk_strategy = "standard"
    pii_policy: PIIPolicy = (
        "mask_contacts_only" if category == "stakeholders" else "aggressive"
    )
    return DocumentProfile(
        domain="referencias",
        doc_type="reference",
        category=category,
        chunk_strategy=chunk_strategy,
        pii_policy=pii_policy,
    )
