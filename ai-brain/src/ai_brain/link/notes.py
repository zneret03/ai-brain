"""Notes, linked to the code they cite; each source ok, moved or gone (A10). Plans are plans.py."""

from __future__ import annotations

import re
from collections import defaultdict

import yaml

from ..extract import files
from . import Ctx

CITE = re.compile(
    r"(?<![\w/.-])((?:[\w@.-]+/)*[\w@-][\w@.-]*\.(?:rb|ts|tsx|js|jsx|mjs|sql|graphql|ya?ml|erb|slim))(?!\w)"
    r"(?::(\d+))?"
)


def link(ctx: Ctx) -> None:
    index = _suffix_index(ctx)
    for k in ctx.project.knowledge:
        if k.name not in ctx.shas or k.role != "notes":
            continue
        md = [(p, b) for p, b, size in ctx.listing.get(k.name, []) if p.endswith(".md") and size < 2_000_000]
        blobs = files.read_blobs(k.path, [b for _, b in md])
        for path, blob in md:
            _note(ctx, k.name, path, blobs.get(blob, b"").decode("utf-8", "replace"), index)


def _suffix_index(ctx: Ctx) -> dict[str, list[tuple[str, str]]]:
    index = defaultdict(list)
    for repo in ctx.parsed:
        for path in ctx.paths(repo):
            index[path.rsplit("/", 1)[-1]].append((repo, path))
    return index


def _note_node(ctx: Ctx, repo: str, path: str, **props) -> str:
    return ctx.g.node(f"{ctx.project.name}:note:{repo}:{path}", "Note", repo=repo, path=path, **props)


def _note(ctx: Ctx, repo: str, path: str, text: str, index) -> None:
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return
    if not isinstance(meta, dict) or not meta.get("sources"):
        return
    nid = _note_node(
        ctx, repo, path, kind="note", name=meta.get("id") or path, title=meta.get("title"), status=meta.get("status")
    )
    gone = []
    for src in meta.get("sources") or []:
        if not isinstance(src, dict):
            continue
        source_repo = str(src.get("repo", "")).split("/")[-1]
        for p in src.get("paths") or []:
            status, hits = _locate(ctx, source_repo, str(p), index)
            if status == "gone":
                gone.append(f"{source_repo}:{p}")
            for hit_repo, hit_path in hits[:20]:
                ctx.g.edge("CITES", nid, ctx.g.file_id(hit_repo, hit_path), status=status, cited=f"{source_repo}:{p}")
    ctx.g.nodes[nid][1]["gone"] = gone


def _locate(ctx: Ctx, repo: str, path: str, index) -> tuple[str, list[tuple[str, str]]]:
    """ok when the path is where the note says; moved when the same file lives elsewhere; gone otherwise."""

    def under(r: str, prefix: str) -> list[tuple[str, str]]:
        ps = ctx.paths(r)
        if prefix in ps:
            return [(r, prefix)]
        if prefix.endswith("/") or not prefix.rsplit("/", 1)[-1].count("."):
            pre = prefix.rstrip("/") + "/"
            return sorted((r, p) for p in ps if p.startswith(pre))
        return []

    if repo in ctx.parsed:
        hits = under(repo, path)
        if hits:
            return "ok", hits
    candidates = []
    mono = next((r for r in ctx.project.repos if r.role == "monorepo"), None)
    if mono:
        if repo == mono.name:
            candidates += [f"{u.prefix}{path}" for u in ctx.units if u.repo == mono.name and u.kind == "app"]
        candidates += [f"{u.prefix}{path}" for u in ctx.units if u.repo == mono.name and u.name == repo]
    for cand in candidates:
        hits = under(mono.name, cand)
        if hits:
            return "moved", hits
    name = path.rstrip("/").rsplit("/", 1)[-1]
    tail = [(r, p) for r, p in index.get(name, []) if p.endswith(path.lstrip("/"))]
    if len(tail) == 1:
        return "moved", tail
    return "gone", []


def _resolve(ctx: Ctx, cited: str, index) -> tuple[str, str] | None:
    first, _, rest = cited.partition("/")
    if first in ctx.parsed and rest in ctx.paths(first):
        return first, rest
    name = cited.rsplit("/", 1)[-1]
    hits = [
        (r, p) for r, p in index.get(name, []) if p == cited or p.endswith("/" + cited) or f"{r}/{p}".endswith(cited)
    ]
    return hits[0] if len(hits) == 1 else None
