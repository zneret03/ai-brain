"""Parse every wanted file of a repo at a commit, through a cache keyed by blob sha, in a process pool."""

from __future__ import annotations

import json
import os
import sqlite3
import zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from ..config import VAR
from . import files, skeleton


def _cache() -> sqlite3.Connection:
    path = VAR / "cache" / f"parse-v{skeleton.VERSION}.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE IF NOT EXISTS parse (blob TEXT PRIMARY KEY, data BLOB)")
    return db


def _work(batch: list[tuple[str, str, bytes]]) -> list[tuple[str, bytes]]:
    out = []
    for path, blob, data in batch:
        try:
            facts = skeleton.parse(path, data)
        except Exception as exc:  # one bad file must not stop the index; coverage reports it
            facts = {"lang": "?", "error": True, "fatal": str(exc)[:200]}
        out.append((blob, zlib.compress(json.dumps(facts, separators=(",", ":")).encode(), 1)))
    return out


def parse_tree(repo: Path, sha: str, keep=files.wanted) -> tuple[dict[str, dict], list[tuple[str, str, int]]]:
    """({path: facts}, full listing) for the repo at sha."""
    listing = files.ls_tree(repo, sha)
    wanted = [(p, b) for p, b, size in listing if keep(p, size)]
    db = _cache()
    blobs = {b for _, b in wanted}
    have: dict[str, bytes] = {}
    blob_list = list(blobs)
    for i in range(0, len(blob_list), 900):
        chunk = blob_list[i : i + 900]
        rows = db.execute(f"SELECT blob, data FROM parse WHERE blob IN ({','.join('?' * len(chunk))})", chunk)
        have.update(rows.fetchall())
    missing = sorted(blobs - have.keys())
    if missing:
        data = files.read_blobs(repo, missing)
        paths = {b: p for p, b in wanted}
        jobs = [(paths[b], b, data[b]) for b in missing if b in data]
        size = max(1, len(jobs) // ((os.cpu_count() or 4) * 4))
        batches = [jobs[i : i + size] for i in range(0, len(jobs), size)]
        workers = min(12, os.cpu_count() or 4)
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for result in pool.map(_work, batches):
                db.executemany("INSERT OR REPLACE INTO parse VALUES (?, ?)", result)
                have.update(result)
        db.commit()
    db.close()
    parsed = {p: json.loads(zlib.decompress(have[b])) for p, b in wanted if b in have}
    return parsed, listing
