"""Optional: tickets to the files their commits changed, and who committed them, from git log at origin/<ref> (A10).
Off without a [tickets] prefix in project.toml."""

from __future__ import annotations

import re
import subprocess
from collections import Counter

from . import Ctx

LIMIT = 3000


def link(ctx: Ctx) -> None:
    prefix = ctx.project.ticket_prefix
    if not prefix:
        return
    p = re.escape(prefix)
    key_re = re.compile(rf"\b{p}-(\d+)\b|/{p}-(\d+)(?:-\d+)*-v\d+", re.I)  # in a subject, or a branch .../proj-12-v1
    g = ctx.g
    seen: dict[str, dict] = {}
    for repo in ctx.project.repos:
        if repo.name not in ctx.shas or repo.role in ("library",):
            continue
        out = subprocess.run(
            [
                "git",
                "-C",
                str(repo.path),
                "log",
                f"-{LIMIT}",
                "--format=%x00%an%x01%cs%x01%s",
                "--name-only",
                ctx.shas[repo.name],
            ],
            capture_output=True,
            text=True,
        ).stdout
        for chunk in out.split("\0")[1:]:
            head, _, names = chunk.partition("\n")
            author, date, subject = (head.split("\x01") + ["", ""])[:3]
            keys = {f"{prefix}-{a or b}" for a, b in key_re.findall(subject)}
            for key in keys:
                tid = g.node(f"{ctx.project.name}:ticket:{key}", "Ticket", name=key)
                s = seen.setdefault(tid, {"authors": Counter(), "commits": 0, "last": "", "repos": set()})
                s["authors"][author] += 1
                s["commits"] += 1
                s["last"] = max(s["last"], date)
                s["repos"].add(repo.name)
                for path in names.split("\n"):
                    fid = g.file_id(repo.name, path.strip())
                    if path.strip() and fid in g.nodes:
                        g.edge("CHANGED", tid, fid)
    for tid, s in seen.items():
        g.nodes[tid][1].update(
            authors=[f"{a} ×{n}" for a, n in s["authors"].most_common(5)],
            commits=s["commits"],
            last=s["last"] or None,
            repos=sorted(s["repos"]),
        )
