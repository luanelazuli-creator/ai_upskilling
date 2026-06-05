"""Memória Episódica — histórico de conversas (SPEC-003-2 / SPEC-MEM §4.2).

Storage híbrido:
    - ChromaDB (coleção `episodic_conversations`): texto e embeddings — busca
      semântica sobre o conteúdo da conversa.
    - SQLite: metadata estruturada para filtros indexáveis (user_id, session_id,
      timestamp, intent, pii_sanitized).

Atomicidade (SPEC-003-2 §6): toda escrita resulta em UM registro em cada store
com o MESMO id. Estratégia best-effort de compensação:
    1) escreve no ChromaDB (mais provável de falhar — dependência externa);
    2) escreve no SQLite;
    3) se SQLite falhar, remove do ChromaDB (rollback).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from ..rag.store import VectorStore

_Base = declarative_base()


class _ConversationMetadata(_Base):
    """Metadata indexável de uma conversa.

    O texto da conversa NÃO vive aqui — fica em ChromaDB para busca semântica.
    O campo `meta_json` carrega anexos opcionais (ex.: tokens_used).
    """

    __tablename__ = "conversations"

    id = Column(String, primary_key=True)
    user_id = Column(String, index=True, nullable=False)
    session_id = Column(String, index=True, nullable=False)
    timestamp = Column(DateTime, index=True, nullable=False)
    intent = Column(String, nullable=True)
    pii_sanitized = Column(Boolean, nullable=False)
    meta_json = Column(Text, nullable=True)  # JSON serializado opcional


@dataclass
class ConversationRecord:
    """Visão unificada (Chroma + SQLite) de uma conversa."""

    id: str
    user_id: str
    session_id: str
    timestamp: datetime
    intent: Optional[str]
    pii_sanitized: bool
    user_message: str
    agent_response: str
    metadata: Dict[str, Any] = field(default_factory=dict)


def _build_conversation_document(user_message: str, agent_response: str) -> str:
    """Texto único embebido para busca semântica (SPEC-003-2 §3.2)."""
    return f"user: {user_message} | agent: {agent_response}"


def _split_conversation_document(document: str) -> Tuple[str, str]:
    """Inverso de `_build_conversation_document`. Tolerante a `|` no conteúdo."""
    if document.startswith("user: ") and " | agent: " in document:
        user_part, agent_part = document.split(" | agent: ", 1)
        return user_part[len("user: "):], agent_part
    return document, ""


class EpisodicMemory:
    """Histórico de conversas com busca semântica + filtros estruturados."""

    def __init__(
        self,
        vector_store: VectorStore,
        sqlite_path: str = "./data/episodic_metadata.db",
        collection_name: str = "episodic_conversations",
    ):
        self._store = vector_store
        self._collection_name = collection_name

        Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(f"sqlite:///{sqlite_path}", future=True)
        _Base.metadata.create_all(self._engine)
        self._Session = sessionmaker(bind=self._engine, future=True)

        self._store.get_or_create_collection(collection_name)

    # ------------------------------------------------------------------ write

    def add_conversation(
        self,
        *,
        user_id: str,
        session_id: str,
        user_message: str,
        agent_response: str,
        pii_sanitized: bool,
        intent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Registra uma conversa atomicamente em ChromaDB + SQLite.

        Args:
            pii_sanitized: flag obrigatória (SPEC-003-2 §9). Deve ser bool;
                None ou outros tipos levantam ValueError.
        """
        if not user_id:
            raise ValueError("user_id é obrigatório")
        if not session_id:
            raise ValueError("session_id é obrigatório")
        if not isinstance(pii_sanitized, bool):
            raise ValueError(
                "pii_sanitized é obrigatório e deve ser True ou False"
            )

        conversation_id = f"conv_{uuid.uuid4().hex}"
        timestamp = datetime.now(timezone.utc)
        document = _build_conversation_document(user_message, agent_response)
        # Apenas user_id/session_id ficam em Chroma para filtros indexáveis;
        # timestamp/intent vivem no SQLite (filtros temporais via SQLite — §3.2).
        chroma_metadata = {
            "user_id": user_id,
            "session_id": session_id,
            "timestamp": timestamp.isoformat(),  # mantido p/ inspeção/debug
            "pii_sanitized": pii_sanitized,
        }
        if intent is not None:
            chroma_metadata["intent"] = intent

        # 1) ChromaDB primeiro.
        self._store.add_chunks(
            collection=self._collection_name,
            ids=[conversation_id],
            documents=[document],
            metadatas=[chroma_metadata],
        )

        # 2) SQLite; se falhar, rollback Chroma (§6).
        try:
            with self._Session() as session:
                session.add(
                    _ConversationMetadata(
                        id=conversation_id,
                        user_id=user_id,
                        session_id=session_id,
                        timestamp=timestamp,
                        intent=intent,
                        pii_sanitized=pii_sanitized,
                        meta_json=json.dumps(metadata or {}, ensure_ascii=False),
                    )
                )
                session.commit()
        except Exception:
            self._delete_chroma([conversation_id])
            raise

        return conversation_id

    # ------------------------------------------------------------------- read

    def search_semantic(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        time_window: Optional[Tuple[datetime, datetime]] = None,
    ) -> List[ConversationRecord]:
        """Busca semântica restrita ao usuário, opcionalmente em janela temporal.

        Per SPEC-003-2 §3.2, o filtro temporal vive no SQLite (não no Chroma):
        identificamos os IDs candidatos por usuário+janela no SQLite e
        intersectamos com a busca semântica feita no Chroma (restrita ao
        mesmo usuário).
        """
        allowed_ids: Optional[set[str]] = None
        if time_window is not None:
            start, end = time_window
            with self._Session() as session:
                rows = (
                    session.query(_ConversationMetadata)
                    .filter(_ConversationMetadata.user_id == user_id)
                    .filter(_ConversationMetadata.timestamp >= start)
                    .filter(_ConversationMetadata.timestamp <= end)
                    .all()
                )
            allowed_ids = {row.id for row in rows}
            if not allowed_ids:
                return []

        # Over-fetch para sobreviver à intersecção com a janela temporal.
        fetch_k = top_k * 3 if allowed_ids is not None else top_k
        chroma_hits = self._store.search(
            collection=self._collection_name,
            query=query,
            top_k=fetch_k,
            where={"user_id": user_id},
        )
        if allowed_ids is not None:
            chroma_hits = [h for h in chroma_hits if h["id"] in allowed_ids]
        chroma_hits = chroma_hits[:top_k]

        ids = [hit["id"] for hit in chroma_hits]
        metadata_by_id = self._fetch_sqlite_metadata(ids)
        return [
            self._merge(hit, metadata_by_id.get(hit["id"]))
            for hit in chroma_hits
            if hit["id"] in metadata_by_id
        ]

    def get_recent(self, user_id: str, n: int = 5) -> List[ConversationRecord]:
        """Conversas mais recentes do usuário, ordenadas por timestamp desc."""
        with self._Session() as session:
            rows = (
                session.query(_ConversationMetadata)
                .filter(_ConversationMetadata.user_id == user_id)
                .order_by(_ConversationMetadata.timestamp.desc())
                .limit(n)
                .all()
            )
        return self._hydrate_with_chroma([row.id for row in rows], rows)

    def get_conversations_between(
        self, user_id: str, start: datetime, end: datetime
    ) -> List[ConversationRecord]:
        """Conversas do usuário em um intervalo de tempo (inclusive)."""
        with self._Session() as session:
            rows = (
                session.query(_ConversationMetadata)
                .filter(_ConversationMetadata.user_id == user_id)
                .filter(_ConversationMetadata.timestamp >= start)
                .filter(_ConversationMetadata.timestamp <= end)
                .order_by(_ConversationMetadata.timestamp.asc())
                .all()
            )
        return self._hydrate_with_chroma([row.id for row in rows], rows)

    def cleanup(self, retention_days: int = 90) -> int:
        """Remove conversas mais antigas que `retention_days` em ambos os stores."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        with self._Session() as session:
            old = (
                session.query(_ConversationMetadata)
                .filter(_ConversationMetadata.timestamp < cutoff)
                .all()
            )
            ids_to_delete = [row.id for row in old]
            for row in old:
                session.delete(row)
            session.commit()
        if ids_to_delete:
            self._delete_chroma(ids_to_delete)
        return len(ids_to_delete)

    def get_user_statistics(self, user_id: str) -> Dict[str, Any]:
        with self._Session() as session:
            rows = (
                session.query(_ConversationMetadata)
                .filter(_ConversationMetadata.user_id == user_id)
                .all()
            )
        if not rows:
            return {
                "user_id": user_id,
                "total_conversations": 0,
                "sanitized_ratio": 0.0,
            }
        sanitized = sum(1 for r in rows if r.pii_sanitized)
        return {
            "user_id": user_id,
            "total_conversations": len(rows),
            "sanitized_ratio": sanitized / len(rows),
            "first_interaction": min(r.timestamp for r in rows).isoformat(),
            "last_interaction": max(r.timestamp for r in rows).isoformat(),
        }

    # --------------------------------------------------------------- helpers

    def _delete_chroma(self, ids: List[str]) -> None:
        col = self._store.get_or_create_collection(self._collection_name)
        try:
            col.delete(ids=ids)
        except Exception:
            return

    def _fetch_sqlite_metadata(
        self, ids: List[str]
    ) -> Dict[str, _ConversationMetadata]:
        if not ids:
            return {}
        with self._Session() as session:
            rows = (
                session.query(_ConversationMetadata)
                .filter(_ConversationMetadata.id.in_(ids))
                .all()
            )
        return {row.id: row for row in rows}

    def _hydrate_with_chroma(
        self, ids: List[str], rows: List[_ConversationMetadata]
    ) -> List[ConversationRecord]:
        """Anexa `user_message`/`agent_response` (vindos do ChromaDB) aos rows SQLite."""
        if not ids:
            return []
        col = self._store.get_or_create_collection(self._collection_name)
        got = col.get(ids=ids, include=["documents"])
        chroma_docs: Dict[str, str] = {}
        for cid, doc in zip(got.get("ids") or [], got.get("documents") or []):
            chroma_docs[cid] = doc
        out: List[ConversationRecord] = []
        for row in rows:
            user_msg, agent_resp = _split_conversation_document(
                chroma_docs.get(row.id, "")
            )
            out.append(
                ConversationRecord(
                    id=row.id,
                    user_id=row.user_id,
                    session_id=row.session_id,
                    timestamp=row.timestamp,
                    intent=row.intent,
                    pii_sanitized=row.pii_sanitized,
                    user_message=user_msg,
                    agent_response=agent_resp,
                    metadata=json.loads(row.meta_json or "{}"),
                )
            )
        return out

    def _merge(
        self,
        chroma_hit: Dict[str, Any],
        sqlite_row: Optional[_ConversationMetadata],
    ) -> ConversationRecord:
        user_msg, agent_resp = _split_conversation_document(chroma_hit["content"])
        if sqlite_row is None:
            # Fallback defensivo se a metadata SQLite sumir (não deve acontecer).
            return ConversationRecord(
                id=chroma_hit["id"],
                user_id=chroma_hit["metadata"].get("user_id", ""),
                session_id=chroma_hit["metadata"].get("session_id", ""),
                timestamp=datetime.fromisoformat(
                    chroma_hit["metadata"].get("timestamp", "1970-01-01T00:00:00+00:00")
                ),
                intent=chroma_hit["metadata"].get("intent"),
                pii_sanitized=bool(chroma_hit["metadata"].get("pii_sanitized", False)),
                user_message=user_msg,
                agent_response=agent_resp,
            )
        return ConversationRecord(
            id=sqlite_row.id,
            user_id=sqlite_row.user_id,
            session_id=sqlite_row.session_id,
            timestamp=sqlite_row.timestamp,
            intent=sqlite_row.intent,
            pii_sanitized=sqlite_row.pii_sanitized,
            user_message=user_msg,
            agent_response=agent_resp,
            metadata=json.loads(sqlite_row.meta_json or "{}"),
        )
