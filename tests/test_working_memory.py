"""Testes do tier 1 — WorkingMemory (SPEC-008 §14.1).

Padrão: sync (sem pytest-asyncio). Cobertura dos 7 casos da spec.
"""

from __future__ import annotations

import time

import pytest

from src.memory.working import WorkingItem, WorkingMemory


def test_add_below_capacity_keeps_all():
    wm = WorkingMemory(capacity=3)
    wm.add("a", importance=0.5, source="user")
    wm.add("b", importance=0.5, source="user")
    assert len(wm) == 2
    assert {it.content for it in wm.get_top_k()} == {"a", "b"}


def test_add_above_capacity_evicts_lowest_importance_oldest():
    wm = WorkingMemory(capacity=2)
    wm.add("velho_baixo", importance=0.2, source="user")
    time.sleep(0.001)
    wm.add("velho_alto", importance=0.9, source="user")
    time.sleep(0.001)
    wm.add("novo_baixo", importance=0.2, source="user")

    contents = {it.content for it in wm.get_top_k()}
    assert "velho_baixo" not in contents, "esperado evict do menos importante e mais antigo"
    assert "velho_alto" in contents
    assert "novo_baixo" in contents
    assert len(wm) == 2


def test_get_top_k_orders_by_importance_then_timestamp():
    wm = WorkingMemory(capacity=10)
    wm.add("baixo_antigo", importance=0.3, source="user")
    time.sleep(0.001)
    wm.add("alto_antigo", importance=0.9, source="user")
    time.sleep(0.001)
    wm.add("medio_novo", importance=0.5, source="user")
    time.sleep(0.001)
    wm.add("alto_novo", importance=0.9, source="user")

    top = wm.get_top_k(3)
    assert [it.content for it in top] == ["alto_novo", "alto_antigo", "medio_novo"]


def test_to_context_block_serialization_format():
    wm = WorkingMemory(capacity=5)
    wm.add("oi", importance=0.7, source="user")
    block = wm.to_context_block()
    assert "oi" in block
    assert "user" in block
    assert "imp=0.70" in block


def test_to_context_block_empty_state():
    wm = WorkingMemory(capacity=5)
    assert "vazia" in wm.to_context_block()


def test_clear_empties_state():
    wm = WorkingMemory(capacity=3)
    wm.add("x", importance=0.5, source="user")
    wm.add("y", importance=0.5, source="user")
    wm.clear()
    assert len(wm) == 0
    assert wm.get_top_k() == []


def test_capacity_configurable_via_settings():
    wm = WorkingMemory(capacity=15)
    assert wm.capacity == 15
    for i in range(20):
        wm.add(f"item_{i}", importance=0.5, source="user")
    assert len(wm) == 15


def test_pii_flag_preserved_round_trip():
    wm = WorkingMemory(capacity=5)
    wm.add("contém algo", importance=0.8, source="user", contains_pii=True)
    item = wm.get_top_k(1)[0]
    assert item.contains_pii is True
    assert "[PII]" in wm.to_context_block()


def test_invalid_capacity_raises():
    with pytest.raises(ValueError):
        WorkingMemory(capacity=0)


def test_working_item_is_dataclass_compatible():
    """Sanity: WorkingItem ainda é o mesmo dataclass usado por ContextBundle."""
    wm = WorkingMemory(capacity=2)
    wm.add("x", importance=0.5, source="agent")
    item = wm.get_top_k(1)[0]
    assert isinstance(item, WorkingItem)
    assert item.source == "agent"
