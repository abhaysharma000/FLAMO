"""Consistent, production-grade backup script for FLAMO.

Performs an atomic SQLite backup via sqlite3.Connection.backup(),
preserving committed transactions even while the database is live in WAL mode.
Also backs up workspace reports and ChromaDB vector store data (if present),
calculates SHA-256 integrity checksums, and produces a verified manifest.json.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import sys
from pathlib import Path

# Add project root to path for settings import
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from app.config import get_settings, settings
except ImportError:
    get_settings = None
    settings = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("flamo.backup")


def calculate_sha256(filepath: Path) -> str:
    """Calculate SHA-256 checksum for a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def backup_sqlite(source_path: Path, dest_path: Path) -> dict[str, any]:
    """Perform atomic online backup of SQLite database using sqlite3.Connection.backup()."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if not source_path.exists():
        logger.warning("Source SQLite database not found at %s. Creating empty DB.", source_path)
        dest_conn = sqlite3.connect(str(dest_path))
        dest_conn.close()
        return {"status": "created_empty", "pages": 0}

    logger.info("Starting atomic SQLite backup from %s to %s", source_path, dest_path)
    source_conn = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    dest_conn = sqlite3.connect(str(dest_path))

    try:
        # Atomic lock-safe page transfer
        source_conn.backup(dest_conn, pages=100)
        dest_conn.commit()
    finally:
        source_conn.close()
        dest_conn.close()

    # Verify integrity of backup copy
    verify_conn = sqlite3.connect(str(dest_path))
    cursor = verify_conn.cursor()
    cursor.execute("PRAGMA integrity_check;")
    integrity = cursor.fetchone()[0]
    cursor.execute("PRAGMA page_count;")
    page_count = cursor.fetchone()[0]
    verify_conn.close()

    if integrity != "ok":
        raise RuntimeError(f"Backup SQLite integrity check failed: {integrity}")

    logger.info("SQLite backup complete (%d pages, integrity: %s)", page_count, integrity)
    return {"status": "ok", "pages": page_count, "integrity": integrity}


def run_backup(
    db_path: Path | None = None,
    workspace_dir: Path | None = None,
    chroma_dir: Path | None = None,
    output_dir: Path | None = None,
    tag: str | None = None,
) -> Path:
    """Execute complete FLAMO state backup."""
    cfg = get_settings() if get_settings else settings
    if db_path is None:
        if cfg and cfg.database_url.startswith("sqlite:///"):
            raw = cfg.database_url.replace("sqlite:////", "/").replace("sqlite:///", "")
            db_path = Path(raw) if Path(raw).is_absolute() else (ROOT_DIR / raw).resolve()
        else:
            db_path = ROOT_DIR / "flamo.db"

    if workspace_dir is None:
        if cfg and cfg.workspace_dir:
            workspace_dir = Path(cfg.workspace_dir).resolve()
        else:
            workspace_dir = ROOT_DIR / "workspace"

    if chroma_dir is None:
        if cfg and cfg.chroma_persist_directory:
            chroma_dir = Path(cfg.chroma_persist_directory).resolve()
        else:
            chroma_dir = ROOT_DIR / "chroma_db"

    now = datetime.datetime.now(datetime.timezone.utc)
    timestamp_str = now.strftime("%Y%m%d_%H%M%S")
    folder_name = f"backup_{timestamp_str}_{tag}" if tag else f"backup_{timestamp_str}"

    base_backup_root = output_dir or (ROOT_DIR / "backups")
    target_backup_dir = (base_backup_root / folder_name).resolve()
    target_backup_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, any] = {
        "timestamp": now.isoformat(),
        "backup_tag": tag,
        "flamo_version": "2.0.0",
        "artifacts": {},
    }

    # 1. SQLite Backup
    dest_db = target_backup_dir / "flamo.db"
    db_meta = backup_sqlite(db_path, dest_db)
    manifest["sqlite"] = {
        "source": str(db_path),
        "file": "flamo.db",
        "sha256": calculate_sha256(dest_db),
        "size_bytes": dest_db.stat().st_size,
        "metadata": db_meta,
    }

    # 2. Workspace Reports & Artifacts Backup
    workspace_dest = target_backup_dir / "workspace"
    manifest["workspace"] = {"source": str(workspace_dir), "files": {}}
    if workspace_dir.exists() and workspace_dir.is_dir():
        workspace_dest.mkdir(parents=True, exist_ok=True)
        file_count = 0
        for root, _, files in os.walk(workspace_dir):
            for file in files:
                src_file = Path(root) / file
                rel_path = src_file.relative_to(workspace_dir)
                dst_file = workspace_dest / rel_path
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
                manifest["workspace"]["files"][str(rel_path).replace("\\", "/")] = {
                    "sha256": calculate_sha256(dst_file),
                    "size_bytes": dst_file.stat().st_size,
                }
                file_count += 1
        logger.info("Workspace backup complete (%d files copied)", file_count)
    else:
        logger.info("Workspace directory does not exist yet. Skipped.")

    # 3. ChromaDB Vector Store Backup
    chroma_dest = target_backup_dir / "chroma_db"
    manifest["chroma_db"] = {"source": str(chroma_dir), "included": False, "files": {}}
    if chroma_dir.exists() and chroma_dir.is_dir():
        chroma_dest.mkdir(parents=True, exist_ok=True)
        chroma_count = 0
        for root, _, files in os.walk(chroma_dir):
            for file in files:
                src_file = Path(root) / file
                rel_path = src_file.relative_to(chroma_dir)
                dst_file = chroma_dest / rel_path
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
                manifest["chroma_db"]["files"][str(rel_path).replace("\\", "/")] = {
                    "sha256": calculate_sha256(dst_file),
                    "size_bytes": dst_file.stat().st_size,
                }
                chroma_count += 1
        manifest["chroma_db"]["included"] = True
        logger.info("ChromaDB backup complete (%d files copied)", chroma_count)
    else:
        logger.info("ChromaDB directory does not exist or vector memory inactive. Skipped.")

    # 4. Write verified manifest
    manifest_path = target_backup_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    logger.info("Backup successfully created at %s", target_backup_dir)
    return target_backup_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FLAMO Backup Utility")
    parser.add_argument("--db-path", type=Path, default=None, help="Path to SQLite database")
    parser.add_argument("--workspace-dir", type=Path, default=None, help="Path to workspace directory")
    parser.add_argument("--chroma-dir", type=Path, default=None, help="Path to ChromaDB directory")
    parser.add_argument("--output-dir", type=Path, default=None, help="Destination directory for backups")
    parser.add_argument("--tag", type=str, default=None, help="Optional tag for backup name")
    args = parser.parse_args()

    run_backup(
        db_path=args.db_path,
        workspace_dir=args.workspace_dir,
        chroma_dir=args.chroma_dir,
        output_dir=args.output_dir,
        tag=args.tag,
    )
