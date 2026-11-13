"""Specs and what they pin: RSpec describe and mirrored paths, Jest imports, Playwright page objects and tags (A10)."""

from __future__ import annotations

import re

from ..model import TEST_PATH
from . import Ctx
from .code import primary_def, resolve_const

TEST = TEST_PATH


def link(ctx: Ctx) -> None:
    g = ctx.g
    pages = [
        (nid, props["repo"], props["display"])
        for nid, (labels, props) in g.nodes.items()
        if "Interface" in labels and props.get("kind") == "pilet_page"
    ]
    for repo, files_ in ctx.parsed.items():
        paths = set(files_)
        for path, f in files_.items():
            if not TEST.search(path):
                continue
            fid = g.file_id(repo, path)
            g.node(fid, "Test")
            for const, nesting, line in f.get("describe", []):
                cpath = resolve_const(ctx, const, nesting) or const.lstrip(":")
                target = primary_def(ctx, cpath)
                if target:
                    g.edge("TESTS", fid, target, line=line, via="describe")
            m = re.match(r"(.*?)spec/(.+)_spec\.rb$", path)
            if m:
                for base in ("app/", "lib/", "app/graphql/", ""):
                    cand = f"{m.group(1)}{base}{m.group(2)}.rb"
                    if cand in paths:
                        g.edge("TESTS", fid, g.file_id(repo, cand), via="path")
                        break
            if f.get("lang") == "ts":
                for _local, (_imported, target, _module) in ctx.imports.get((repo, path), {}).items():
                    if target and not TEST.search(target):
                        g.edge("TESTS", fid, g.file_id(repo, target), via="import")
                        for goto in _gotos(ctx, repo, target):
                            for pid in _match_pages(pages, goto):
                                g.edge("TESTS", fid, pid, via=target)
                for tag, line in f.get("tags", []):
                    tid = g.node(f"{ctx.project.name}:ticket:{tag}", "Ticket", name=tag)
                    g.edge("TAGGED", fid, tid, line=line)


def _gotos(ctx: Ctx, repo: str, path: str) -> list[str]:
    return [p for p, _ in ctx.parsed.get(repo, {}).get(path, {}).get("gotos", [])]


def _match_pages(pages, url: str) -> list[str]:
    """Pilet pages whose path (after the /p/ prefix the shell adds) is the longest prefix of the URL."""
    path = re.sub(r"^\{\}", "", url).split("?")[0]
    path = re.sub(r"^/p/", "", path).strip("/")
    best, size = [], -1
    for nid, _repo, page in pages:
        pat = re.sub(r":\w+", "[^/]+", page.strip("/"))
        if re.fullmatch(pat, path) or path.startswith(page.strip("/") + "/") or re.match(pat + "(/|$)", path):
            if len(page) > size:
                best, size = [nid], len(page)
            elif len(page) == size:
                best.append(nid)
    return best
