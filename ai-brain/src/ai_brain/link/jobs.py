"""Jobs, where they are enqueued, and the recurring schedules that start them (A7, A9)."""

from __future__ import annotations

import re

from . import Ctx
from .code import primary_def, resolve_const

JOB_DIRS = re.compile(r"(^|/)app/(jobs|workers|sidekiq)/")


def link(ctx: Ctx) -> None:
    g = ctx.g
    jobs: dict[str, str] = {}
    for row in ctx.facts.get("job", []):
        rel = ctx.rel(row.get("file"))
        sid = (ctx.sym.get((rel[0], rel[1], row["class"])) if rel else None) or primary_def(ctx, row["class"])
        if sid:
            jobs[row["class"]] = sid
    for (_repo, path, qual), sid in ctx.sym.items():
        props = g.nodes[sid][1]
        if JOB_DIRS.search(path) and props.get("kind") == "class" and qual.endswith(("Job", "Worker")):
            jobs.setdefault(qual, sid)
    for sid in jobs.values():
        g.nodes[sid][1]["role"] = "job"
    for repo, files_ in ctx.parsed.items():
        for path, f in files_.items():
            for owner, const, nesting, meth, line in f.get("enqueues", []):
                cpath = resolve_const(ctx, const, nesting)
                target = jobs.get(cpath) if cpath else None
                if target:
                    g.edge("ENQUEUES", ctx.owner_id(repo, path, owner), target, line=line, via=meth)
    for row in ctx.facts.get("schedule", []):
        target = jobs.get(row.get("job")) or primary_def(ctx, row.get("job") or "")
        rel = ctx.rel(row.get("source"))
        sched = g.iface(
            "schedule",
            f"{row.get('job')}@{row.get('cron')}",
            cron=row.get("cron"),
            source=f"{rel[0]}/{rel[1]}" if rel else row.get("source"),
            standalone=row.get("standalone"),
        )
        if target:
            g.nodes[target][1]["role"] = "job"
            g.edge("SCHEDULED_BY", target, sched)
