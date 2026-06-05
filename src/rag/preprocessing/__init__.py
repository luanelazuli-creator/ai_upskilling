"""Pré-processamento de dados brutos para Markdown + frontmatter (SPEC-004)."""

from .domains import (
    SUPPORTED_SUFFIXES,
    Domain,
    DocumentProfile,
    profile_document,
)
from .frontmatter import (
    build_frontmatter,
    compute_content_hash,
    serialize_markdown,
)
from .loaders import RawDocument, load_document

__all__ = [
    "SUPPORTED_SUFFIXES",
    "Domain",
    "DocumentProfile",
    "profile_document",
    "build_frontmatter",
    "compute_content_hash",
    "serialize_markdown",
    "RawDocument",
    "load_document",
]
