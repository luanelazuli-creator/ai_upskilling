"""Working Memory — tier 1 da memória do Second Brain (SPEC-MEM §4.1 / SPEC-008 §4).

`WorkingItem` é o contrato compartilhado com o `ContextBundle.working`.
`WorkingMemory` é o buffer com política de evicção próprio do tier 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Literal

WorkingSourceLiteral = Literal["user", "agent", "router", "system"]


@dataclass
class WorkingItem:
    """Item da Working Memory (contrato compartilhado com SPEC-008 §4.1)."""

    content: str
    importance: float
    source: WorkingSourceLiteral
    timestamp: datetime
    contains_pii: bool = False


class WorkingMemory:
    """Buffer efêmero do tier 1 (SPEC-008 §4.2).

    Política de evicção (§4.3): quando `len > capacity`, remove iterativamente
    o item com menor `(importance, timestamp)` — menos importante e mais antigo
    primeiro — até caber.
    """

    def __init__(self, capacity: int = 10):
        if capacity < 1:
            raise ValueError("capacity deve ser >= 1")
        self._items: List[WorkingItem] = []
        self._capacity = capacity

    @property
    def capacity(self) -> int:
        return self._capacity

    def add(
        self,
        content: str,
        importance: float,
        source: WorkingSourceLiteral,
        contains_pii: bool = False,
    ) -> None:
        item = WorkingItem(
            content=content,
            importance=float(importance),
            source=source,
            timestamp=datetime.now(timezone.utc),
            contains_pii=contains_pii,
        )
        self._items.append(item)
        self._evict_if_needed()

    def get_top_k(self, k: int = 10) -> List[WorkingItem]:
        """Retorna até `k` itens ordenados por (importance, timestamp) desc."""
        ordered = sorted(
            self._items,
            key=lambda it: (it.importance, it.timestamp),
            reverse=True,
        )
        return ordered[:k]

    def clear(self) -> None:
        self._items.clear()

    def to_context_block(self) -> str:
        """Serialização legível para injeção em prompt (debug/contexto)."""
        if not self._items:
            return "(working memory vazia)"
        lines = []
        for it in self.get_top_k(self._capacity):
            ts = it.timestamp.strftime("%H:%M:%S")
            pii_tag = " [PII]" if it.contains_pii else ""
            lines.append(
                f"[{ts}] ({it.source}, imp={it.importance:.2f}){pii_tag} {it.content}"
            )
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._items)

    def _evict_if_needed(self) -> None:
        while len(self._items) > self._capacity:
            idx_min = min(
                range(len(self._items)),
                key=lambda i: (self._items[i].importance, self._items[i].timestamp),
            )
            self._items.pop(idx_min)
