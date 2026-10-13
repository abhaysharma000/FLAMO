"""Live Integration Audit for Gemini Embeddings + ChromaDB Semantic Memory.

Executes a live end-to-end integration audit using the local configured Gemini API key:
- Verifies embedding model support with the Google GenAI API.
- Generates embeddings for 2 related sentences and 1 unrelated sentence.
- Stores items in ChromaDB, destroys the store instance, recreates it from disk,
  and executes a natural-language semantic query.
- Records ranking, scores, model name, backend, and persistence outcomes.
- Verifies that error conditions (missing key, invalid key, invalid model) fail loudly.

NEVER PRINTS, LOGS, OR EXPOSES API KEYS.
"""

import os
import shutil
import tempfile
import uuid
from pathlib import Path
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.models.memory import MemoryCategory, MemoryItem
from app.services.memory import ChromaMemoryStore


def run_live_audit() -> bool:
    print("=" * 80)
    print("FLAMO PHASE 5.1: LIVE GEMINI EMBEDDING & CHROMADB INTEGRATION AUDIT")
    print("=" * 80)

    # 1. Credentials Check
    key = settings.effective_gemini_api_key
    if not key:
        print("[FAIL] CRITICAL: Neither GEMINI_API_KEY nor GOOGLE_API_KEY is found in .env.")
        print("Please configure a valid key in .env to run this live integration audit.")
        return False

    print(f"[*] API Key Present:      YES (redacted, length: {len(key)} chars)")
    print(f"[*] Configured Backend:   {settings.memory_backend}")
    print(f"[*] Embedding Model:      {settings.embedding_model}")

    # 2. Real API Embedding Check
    print("\n--- 1. Testing Live Gemini Embedding API Call ---")
    try:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        embeddings = GoogleGenerativeAIEmbeddings(
            model=settings.embedding_model,
            google_api_key=key,
        )
        sample_text = "Flamo autonomous AI operations agent live verification."
        vec = embeddings.embed_query(sample_text)
        print(f"[*] Real API Call:        SUCCESS")
        print(f"[*] Vector Dimensions:    {len(vec)} (expected: 3072)")
        assert len(vec) == 3072, f"Expected 3072, got {len(vec)}"
    except Exception as e:
        print(f"[FAIL] Real Embedding API call failed: {type(e).__name__}: {e}")
        return False

    # 3. Semantic Lifecycle & Persistence Test
    print("\n--- 2. Testing ChromaDB Lifecycle & Persistence (2 Related, 1 Unrelated) ---")
    tmp_dir = tempfile.mkdtemp(prefix="flamo_audit_chroma_")
    coll_name = f"audit_coll_{uuid.uuid4().hex[:6]}"

    sentence_related_1 = (
        "Flamo is an autonomous AI operations agent built with LangGraph for deterministic execution and stateful recovery."
    )
    sentence_related_2 = (
        "Autonomous agent workflows maintain checkpointed task plans and bounded retry mechanisms to resume after interruption."
    )
    sentence_unrelated = (
        "Photosynthesis in plant chloroplasts converts sunlight, water, and carbon dioxide into glucose and oxygen."
    )

    try:
        # Store in instance 1
        store1 = ChromaMemoryStore(
            persist_directory=tmp_dir,
            collection_name=coll_name,
            embedding_model=settings.embedding_model,
            api_key=key,
        )

        item1 = MemoryItem(
            id="mem-agent-framework",
            category=MemoryCategory.REUSABLE_KNOWLEDGE,
            content=sentence_related_1,
            metadata={"domain": "agent_architecture", "framework": "langgraph"},
            task_id="task-audit-001",
        )
        item2 = MemoryItem(
            id="mem-agent-recovery",
            category=MemoryCategory.TASK_MEMORY,
            content=sentence_related_2,
            metadata={"domain": "agent_architecture", "feature": "recovery"},
            task_id="task-audit-002",
        )
        item3 = MemoryItem(
            id="mem-biology-photosynthesis",
            category=MemoryCategory.REUSABLE_KNOWLEDGE,
            content=sentence_unrelated,
            metadata={"domain": "biology", "process": "photosynthesis"},
            task_id="task-audit-003",
        )

        store1.store(item1)
        store1.store(item2)
        store1.store(item3)
        print(f"[*] Stored 3 memory items in ChromaDB (instance 1)")

        # Destroy instance 1
        del store1

        # Recreate store instance 2 pointing to the same directory
        store2 = ChromaMemoryStore(
            persist_directory=tmp_dir,
            collection_name=coll_name,
            embedding_model=settings.embedding_model,
            api_key=key,
        )
        print(f"[*] Destroyed instance 1 and successfully recreated store instance 2 from persistent disk")

        # Natural language query
        query = "How do autonomous agents resume interrupted workflows and maintain operational execution?"
        print(f"[*] Query String:         '{query}'")

        results = store2.retrieve(query=query, limit=3, min_relevance=0.01)

        print("\n--- 3. Retrieval Ranking & Telemetry Results ---")
        print(f"{'Rank':<5} | {'Memory ID':<28} | {'Score':<8} | {'Category':<18} | {'Task ID':<15} | {'Content Snippet'}")
        print("-" * 110)
        for idx, r in enumerate(results, start=1):
            snippet = (r.content[:45] + "...") if len(r.content) > 45 else r.content
            print(f"{idx:<5} | {r.id:<28} | {r.relevance_score:<8.4f} | {r.category.value:<18} | {str(r.task_id):<15} | {snippet}")
        print("-" * 110)

        scores = {r.id: r.relevance_score for r in results}
        # Validate semantic separation
        assert scores["mem-agent-recovery"] > scores["mem-biology-photosynthesis"], "Related item 2 should score higher than biology"
        assert scores["mem-agent-framework"] > scores["mem-biology-photosynthesis"], "Related item 1 should score higher than biology"

        # Validate persistence of custom metadata
        rec_item2 = next(r for r in results if r.id == "mem-agent-recovery")
        assert rec_item2.metadata.get("domain") == "agent_architecture"
        assert rec_item2.metadata.get("feature") == "recovery"
        assert rec_item2.task_id == "task-audit-002"
        print("[*] Semantic Separation:  CONFIRMED (agent items ranked higher than unrelated biology)")
        print("[*] Persistence Check:    CONFIRMED (custom metadata & task IDs survived store re-creation)")
        print("[*] Note:                 Semantic quality cannot be claimed from a single test example alone.")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # 4. Error Condition Audits
    print("\n--- 4. Error Condition & Fallback Safeguard Verifications ---")

    # A. Missing credentials
    try:
        s_no_key = ChromaMemoryStore(api_key="")
        print("[FAIL] Missing API key did not raise error!")
        return False
    except ValueError as e:
        print(f"[*] Missing Credentials Check: PASSED -> ValueError raised: {e}")

    # B. Invalid credentials
    try:
        s_bad_key = ChromaMemoryStore(api_key="AIzaSy_FAKE_INVALID_API_KEY_999")
        s_bad_key.retrieve("test query")
        print("[FAIL] Invalid API key did not raise error!")
        return False
    except Exception as e:
        print(f"[*] Invalid API Key Check:     PASSED -> {type(e).__name__} raised (no silent fallback)")

    # C. Invalid model name
    try:
        s_bad_model = ChromaMemoryStore(
            embedding_model="models/nonexistent-model-xyz",
            api_key=key,
        )
        s_bad_model.retrieve("test query")
        print("[FAIL] Invalid model name did not raise error!")
        return False
    except Exception as e:
        print(f"[*] Invalid Model Check:       PASSED -> {type(e).__name__} raised (no silent fallback)")

    print("\n" + "=" * 80)
    print("LIVE AUDIT RESULT: ALL CHECKS PASSED")
    print("=" * 80)
    return True


if __name__ == "__main__":
    success = run_live_audit()
    sys.exit(0 if success else 1)
