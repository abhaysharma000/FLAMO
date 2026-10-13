"""Persistent Semantic Memory service with SQLite and PgVector backends."""

import json
import logging
import math
import re
import sqlite3
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.models.memory import MemoryCategory, MemoryItem, MemoryQuery

logger = logging.getLogger("flamo.services.memory")


def _stem(word: str) -> str:
    """Lightweight suffix stemmer for semantic token normalization."""
    w = word.lower()
    for suffix in ("ing", "tion", "tions", "ences", "ence", "es", "s", "ed", "ment"):
        if len(w) > len(suffix) + 3 and w.endswith(suffix):
            return w[:-len(suffix)]
    return w


def _tokenize(text: str) -> List[str]:
    """Tokenize and stem text into normalized word roots."""
    raw_tokens = re.findall(r"\b\w{2,}\b", text.lower())
    return [_stem(t) for t in raw_tokens]


def _compute_cosine_similarity(query_tokens: List[str], doc_tokens: List[str]) -> float:
    """Calculate term-frequency cosine similarity between query and document."""
    if not query_tokens or not doc_tokens:
        return 0.0

    # Build term frequencies
    q_freq: Dict[str, int] = {}
    for t in query_tokens:
        q_freq[t] = q_freq.get(t, 0) + 1

    d_freq: Dict[str, int] = {}
    for t in doc_tokens:
        d_freq[t] = d_freq.get(t, 0) + 1

    common_terms = set(q_freq.keys()).intersection(set(d_freq.keys()))
    if not common_terms:
        return 0.0

    dot_product = sum(q_freq[t] * d_freq[t] for t in common_terms)
    q_norm = math.sqrt(sum(v * v for v in q_freq.values()))
    d_norm = math.sqrt(sum(v * v for v in d_freq.values()))

    if q_norm == 0.0 or d_norm == 0.0:
        return 0.0

    return dot_product / (q_norm * d_norm)


class MemoryStore(ABC):
    """Abstract interface for persistent semantic memory storage."""

    @abstractmethod
    def store(self, item: MemoryItem) -> str:
        """Persist a memory item and return its ID."""
        pass

    @abstractmethod
    def retrieve(
        self,
        query: str,
        category: Optional[MemoryCategory] = None,
        limit: int = 5,
        min_relevance: float = 0.05,
    ) -> List[MemoryItem]:
        """Retrieve the most relevant memories matching a query."""
        pass

    @abstractmethod
    def delete(self, item_id: str) -> bool:
        """Remove a memory item by ID."""
        pass

    @abstractmethod
    def clear(self, category: Optional[MemoryCategory] = None) -> int:
        """Clear memories, optionally filtered by category."""
        pass


class SqliteMemoryStore(MemoryStore):
    """SQLite-backed memory store with stemmed lexical token-frequency ranking."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or settings.sqlite_db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize the memories table schema."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT DEFAULT '{}',
                    timestamp TEXT NOT NULL,
                    task_id TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category)"
            )
            conn.commit()

    def store(self, item: MemoryItem) -> str:
        """Persist a memory item into SQLite."""
        if not item.id:
            item.id = f"mem-{uuid.uuid4().hex[:8]}"

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO memories 
                (id, category, content, metadata_json, timestamp, task_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    item.category.value,
                    item.content,
                    json.dumps(item.metadata),
                    item.timestamp,
                    item.task_id,
                ),
            )
            conn.commit()
        logger.debug("Stored memory %s [%s]", item.id, item.category)
        return item.id

    def retrieve(
        self,
        query: str,
        category: Optional[MemoryCategory] = None,
        limit: int = 5,
        min_relevance: float = 0.05,
    ) -> List[MemoryItem]:
        """Rank memories against query using stemmed lexical token-frequency matching."""
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        with self._get_connection() as conn:
            if category:
                rows = conn.execute(
                    "SELECT id, category, content, metadata_json, timestamp, task_id FROM memories WHERE category = ?",
                    (category.value,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, category, content, metadata_json, timestamp, task_id FROM memories"
                ).fetchall()

        scored_items: List[MemoryItem] = []
        for r in rows:
            content = r["content"]
            doc_tokens = _tokenize(content)
            score = _compute_cosine_similarity(query_tokens, doc_tokens)

            if score >= min_relevance:
                meta = {}
                try:
                    meta = json.loads(r["metadata_json"])
                except Exception:
                    pass

                item = MemoryItem(
                    id=r["id"],
                    category=MemoryCategory(r["category"]),
                    content=content,
                    metadata=meta,
                    timestamp=r["timestamp"],
                    task_id=r["task_id"],
                    relevance_score=round(score, 4),
                    scoring_method="stemmed_token_match",
                )
                scored_items.append(item)

        # Sort descending by relevance score
        scored_items.sort(key=lambda m: m.relevance_score or 0.0, reverse=True)
        return scored_items[:limit]

    def delete(self, item_id: str) -> bool:
        """Delete memory item."""
        with self._get_connection() as conn:
            cur = conn.execute("DELETE FROM memories WHERE id = ?", (item_id,))
            conn.commit()
            return cur.rowcount > 0

    def clear(self, category: Optional[MemoryCategory] = None) -> int:
        """Clear all memories or memories of given category."""
        with self._get_connection() as conn:
            if category:
                cur = conn.execute("DELETE FROM memories WHERE category = ?", (category.value,))
            else:
                cur = conn.execute("DELETE FROM memories")
            conn.commit()
            return cur.rowcount


class PgVectorMemoryStore(MemoryStore):
    """PostgreSQL + PgVector backend placeholder interface for production deployment."""

    def __init__(self, connection_url: Optional[str] = None) -> None:
        self.connection_url = connection_url or settings.database_url
        logger.info("PgVectorMemoryStore initialized with connection: %s", self.connection_url)

    def store(self, item: MemoryItem) -> str:
        logger.info("PgVectorMemoryStore: Storing %s (delegating to PostgreSQL)", item.id)
        return item.id

    def retrieve(
        self,
        query: str,
        category: Optional[MemoryCategory] = None,
        limit: int = 5,
        min_relevance: float = 0.05,
    ) -> List[MemoryItem]:
        logger.info("PgVectorMemoryStore: Querying '%s'", query)
        return []

    def delete(self, item_id: str) -> bool:
        return True

    def clear(self, category: Optional[MemoryCategory] = None) -> int:
        return 0


class ChromaMemoryStore(MemoryStore):
    """ChromaDB persistent vector memory store using Gemini embeddings."""

    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: str = "flamo_memory",
        embedding_model: Optional[str] = None,
        api_key: Optional[str] = None,
        embeddings: Optional[Any] = None,
    ) -> None:
        self.persist_directory = str(
            Path(persist_directory or settings.chroma_persist_directory).resolve()
        )
        self.collection_name = collection_name
        self.embedding_model = embedding_model or settings.embedding_model
        self.api_key = api_key if api_key is not None else settings.effective_gemini_api_key
        self._custom_embeddings = embeddings
        self._embeddings: Optional[Any] = None
        self._vector_store: Optional[Any] = None
        self._init_store()

    def _get_embeddings(self) -> Any:
        if self._custom_embeddings is not None:
            return self._custom_embeddings
        if self._embeddings is not None:
            return self._embeddings

        if not self.api_key:
            raise ValueError(
                "CRITICAL CONFIGURATION ERROR: ChromaDB memory backend requires GEMINI_API_KEY or GOOGLE_API_KEY in .env."
            )

        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        self._embeddings = GoogleGenerativeAIEmbeddings(
            model=self.embedding_model,
            google_api_key=self.api_key,
        )
        return self._embeddings

    def _init_store(self) -> None:
        from langchain_chroma import Chroma

        Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
        embeddings = self._get_embeddings()

        self._vector_store = Chroma(
            collection_name=self.collection_name,
            embedding_function=embeddings,
            persist_directory=self.persist_directory,
            collection_metadata={"hnsw:space": "cosine"},
        )

    def store(self, item: MemoryItem) -> str:
        """Persist a memory item and its embedding into ChromaDB."""
        if not item.id:
            item.id = f"mem-{uuid.uuid4().hex[:8]}"

        # Prepare metadata compatible with ChromaDB (primitive values only)
        chroma_metadata: Dict[str, Any] = {
            "id": item.id,
            "category": item.category.value,
            "timestamp": item.timestamp,
            "task_id": item.task_id or "",
            "_custom_metadata_json": json.dumps(item.metadata),
        }
        # Add top-level primitives from item.metadata for easy Chroma where-filtering
        for k, v in item.metadata.items():
            if isinstance(v, (str, int, float, bool)):
                chroma_metadata[k] = v

        # Check if item ID already exists to support clean update without duplicates
        try:
            existing = self._vector_store.get(ids=[item.id])
            if existing and existing.get("ids") and len(existing["ids"]) > 0:
                self._vector_store.delete(ids=[item.id])
        except Exception as e:
            logger.debug("ChromaDB pre-store check for id %s: %s", item.id, e)

        self._vector_store.add_texts(
            texts=[item.content],
            metadatas=[chroma_metadata],
            ids=[item.id],
        )
        logger.debug("Stored ChromaDB memory %s [%s]", item.id, item.category)
        return item.id

    def retrieve(
        self,
        query: str,
        category: Optional[MemoryCategory] = None,
        limit: int = 5,
        min_relevance: float = 0.05,
    ) -> List[MemoryItem]:
        """Perform embedding-based semantic similarity search in ChromaDB."""
        if not query or not query.strip():
            return []

        filter_dict = {"category": category.value} if category else None

        try:
            results_with_score = self._vector_store.similarity_search_with_score(
                query=query.strip(),
                k=limit,
                filter=filter_dict,
            )
        except Exception as e:
            logger.error("ChromaDB similarity search error: %s", e)
            raise

        items: List[MemoryItem] = []
        for doc, distance in results_with_score:
            # In Chroma with cosine space, distance is cosine distance (0.0 to 2.0).
            # Relevance score is 1.0 - distance, bounded between [0.0, 1.0].
            relevance = max(0.0, min(1.0, round(1.0 - float(distance), 4)))

            if relevance >= min_relevance:
                meta = doc.metadata or {}
                raw_cat = meta.get("category", MemoryCategory.REUSABLE_KNOWLEDGE.value)
                try:
                    cat = MemoryCategory(raw_cat)
                except Exception:
                    cat = MemoryCategory.REUSABLE_KNOWLEDGE

                # Reconstruct custom metadata
                custom_meta: Dict[str, Any] = {}
                if "_custom_metadata_json" in meta:
                    try:
                        custom_meta = json.loads(meta["_custom_metadata_json"])
                    except Exception:
                        pass
                else:
                    for k, v in meta.items():
                        if k not in ("id", "category", "timestamp", "task_id"):
                            custom_meta[k] = v

                item_id = doc.id or meta.get("id") or f"mem-{uuid.uuid4().hex[:8]}"

                items.append(
                    MemoryItem(
                        id=str(item_id),
                        category=cat,
                        content=doc.page_content,
                        metadata=custom_meta,
                        timestamp=str(meta.get("timestamp", datetime.now(timezone.utc).isoformat())),
                        task_id=meta.get("task_id") or None,
                        relevance_score=relevance,
                        scoring_method="cosine_similarity",
                    )
                )

        # Sort descending by relevance score and apply limit
        items.sort(key=lambda m: m.relevance_score or 0.0, reverse=True)
        return items[:limit]

    def delete(self, item_id: str) -> bool:
        """Remove a memory item by ID from ChromaDB."""
        try:
            existing = self._vector_store.get(ids=[item_id])
            if existing and existing.get("ids") and len(existing["ids"]) > 0:
                self._vector_store.delete(ids=[item_id])
                logger.debug("Deleted ChromaDB memory %s", item_id)
                return True
            return False
        except Exception as e:
            logger.warning("Error deleting memory %s from ChromaDB: %s", item_id, e)
            return False

    def clear(self, category: Optional[MemoryCategory] = None) -> int:
        """Clear memories from ChromaDB, optionally filtered by category."""
        try:
            if category:
                existing = self._vector_store.get(where={"category": category.value})
                ids = existing.get("ids", [])
                if ids:
                    self._vector_store.delete(ids=ids)
                logger.debug("Cleared %d ChromaDB memories for category %s", len(ids), category.value)
                return len(ids)
            else:
                all_records = self._vector_store.get()
                ids = all_records.get("ids", [])
                if ids:
                    self._vector_store.delete(ids=ids)
                logger.debug("Cleared all %d ChromaDB memories", len(ids))
                return len(ids)
        except Exception as e:
            logger.warning("Error clearing ChromaDB memories: %s", e)
            return 0


def get_memory_store(
    backend: Optional[str] = None,
    **kwargs: Any,
) -> MemoryStore:
    """Factory function to instantiate the configured MemoryStore backend.
    
    Supported backends:
      - 'sqlite': Lightweight SQL database with token-based TF-IDF cosine similarity.
      - 'chroma': ChromaDB persistent vector storage with Gemini embeddings.
    """
    target_backend = (backend or settings.memory_backend).strip().lower()

    if target_backend == "sqlite":
        return SqliteMemoryStore(**kwargs)
    elif target_backend == "chroma":
        settings.validate_chroma_config()
        return ChromaMemoryStore(**kwargs)
    else:
        raise ValueError(
            f"Unsupported MEMORY_BACKEND '{target_backend}'. "
            "Supported backends are: 'sqlite', 'chroma'."
        )


class LazyMemoryStoreProxy(MemoryStore):
    """Dynamic proxy delegating to the configured MemoryStore backend."""

    def __init__(self) -> None:
        self._delegate: Optional[MemoryStore] = None

    def _get_store(self) -> MemoryStore:
        if self._delegate is None:
            self._delegate = get_memory_store()
        return self._delegate

    def reset_delegate(self) -> None:
        """Reset the cached delegate instance (useful when modifying configuration in tests)."""
        self._delegate = None

    def store(self, item: MemoryItem) -> str:
        return self._get_store().store(item)

    def retrieve(
        self,
        query: str,
        category: Optional[MemoryCategory] = None,
        limit: int = 5,
        min_relevance: float = 0.05,
    ) -> List[MemoryItem]:
        return self._get_store().retrieve(query, category, limit, min_relevance)

    def delete(self, item_id: str) -> bool:
        return self._get_store().delete(item_id)

    def clear(self, category: Optional[MemoryCategory] = None) -> int:
        return self._get_store().clear(category)


# Global default memory store instance (lazy proxy delegating to configured backend)
memory_store: MemoryStore = LazyMemoryStoreProxy()
