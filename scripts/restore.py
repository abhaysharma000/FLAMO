"""Consistent, safe restore script for FLAMO.

Validates manifest.json integrity checksums and runs PRAGMA integrity_check
before restoring SQLite database, workspace artifacts, and ChromaDB vector store.
"""

from __future__ import annotations

import argparse
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
logger = logging.getLogger("flamo.restore")


def calculate_sha256(filepath: Path) -> str:
    """Calculate SHA-256 checksum for a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_manifest(backup_dir: Path) -> dict[str, any]:
    """Verify integrity of all files in the backup directory against manifest.json."""
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found at {manifest_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # 1. Verify SQLite database checksum
    sqlite_info = manifest.get("sqlite")
    if sqlite_info:
        db_file = backup_dir / sqlite_info["file"]
        if not db_file.exists():
            raise FileNotFoundError(f"SQLite backup file missing: {db_file}")
        actual_sha = calculate_sha256(db_file)
        if actual_sha != sqlite_info["sha256"]:
            raise ValueError(
                f"SQLite backup checksum mismatch! Expected {sqlite_info['sha256']}, got {actual_sha}"
            )

    # 2. Verify workspace files
    workspace_info = manifest.get("workspace", {})
    for rel_path, meta in workspace_info.get("files", {}).items():
        file_path = backup_dir / "workspace" / rel_path
        if not file_path.exists():
            raise FileNotFoundError(f"Workspace file missing from backup: {file_path}")
        actual_sha = calculate_sha256(file_path)
        if actual_sha != meta["sha256"]:
            raise ValueError(
                f"Workspace file checksum mismatch ({rel_path})! Expected {meta['sha256']}, got {actual_sha}"
            )

    # 3. Verify ChromaDB files
    chroma_info = manifest.get("chroma_db", {})
    if chroma_info.get("included"):
        for rel_path, meta in chroma_info.get("files", {}).items():
            file_path = backup_dir / "chroma_db" / rel_path
            if not file_path.exists():
                raise FileNotFoundError(f"ChromaDB file missing from backup: {file_path}")
            actual_sha = calculate_sha256(file_path)
            if actual_sha != meta["sha256"]:
                raise ValueError(
                    f"ChromaDB file checksum mismatch ({rel_path})! Expected {meta['sha256']}, got {actual_sha}"
                )

    logger.info("Backup manifest and all file checksums verified successfully.")
    return manifest


def restore_backup(
    backup_dir: Path,
    dest_db_path: Path | None = None,
    dest_workspace_dir: Path | None = None,
    dest_chroma_dir: Path | None = None,
    force: bool = False,
) -> bool:
    """Execute verified restoration of FLAMO state."""
    cfg = get_settings() if get_settings else settings
    if dest_db_path is None:
        if cfg and cfg.database_url.startswith("sqlite:///"):
            raw = cfg.database_url.replace("sqlite:////", "/").replace("sqlite:///", "")
            dest_db_path = Path(raw) if Path(raw).is_absolute() else (ROOT_DIR / raw).resolve()
        else:
            dest_db_path = ROOT_DIR / "flamo.db"

    if dest_workspace_dir is None:
        if cfg and cfg.workspace_dir:
            dest_workspace_dir = Path(cfg.workspace_dir).resolve()
        else:
            dest_workspace_dir = ROOT_DIR / "workspace"

    if dest_chroma_dir is None:
        if cfg and cfg.chroma_persist_directory:
            dest_chroma_dir = Path(cfg.chroma_persist_directory).resolve()
        else:
            dest_chroma_dir = ROOT_DIR / "chroma_db"

    logger.info("Restoring from backup at: %s", backup_dir)
    manifest = verify_manifest(backup_dir)

    # 1. Restore SQLite Database safely using sqlite3.Connection.backup()
    source_db_file = backup_dir / manifest["sqlite"]["file"]
    dest_db_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Restoring SQLite database to %s", dest_db_path)
    source_conn = sqlite3.connect(f"file:{source_db_file}?mode=ro", uri=True)
    dest_conn = sqlite3.connect(str(dest_db_path))
    try:
        source_conn.backup(dest_conn, pages=100)
        dest_conn.commit()
    finally:
        source_conn.close()
        dest_conn.close()

    # Verify restored SQLite DB
    verify_conn = sqlite3.connect(str(dest_db_path))
    cursor = verify_conn.cursor()
    cursor.execute("PRAGMA integrity_check;")
    integrity = cursor.fetchone()[0]
    verify_conn.close()
    if integrity != "ok":
        raise RuntimeError(f"Restored database failed integrity check: {integrity}")
    logger.info("SQLite database restored successfully (integrity: %s)", integrity)

    # 2. Restore Workspace Files
    backup_workspace_dir = backup_dir / "workspace"
    if backup_workspace_dir.exists() and backup_workspace_dir.is_dir():
        dest_workspace_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        for root, _, files in os.walk(backup_workspace_dir):
            for file in files:
                src_file = Path(root) / file
                rel_path = src_file.relative_to(backup_workspace_dir)
                dst_file = dest_workspace_dir / rel_path
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
                count += 1
        logger.info("Workspace restored (%d files copied to %s)", count, dest_workspace_dir)

    # 3. Restore ChromaDB if present in backup
    chroma_info = manifest.get("chroma_db", {})
    if chroma_info.get("included"):
        backup_chroma_dir = backup_dir / "chroma_db"
        if backup_chroma_dir.exists() and backup_chroma_dir.is_dir():
            dest_chroma_dir.mkdir(parents=True, exist_ok=True)
            count = 0
            for root, _, files in os.walk(backup_chroma_dir):
                for file in files:
                    src_file = Path(root) / file
                    rel_path = src_file.relative_to(backup_chroma_dir)
                    dst_file = dest_chroma_dir / rel_path
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dst_file)
                    count += 1
            logger.info("ChromaDB restored (%d files copied to %s)", count, dest_chroma_dir)

    logger.info("Restoration complete.")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FLAMO Restore Utility")
    parser.add_argument("--backup-dir", type=Path, required=True, help="Path to backup directory containing manifest.json")
    parser.add_argument("--dest-db-path", type=Path, default=None, help="Destination path for SQLite database")
    parser.add_argument("--dest-workspace-dir", type=Path, default=None, help="Destination path for workspace")
    parser.add_argument("--dest-chroma-dir", type=Path, default=None, help="Destination path for ChromaDB")
    args = parser.parse_args()

    restore_backup(
        backup_dir=args.backup_dir,
        dest_db_path=args.dest_db_path,
        dest_workspace_dir=args.dest_workspace_dir,
        dest_chroma_dir=args.dest_chroma_dir,
    )
