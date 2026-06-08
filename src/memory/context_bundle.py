"""ContextBundle — payload imutável entregue ao Agente 2 (SPEC-MEM §5.3).

Coordena as quatro fontes de contexto montadas pelo orquestrador (SPEC-008):
    - working: itens da Working Memory (tier 1)
    - recent_episodic: conversas recentes (Episodic, tier 2)
    - semantic_facts: fatos sobre o usuário (Semantic, tier 3)
    - rag_chunks: trechos de documentos indexados (RAG)
    - metadata: intent, janela temporal, contagem de tokens, ids de sessão/turn

Pré-condições garantidas pelo orquestrador antes de entregar (SPEC-006 §2.1):
    - `rag_chunks` e `semantic_facts` já filtrados por `user_id`.
    - Orçamento de tokens já aplicado; o agente não trunca mais.
    - `metadata["intent"]` ecoa o intent da triagem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ..rag.retriever import RAGChunk
from .episodic import ConversationRecord
from .semantic import Fact
from .working import WorkingItem


@dataclass
class ContextBundle:
    """Bundle estático consumido pela síntese — stateless do lado do agente."""

    working: List[WorkingItem] = field(default_factory=list)
    recent_episodic: List[ConversationRecord] = field(default_factory=list)
    semantic_facts: List[Fact] = field(default_factory=list)
    rag_chunks: List[RAGChunk] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
