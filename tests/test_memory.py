"""Unit tests for Persistent Semantic Memory store."""

import pytest
from app.models.memory import MemoryCategory, MemoryItem
from app.services.memory import SqliteMemoryStore


@pytest.fixture
def temp_memory_store(tmp_path):
    db_file = tmp_path / "test_memory.db"
    return SqliteMemoryStore(db_path=str(db_file))


def test_memory_store_and_retrieve(temp_memory_store):
    store = temp_memory_store

    item1 = MemoryItem(
        id="mem-1",
        category=MemoryCategory.REUSABLE_KNOWLEDGE,
        content="LangGraph uses StateGraph to construct stateful cyclic agent workflows.",
        metadata={"author": "LangChain"},
    )
    item2 = MemoryItem(
        id="mem-2",
        category=MemoryCategory.USER_PREFERENCES,
        content="User prefers concise responses with bullet points and code examples.",
        metadata={"preference_type": "formatting"},
    )
    item3 = MemoryItem(
        id="mem-3",
        category=MemoryCategory.TASK_MEMORY,
        content="The previous task calculated 125 * 48 = 6000 for product batch size.",
        metadata={"task": "math"},
    )

    store.store(item1)
    store.store(item2)
    store.store(item3)

    # 1. Semantic query matching item1
    results = store.retrieve("StateGraph agent workflow cycle", limit=2)
    assert len(results) >= 1
    assert results[0].id == "mem-1"
    assert results[0].relevance_score > 0.0

    # 2. Category filtering
    pref_results = store.retrieve("formatting style preferences", category=MemoryCategory.USER_PREFERENCES)
    assert len(pref_results) == 1
    assert pref_results[0].id == "mem-2"

    # 3. Irrelevant query returns empty
    irrelevant = store.retrieve("astrophysics black holes gravitational waves")
    assert len(irrelevant) == 0


def test_memory_delete_and_clear(temp_memory_store):
    store = temp_memory_store

    item = MemoryItem(
        id="del-1",
        category=MemoryCategory.REUSABLE_KNOWLEDGE,
        content="Disposable knowledge item.",
    )
    store.store(item)

    assert store.delete("del-1") is True
    assert store.delete("nonexistent") is False
    assert len(store.retrieve("Disposable")) == 0
