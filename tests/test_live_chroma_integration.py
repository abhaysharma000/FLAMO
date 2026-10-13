"""Opt-in live integration tests for Gemini Embeddings + ChromaDB persistent vector memory.

These tests make real calls to the Google Gemini Embedding API using the locally
configured API key. They are strictly opt-in and excluded from default test runs via:
    pytest -m live_api

NEVER PRINT, LOG, OR EXPOSE THE API KEY VALUE IN THESE TESTS.
"""

import os
import shutil
import tempfile
import uuid
from typing import Generator

import pytest
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_google_genai._common import GoogleGenerativeAIError

from app.config import settings
from app.models.memory import MemoryCategory, MemoryItem
from app.services.memory import ChromaMemoryStore, get_memory_store


@pytest.fixture
def require_live_gemini_key() -> str:
    """Ensures Gemini API key is configured before running live API tests."""
    key = settings.effective_gemini_api_key
    if not key:
        pytest.skip(
            "GEMINI_API_KEY or GOOGLE_API_KEY is not configured. "
            "Set a valid key in .env to run opt-in live API tests."
        )
    return key


@pytest.fixture
def live_chroma_tmp_dir() -> Generator[str, None, None]:
    """Isolated temporary directory for live Chroma testing."""
    temp_dir = tempfile.mkdtemp(prefix="flamo_live_chroma_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


# ==============================================================================
# Live Test 1: Real Embedding Model Validation & Dimensions
# ==============================================================================

@pytest.mark.live_api
def test_live_gemini_embedding_model_support(require_live_gemini_key: str):
    """Verify that the configured embedding model is supported and real API call succeeds."""
    api_key = require_live_gemini_key
    model_name = settings.embedding_model

    embeddings = GoogleGenerativeAIEmbeddings(
        model=model_name,
        google_api_key=api_key,
    )

    sample_text = "Flamo autonomous operations agent embedding verification."
    vector = embeddings.embed_query(sample_text)

    assert isinstance(vector, list)
    assert len(vector) == 3072, f"Expected 3072 dimensions for {model_name}, got {len(vector)}"
    assert all(isinstance(val, float) for val in vector)
    assert any(val != 0.0 for val in vector)


# ==============================================================================
# Live Test 2: Semantic Separation, Persistence Across Re-creation & Retrieval
# ==============================================================================

@pytest.mark.live_api
def test_live_chroma_semantic_memory_lifecycle(
    require_live_gemini_key: str,
    live_chroma_tmp_dir: str,
):
    """Generate live embeddings for 2 related sentences + 1 unrelated sentence,
    persist to ChromaDB, recreate store, and verify semantic retrieval ranking.
    """
    api_key = require_live_gemini_key
    model_name = settings.embedding_model
    coll_name = f"live_audit_{uuid.uuid4().hex[:6]}"

    # Two semantically related sentences
    sentence_related_1 = (
        "Flamo is an autonomous AI operations agent built with LangGraph for deterministic execution and stateful recovery."
    )
    sentence_related_2 = (
        "Autonomous agent workflows maintain checkpointed task plans and bounded retry mechanisms to resume after interruption."
    )
    # One unrelated sentence
    sentence_unrelated = (
        "Photosynthesis in plant chloroplasts converts sunlight, water, and carbon dioxide into glucose and oxygen."
    )

    # 1. Initialize store instance 1 and store memories
    store1 = ChromaMemoryStore(
        persist_directory=live_chroma_tmp_dir,
        collection_name=coll_name,
        embedding_model=model_name,
        api_key=api_key,
    )

    item1 = MemoryItem(
        id="rel-agent-framework",
        category=MemoryCategory.REUSABLE_KNOWLEDGE,
        content=sentence_related_1,
        metadata={"domain": "ai_agents", "framework": "langgraph"},
        task_id="task-live-101",
    )
    item2 = MemoryItem(
        id="rel-workflow-recovery",
        category=MemoryCategory.TASK_MEMORY,
        content=sentence_related_2,
        metadata={"domain": "ai_agents", "feature": "recovery"},
        task_id="task-live-102",
    )
    item3 = MemoryItem(
        id="unrel-biology",
        category=MemoryCategory.REUSABLE_KNOWLEDGE,
        content=sentence_unrelated,
        metadata={"domain": "botany", "process": "photosynthesis"},
        task_id="task-live-103",
    )

    store1.store(item1)
    store1.store(item2)
    store1.store(item3)

    # 2. Simulate process exit / close instance 1
    del store1

    # 3. Recreate store instance 2 from identical persistent directory
    store2 = ChromaMemoryStore(
        persist_directory=live_chroma_tmp_dir,
        collection_name=coll_name,
        embedding_model=model_name,
        api_key=api_key,
    )

    # 4. Natural language query semantically aligned with agent workflow recovery
    query = "How do autonomous agents resume interrupted workflows and maintain operational execution?"
    results = store2.retrieve(query=query, limit=3, min_relevance=0.01)

    assert len(results) == 3, f"Expected 3 memories retrieved, got {len(results)}"

    retrieved_ids = [r.id for r in results]
    scores = {r.id: r.relevance_score for r in results}

    # Verify that both related items scored higher than the unrelated botany sentence
    assert scores["unrel-biology"] is not None
    assert scores["rel-agent-framework"] is not None
    assert scores["rel-workflow-recovery"] is not None

    # The unrelated biology sentence must have a lower relevance score than the agent-related items
    assert scores["rel-workflow-recovery"] > scores["unrel-biology"]
    assert scores["rel-agent-framework"] > scores["unrel-biology"]

    # Verify persistence: custom metadata and task IDs were preserved across store re-creation
    recreated_item2 = next(r for r in results if r.id == "rel-workflow-recovery")
    assert recreated_item2.task_id == "task-live-102"
    assert recreated_item2.metadata.get("domain") == "ai_agents"
    assert recreated_item2.metadata.get("feature") == "recovery"


# ==============================================================================
# Live Test 3: Clear Errors on Missing Credentials, Invalid Models & Invalid Keys
# ==============================================================================

@pytest.mark.live_api
def test_live_chroma_error_handling(
    require_live_gemini_key: str,
    live_chroma_tmp_dir: str,
):
    """Verify that invalid models, invalid keys, and missing credentials raise clear errors
    without silently switching to fake embeddings or SQLite.
    """
    # 1. Missing credentials explicitly raises ValueError
    with pytest.raises(ValueError, match="CRITICAL CONFIGURATION ERROR"):
        ChromaMemoryStore(
            persist_directory=live_chroma_tmp_dir,
            api_key="",
        )

    # 2. Invalid API key produces GoogleGenerativeAIError on operation
    store_bad_key = ChromaMemoryStore(
        persist_directory=live_chroma_tmp_dir,
        api_key="AIzaSy_INVALID_KEY_FOR_TESTING_123456789",
    )
    with pytest.raises((GoogleGenerativeAIError, Exception)) as exc_info:
        store_bad_key.retrieve("test query")
    assert any(
        term in str(exc_info.value).lower()
        for term in ["api key", "invalid_argument", "unauthorized", "400", "403"]
    )

    # 3. Invalid model name produces 404 NOT_FOUND GoogleGenerativeAIError
    store_bad_model = ChromaMemoryStore(
        persist_directory=live_chroma_tmp_dir,
        embedding_model="models/nonexistent-embedding-model-xyz",
        api_key=require_live_gemini_key,
    )
    with pytest.raises((GoogleGenerativeAIError, Exception)) as exc_info_model:
        store_bad_model.retrieve("test query")
    assert any(
        term in str(exc_info_model.value).lower()
        for term in ["not found", "404", "not supported", "nonexistent"]
    )
