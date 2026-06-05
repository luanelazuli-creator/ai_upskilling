"""Testes da SPEC-003-2 — migração SemanticMemory + EpisodicMemory.

Usa o embedder "fake" (determinístico, sem download) para rodar offline.
Cobre o plano de testes da §8 da spec.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.memory import ConversationRecord, EpisodicMemory, Fact, SemanticMemory
from src.memory.episodic import _ConversationMetadata
from src.rag.embedder import get_embedding_function
from src.rag.store import VectorStore
from src.utils.session import resolve_session_id


# --- fixtures ------------------------------------------------------------


@pytest.fixture
def vector_store(tmp_path: Path) -> VectorStore:
    return VectorStore(
        db_path=str(tmp_path / "vs"),
        embedding_function=get_embedding_function("fake"),
    )


@pytest.fixture
def semantic(vector_store: VectorStore) -> SemanticMemory:
    return SemanticMemory(vector_store=vector_store)


@pytest.fixture
def episodic(vector_store: VectorStore, tmp_path: Path) -> EpisodicMemory:
    return EpisodicMemory(
        vector_store=vector_store,
        sqlite_path=str(tmp_path / "episodic.db"),
    )


# --- SemanticMemory (§8.1) ----------------------------------------------


def test_add_fact_persists_to_chromadb(semantic):
    fact_id = semantic.add_fact(
        user_id="luane",
        content="Luane prefere respostas curtas",
        category="preference",
        confidence=0.95,
    )
    got = semantic.get_fact(fact_id)
    assert got is not None
    assert isinstance(got, Fact)
    assert got.content == "Luane prefere respostas curtas"
    assert got.category == "preference"
    assert got.confidence == pytest.approx(0.95)


def test_search_finds_semantically_similar(semantic):
    # Embedder fake casa por token compartilhado; basta sobreposição lexical.
    semantic.add_fact("luane", "Python é uma linguagem de programação")
    semantic.add_fact("luane", "JavaScript roda no navegador")
    hits = semantic.search("luane", "Python linguagem", top_k=2)
    assert hits, "deveria recuperar pelo menos 1 fato"
    assert "Python" in hits[0].content


def test_search_isolates_by_user_id(semantic):
    semantic.add_fact("alice", "Alice gosta de café")
    semantic.add_fact("bob", "Bob gosta de chá")
    alice_hits = semantic.search("alice", "café chá", top_k=5)
    bob_hits = semantic.search("bob", "café chá", top_k=5)
    assert all(f.user_id == "alice" for f in alice_hits)
    assert all(f.user_id == "bob" for f in bob_hits)
    assert {f.content for f in alice_hits} == {"Alice gosta de café"}
    assert {f.content for f in bob_hits} == {"Bob gosta de chá"}


def test_delete_fact_removes_from_collection(semantic):
    fact_id = semantic.add_fact("luane", "Fato a esquecer", category="preference")
    semantic.delete_fact(fact_id)
    assert semantic.get_fact(fact_id) is None


def test_delete_unknown_fact_is_no_op(semantic):
    # Idempotência (§9): apagar ID inexistente não deve levantar.
    semantic.delete_fact("fact_does_not_exist")


def test_list_by_category_filters_correctly(semantic):
    semantic.add_fact("luane", "Prefere markdown", category="preference")
    semantic.add_fact("luane", "Tem cachorro", category="profile")
    semantic.add_fact("luane", "Gosta de chocolate", category="preference")
    prefs = semantic.list_by_category("luane", "preference")
    assert len(prefs) == 2
    assert all(f.category == "preference" for f in prefs)


def test_statistics_aggregates_per_user(semantic):
    semantic.add_fact("luane", "F1", category="preference", confidence=0.8)
    semantic.add_fact("luane", "F2", category="profile", confidence=1.0)
    semantic.add_fact("outro", "Fx", confidence=0.5)
    stats = semantic.get_statistics("luane")
    assert stats["total_facts"] == 2
    assert stats["avg_confidence"] == pytest.approx(0.9)
    assert stats["categories"] == {"preference": 1, "profile": 1}


def test_add_fact_rejects_empty_content(semantic):
    with pytest.raises(ValueError):
        semantic.add_fact("luane", "")


# --- EpisodicMemory (§8.2) ----------------------------------------------


def _add(episodic: EpisodicMemory, **overrides) -> str:
    payload = {
        "user_id": "luane",
        "session_id": "s1",
        "user_message": "qual o status do curso?",
        "agent_response": "Você está no módulo 4.",
        "pii_sanitized": True,
    }
    payload.update(overrides)
    return episodic.add_conversation(**payload)


def test_add_conversation_writes_both_stores(episodic, vector_store):
    cid = _add(episodic, intent="course_status")
    # SQLite
    with episodic._Session() as session:
        row = session.get(_ConversationMetadata, cid)
    assert row is not None
    assert row.user_id == "luane"
    assert row.session_id == "s1"
    assert row.intent == "course_status"
    assert row.pii_sanitized is True
    # ChromaDB
    col = vector_store.get_or_create_collection("episodic_conversations")
    got = col.get(ids=[cid], include=["documents", "metadatas"])
    assert got["ids"] == [cid]
    assert "qual o status do curso?" in got["documents"][0]
    assert got["metadatas"][0]["user_id"] == "luane"


def test_pii_sanitized_flag_required(episodic):
    # Sem a flag: TypeError (Python, keyword obrigatório).
    with pytest.raises(TypeError):
        episodic.add_conversation(
            user_id="luane",
            session_id="s1",
            user_message="oi",
            agent_response="olá",
        )
    # Com a flag em None: ValueError (validação explícita §9).
    with pytest.raises(ValueError):
        episodic.add_conversation(
            user_id="luane",
            session_id="s1",
            user_message="oi",
            agent_response="olá",
            pii_sanitized=None,  # type: ignore[arg-type]
        )


def test_atomicity_rollback_on_sqlite_failure(episodic, vector_store, monkeypatch):
    """Se SQLite falhar, o chunk gravado no ChromaDB deve ser removido (§6)."""

    class BoomSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def add(self, *_args, **_kwargs):
            raise RuntimeError("simulated sqlite failure")

        def commit(self):  # pragma: no cover - não chega aqui
            raise AssertionError("commit não deveria ser chamado")

    # Conta documentos antes; depois confirma que não cresceu.
    col = vector_store.get_or_create_collection("episodic_conversations")
    before = col.count()
    monkeypatch.setattr(episodic, "_Session", lambda: BoomSession())
    with pytest.raises(RuntimeError, match="simulated sqlite failure"):
        _add(episodic)
    assert col.count() == before, "ChromaDB deveria ter sido rolled-back"


def test_get_recent_returns_chronological(episodic):
    a = _add(episodic, user_message="primeira")
    b = _add(episodic, user_message="segunda")
    c = _add(episodic, user_message="terceira")
    recent = episodic.get_recent("luane", n=3)
    assert [r.id for r in recent] == [c, b, a]


def test_search_semantic_with_time_window(episodic):
    # Cria conversas e mexe nos timestamps do SQLite para simular passado.
    cid_old = _add(episodic, user_message="conversa antiga sobre Python")
    cid_new = _add(episodic, user_message="conversa recente sobre Python")
    old_ts = datetime.now(timezone.utc) - timedelta(days=10)
    with episodic._Session() as session:
        row = session.get(_ConversationMetadata, cid_old)
        row.timestamp = old_ts
        session.commit()
    # Janela: últimos 5 dias só.
    window = (
        datetime.now(timezone.utc) - timedelta(days=5),
        datetime.now(timezone.utc) + timedelta(seconds=1),
    )
    hits = episodic.search_semantic(
        "luane", "Python", top_k=5, time_window=window
    )
    ids = {h.id for h in hits}
    assert cid_new in ids
    assert cid_old not in ids


def test_cleanup_respects_retention_days(episodic, vector_store):
    cid_old = _add(episodic, user_message="velha")
    cid_keep = _add(episodic, user_message="nova")
    with episodic._Session() as session:
        row = session.get(_ConversationMetadata, cid_old)
        row.timestamp = datetime.now(timezone.utc) - timedelta(days=120)
        session.commit()
    deleted = episodic.cleanup(retention_days=90)
    assert deleted == 1
    # ChromaDB também limpou:
    col = vector_store.get_or_create_collection("episodic_conversations")
    remaining = col.get(ids=[cid_old, cid_keep], include=[])
    assert remaining["ids"] == [cid_keep]


def test_isolation_by_user(episodic):
    _add(episodic, user_id="alice", session_id="sa")
    _add(episodic, user_id="bob", session_id="sb")
    assert len(episodic.get_recent("alice")) == 1
    assert len(episodic.get_recent("bob")) == 1


def test_user_statistics(episodic):
    _add(episodic, pii_sanitized=True)
    _add(episodic, pii_sanitized=True)
    _add(episodic, pii_sanitized=False)
    stats = episodic.get_user_statistics("luane")
    assert stats["total_conversations"] == 3
    assert stats["sanitized_ratio"] == pytest.approx(2 / 3)


# --- Resolução de SESSION_ID (§8.3) -------------------------------------


def test_session_id_generated_when_not_set():
    sid = resolve_session_id(None)
    # UUID v4 no formato canônico (36 chars com 4 hifens).
    assert len(sid) == 36 and sid.count("-") == 4

    sid_empty = resolve_session_id("")
    assert len(sid_empty) == 36

    # Cada chamada gera ID novo.
    assert resolve_session_id(None) != resolve_session_id(None)


def test_session_id_from_env_used_as_is():
    sid = resolve_session_id("sessao-fixa-para-teste")
    assert sid == "sessao-fixa-para-teste"
