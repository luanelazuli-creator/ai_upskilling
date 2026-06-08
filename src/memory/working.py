"""Working Memory — tier 1 da memória do Second Brain (SPEC-MEM §4.1).

Esta spec (SPEC-006) define apenas o `WorkingItem` (estrutura de dado)
para tipar o `ContextBundle.working`. A classe `WorkingMemory` com política
de evicção, capacity etc. é responsabilidade da SPEC-008 (orquestrador).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

WorkingSourceLiteral = Literal["user", "agent", "router", "system"]


@dataclass
class WorkingItem:
    """Item da Working Memory (contrato compartilhado com SPEC-008 §4.1)."""

    content: str
    importance: float
    source: WorkingSourceLiteral
    timestamp: datetime
    contains_pii: bool = False
