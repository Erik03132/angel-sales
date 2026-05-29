#!/usr/bin/env python3
"""auto_cleanup.py – автономный агент‑очиститель.

Запускается как отдельный процесс (PM2) и каждые N минут сканирует:
  • Локальные директории (CONFIG['LOCAL_PATHS'])
  • Смонтированную папку NAS (CONFIG['NAS_MOUNT'])

Функции:
  1. Поиск дубликатов (SHA‑256) и перемещение их в папку
     <NAS_MOUNT>/duplicates/ (чтобы не потерять данные).
  2. Удаление пустых каталогов (по желанию).
  3. Вывод отчёта в лог (JSON‑строка) – удобно парсить.

Конфигурация берётся из .env (используется python‑dotenv).
Переменные .env:
  CLEAN_LOCAL_PATHS   – пробел‑разделённый список локальных путей для сканирования
  CLEAN_NAS_MOUNT    – точка монтирования NAS (must be already mounted)
  CLEAN_DUP_DEST     – куда перемещать дубликаты на NAS (по умолчанию <NAS_MOUNT>/duplicates)
  CLEAN_INTERVAL_MIN – интервал в минутах между сканами (для PM2 – cron‑правило)
  CLEAN_REMOVE_EMPTY – "yes"/"no" – удалять пустые директории после перемещения

Запуск через PM2 (пример в ecosystem.config.js) – будет работать 24/7.
"""

import hashlib
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Load environment variables (fallback defaults)
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

LOCAL_PATHS = os.getenv("CLEAN_LOCAL_PATHS", "").split()
NAS_MOUNT = os.getenv("CLEAN_NAS_MOUNT", "")
DUP_DEST = os.getenv("CLEAN_DUP_DEST", "")
INTERVAL = int(os.getenv("CLEAN_INTERVAL_MIN", "60"))
REMOVE_EMPTY = os.getenv("CLEAN_REMOVE_EMPTY", "no").lower() == "yes"

if not LOCAL_PATHS or not NAS_MOUNT:
    print(json.dumps({"error": "CLEAN_LOCAL_PATHS or CLEAN_NAS_MOUNT not set in .env"}))
    sys.exit(1)

if not DUP_DEST:
    DUP_DEST = os.path.join(NAS_MOUNT, "duplicates")

# Ensure destination exists
os.makedirs(DUP_DEST, exist_ok=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def sha256_path(path: Path, block_size: int = 65536) -> str:
    """Calculate SHA‑256 hash of a file."""
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(block_size), b''):
            h.update(block)
    return h.hexdigest()

def scan_paths(paths: list[Path]) -> dict[str, list[Path]]:
    """Return dict {hash: [paths...]}. Only files are considered."""
    hash_map: dict[str, list[Path]] = {}
    for root in paths:
        for file in root.rglob('*'):
            if file.is_file():
                try:
                    h = sha256_path(file)
                except Exception:
                    # Skip unreadable files, log later
                    continue
                hash_map.setdefault(h, []).append(file)
    return hash_map

def move_duplicates(hash_map: dict[str, list[Path]]) -> list[dict]:
    """For each hash with >1 files, keep the first (by sorted path) and move others.
    Returns a list of actions for logging.
    """
    actions = []
    for h, files in hash_map.items():
        if len(files) <= 1:
            continue
        # Sort to have deterministic "keep" file
        files.sort()
        keep = files[0]
        for dup in files[1:]:
            # Build destination path preserving relative structure if possible
            rel = dup.relative_to('/') if dup.is_absolute() else dup
            dest = Path(DUP_DEST) / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(dup), str(dest))
                actions.append({
                    "kept": str(keep),
                    "moved": str(dup),
                    "dest": str(dest),
                    "hash": h,
                })
            except Exception as e:
                actions.append({
                    "error": str(e),
                    "file": str(dup),
                })
    return actions

def remove_empty_dirs(paths: list[Path]):
    removed = []
    for root in paths:
        for d in list(root.rglob('*')):
            if d.is_dir():
                try:
                    # rmdir succeeds only if dir empty
                    d.rmdir()
                    removed.append(str(d))
                except Exception:
                    pass
    return removed

# ---------------------------------------------------------------------------
# Main loop (single iteration – PM2 will restart according to cron schedule)
# ---------------------------------------------------------------------------
def main():
    start = datetime.utcnow().isoformat() + 'Z'
    report = {
        "timestamp": start,
        "local_paths": LOCAL_PATHS,
        "nas_mount": NAS_MOUNT,
        "dup_destination": DUP_DEST,
        "actions": [],
        "removed_empty": [],
        "errors": [],
    }
    try:
        # Build list of Path objects for scanning
        scan_targets = [Path(p).expanduser().resolve() for p in LOCAL_PATHS]
        if NAS_MOUNT:
            scan_targets.append(Path(NAS_MOUNT).resolve())

        hash_map = scan_paths(scan_targets)
        dup_actions = move_duplicates(hash_map)
        report["actions"] = dup_actions

        if REMOVE_EMPTY:
            removed = remove_empty_dirs(scan_targets)
            report["removed_empty"] = removed
    except Exception as exc:
        report["errors"].append(str(exc))

    # Output JSON line – PM2 logs will capture it
    print(json.dumps(report, ensure_ascii=False))

if __name__ == "__main__":
    main()
