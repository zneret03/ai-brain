"""Parse every wanted file of a repo at a commit, through a cache keyed by blob sha, in a process pool. A file the
generic reader reads is keyed by blob, language and query digest, so a changed query reads it again."""

from __future__ import annotations

import json
import os
import sqlite3
import zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from ..config import VAR
from . import files, languages, skeleton


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


def _key(path: str, blob: str) -> str:
    lang = languages.language_for(path)
    return blob if lang is None or lang in languages.OWN else f"{blob}:{lang}:{languages.digest(lang)}"


def parse_tree(repo: Path, sha: str, keep=files.wanted) -> tuple[dict[str, dict], list[tuple[str, str, int]]]:
    """({path: facts}, full listing) for the repo at sha."""
    listing = files.ls_tree(repo, sha)
    languages.ensure({languages.language_for(p) for p, _, size in listing if keep(p, size)})
    wanted = [(p, _key(p, b)) for p, b, size in listing if keep(p, size)]
    db = _cache()
    keys = {k for _, k in wanted}
    have: dict[str, bytes] = {}
    key_list = list(keys)
    for i in range(0, len(key_list), 900):
        chunk = key_list[i : i + 900]
        rows = db.execute(f"SELECT blob, data FROM parse WHERE blob IN ({','.join('?' * len(chunk))})", chunk)
        have.update(rows.fetchall())
    missing = sorted(keys - have.keys())
    if missing:
        data = files.read_blobs(repo, sorted({k.split(":", 1)[0] for k in missing}))
        paths = {k: p for p, k in wanted}
        jobs = [(paths[k], k, data[k.split(":", 1)[0]]) for k in missing if k.split(":", 1)[0] in data]
        size = max(1, len(jobs) // ((os.cpu_count() or 4) * 4))
        batches = [jobs[i : i + size] for i in range(0, len(jobs), size)]
        workers = min(12, os.cpu_count() or 4)
        with ProcessPoolExecutor(
            max_workers=workers, initializer=languages.configure, initargs=languages.current()
        ) as pool:
            for result in pool.map(_work, batches):
                db.executemany("INSERT OR REPLACE INTO parse VALUES (?, ?)", result)
                have.update(result)
        db.commit()
    db.close()
    parsed = {p: json.loads(zlib.decompress(have[k])) for p, k in wanted if k in have}
    return parsed, listing
