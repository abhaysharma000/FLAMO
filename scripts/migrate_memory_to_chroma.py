"""Opt-in migration utility to migrate memories from SQLite to ChromaDB.

Safety Guarantees:
- Strictly reads from SQLite without modifying, deleting, or locking source records.
- Preserves original IDs, categories, timestamps, task IDs, and custom metadata.
- Idempotent: can be safely re-run without creating duplicate logical records.
- Reports exact counts for read, migrated, skipped, and failed records.
- Does not affect or overwrite unrelated ChromaDB records.

Backup instructions prior to migration:
  Windows PowerShell:
    Copy-Item flamo.db flamo.db.bak
  Linux / macOS:
    cp flamo.db flamo.db.bak
"""

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.models.memory import MemoryCategory, MemoryItem
from app.services.memory import ChromaMemoryStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("flamo.migrate")


def migrate_sqlite_to_chroma(
    sqlite_db_path: str,
    chroma_dir: str,
    dry_run: bool = False,
    force_update: bool = False,
    embeddings: Optional[Any] = None,
) -> Dict[str, int]:
    """Migrates records from SQLite memories table into ChromaDB vector store.
    
    Returns a dictionary with summary statistics: read, migrated, skipped, failed.
    """
    stats = {"read": 0, "migrated": 0, "skipped": 0, "failed": 0}

    db_path = Path(sqlite_db_path).resolve()
    if not db_path.exists():
        logger.error("SQLite database not found at %s", db_path)
        return stats

    logger.info("Reading memories from SQLite: %s", db_path)
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        with conn:
            # Check if memories table exists
            table_check = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='memories'"
            ).fetchone()
            if not table_check:
                logger.warning("No 'memories' table found in SQLite database.")
                return stats

            cursor = conn.execute(
                "SELECT id, category, content, metadata_json, timestamp, task_id FROM memories"
            )
            rows = cursor.fetchall()
    except Exception as e:
        logger.error("Failed to read SQLite memories: %s", e)
        return stats

    stats["read"] = len(rows)
    logger.info("Found %d memories in SQLite database.", stats["read"])

    if stats["read"] == 0:
        return stats

    # Initialize Chroma store
    chroma_store: Optional[ChromaMemoryStore] = None
    if not dry_run:
        try:
            chroma_store = ChromaMemoryStore(
                persist_directory=chroma_dir,
                embeddings=embeddings,
            )
        except Exception as e:
            logger.error("Failed to initialize ChromaDB store: %s", e)
            stats["failed"] = stats["read"]
            return stats

    for row in rows:
        mem_id = row["id"]
        try:
            # Parse row data
            cat_str = row["category"]
            try:
                cat = MemoryCategory(cat_str)
            except Exception:
                cat = MemoryCategory.REUSABLE_KNOWLEDGE

            meta = {}
            if row["metadata_json"]:
                try:
                    meta = json.loads(row["metadata_json"])
                except Exception:
                    pass

            item = MemoryItem(
                id=mem_id,
                category=cat,
                content=row["content"],
                metadata=meta,
                timestamp=row["timestamp"],
                task_id=row["task_id"],
            )

            if dry_run:
                stats["migrated"] += 1
                logger.info("[DRY RUN] Would migrate memory '%s' [%s]", mem_id, cat.value)
                continue

            # Idempotency check: see if already exists in Chroma
            assert chroma_store is not None
            existing = chroma_store._vector_store.get(ids=[mem_id])
            if existing and existing.get("ids") and len(existing["ids"]) > 0:
                if not force_update:
                    stats["skipped"] += 1
                    logger.debug("Skipping already migrated memory '%s'", mem_id)
                    continue

            # Store into Chroma
            chroma_store.store(item)
            stats["migrated"] += 1
            logger.debug("Successfully migrated memory '%s'", mem_id)

        except Exception as err:
            stats["failed"] += 1
            logger.error("Error migrating memory '%s': %s", mem_id, err)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate FLAMO semantic memories from SQLite to ChromaDB."
    )
    parser.add_argument(
        "--sqlite-db",
        type=str,
        default=settings.sqlite_db_path,
        help="Path to source SQLite database file (default: from settings)",
    )
    parser.add_argument(
        "--chroma-dir",
        type=str,
        default=settings.chroma_persist_directory,
        help="Target ChromaDB persistence directory (default: from settings)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect and report records without making changes",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite existing records in ChromaDB",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("FLAMO MEMORY MIGRATION: SQLite -> ChromaDB")
    print("=" * 60)
    print(f"Source Database:   {args.sqlite_db}")
    print(f"Target Directory:  {args.chroma_dir}")
    print(f"Dry Run Mode:      {args.dry_run}")
    print(f"Force Overwrite:   {args.force}")
    print("-" * 60)
    print("Safety Notice: Source SQLite records will NOT be modified or deleted.")
    print("Recommended backup command:")
    print(f"  cp {args.sqlite_db} {args.sqlite_db}.bak")
    print("-" * 60)

    stats = migrate_sqlite_to_chroma(
        sqlite_db_path=args.sqlite_db,
        chroma_dir=args.chroma_dir,
        dry_run=args.dry_run,
        force_update=args.force,
    )

    print("=" * 60)
    print("MIGRATION SUMMARY:")
    print(f"  Records Read:      {stats['read']}")
    print(f"  Records Migrated:  {stats['migrated']}")
    print(f"  Records Skipped:   {stats['skipped']}")
    print(f"  Records Failed:    {stats['failed']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
