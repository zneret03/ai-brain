"""The verbs, for the CLI and for short scripts: `from ai_brain import api; print(api.impact("Type.field"))`.
Each returns the CLI's text; a multi-step script prints only its final answer (A12)."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from collections import Counter
from contextlib import contextmanager

from . import indexer, output
from .config import BRAIN, VAR, load_project
from .extract import files
from .graph import queries as Q
from .graph.driver import Unreachable, connect
from .model import TEST_PATH, tokens
from .output import emit, loc


class NotRun(Exception):
    def __init__(self, reason: str, code: int):
        super().__init__(reason)
        self.reason, self.code = reason, code


@contextmanager
def _session():
    try:
        driver = connect()
    except Unreachable as exc:
        raise NotRun(str(exc), output.UNREACHABLE) from exc
    try:
        with driver.session() as session:
            yield session
    finally:
        driver.close()


def _project(name: str | None = None):
    return load_project(name)


def _stale(project, state) -> dict[str, int]:
    moved = {}
    for repo, sha in (state.get("indexed") or {}).items():
        r = project.repo(repo)
        if r is None or not r.path.exists():
            continue
        lock = indexer.lockfile(project) if r.role == "library" else None
        try:
            if r.role == "library":
                cur = indexer.target_shas(project, lock).get(repo)
            else:
                cur = files.newest_rev(r.path, r.ref) if r.role == "sprints" else files.rev(r.path, r.ref)
        except RuntimeError:
            continue
        if cur and cur != sha:
            moved[repo] = 1
    return moved


def _head(project, check_stale: bool = True) -> str:
    state = indexer.load_state(project)
    return output.header(state, _stale(project, state) if check_stale and state else None)


def _q(words: list[str]) -> str:
    return " ".join(f"+{w}" for w in tokens(*words).split())


def _cmd(verb: str, args: list[str]) -> str:
    return "ai-brain/bin/ai-brain " + " ".join([verb, *args])


# ---------------------------------------------------------------- search verbs


def surface(words: list[str], project: str | None = None, show_all: bool = False) -> str:
    p = _project(project)
    q = _q(words)
    if not q:
        return emit(_head(p), [], "")
    with _session() as s:
        total = s.run(Q.FULLTEXT_COUNT, index="interface_search", q=q, p=p.name).single()["n"]
        rows = s.run(
            Q.SURFACE, q=q, p=p.name, lim=total if show_all else output.CAP + 1, consumers=Q.CONSUMER_EDGES
        ).data()
    lines = [
        f"{r['kind']:<17} {r['name']}  [{r['owner'] or '-'}]  {loc(r['repo'], r['path'], r['line'])}"
        f"  · {r['consumers']} consumers"
        for r in rows
    ]
    lines += ["…"] * (total - len(rows))
    return emit(_head(p), lines, _cmd("surface", words), show_all)


def find(words: list[str], project: str | None = None, show_all: bool = False) -> str:
    p = _project(project)
    q = _q(words)
    if not q:
        return emit(_head(p), [], "")
    with _session() as s:
        total = s.run(Q.FULLTEXT_COUNT, index="symbol_search", q=q, p=p.name).single()["n"]
        rows = s.run(Q.FIND, q=q, p=p.name, lim=total if show_all else output.CAP + 1).data()
    lines = [
        f"{r['kind']:<8} {r['name']}{' (' + r['role'] + ')' if r['role'] else ''}  "
        f"{loc(r['repo'], r['path'], r['line'])}  · {r['callers']} callers"
        for r in rows
    ]
    lines += ["…"] * (total - len(rows))
    return emit(_head(p), lines, _cmd("find", words), show_all)


# ---------------------------------------------------------------- by id


def _seeds(s, p, target: str) -> list[dict]:
    rows = s.run(Q.RESOLVE, p=p.name, t=target).data()
    if not rows:
        rows = s.run(Q.RESOLVE_LOOSE, p=p.name, t=target.rsplit("/", 1)[-1] if "/" in target else target).data()
    return rows


def _impact_lines(s, ids: list[str], exclude: set[str] = frozenset(), diff_files: set[str] | None = None):
    exp = s.run(Q.EXPAND, ids=ids).single()
    nodes, ifaces = exp["nodes"], exp["ifaces"]
    ifaces = list(dict.fromkeys(ifaces + [i for i in ids if i.split(":")[1] in _KINDS]))
    excl = sorted(set(nodes) | set(exclude))
    consumers, tests_of, notes_of = [], set(nodes), set(nodes)
    test_lines = []
    for r in s.run(Q.CONSUMERS, ids=ifaces, consumers=Q.CONSUMER_EDGES, exclude=excl).data():
        if diff_files is not None and f"{r['repo']}/{r['path']}" in diff_files:
            continue
        line = f"{r['rel'].lower():<13} {r['iface']} ← {r['name']}  {loc(r['repo'], r['path'], r['line'])}"
        ids = [r["cid"], r["fid"], *r["uids"]]
        tests_of.update(i for i in ids if i)
        notes_of.update(i for i in ids if i)
        (test_lines if r["rel"] == "TESTS" or TEST_PATH.search(r["path"] or "") else consumers).append(line)
        for name, repo, path, ln in r["users"]:
            if name and (diff_files is None or f"{repo}/{path}" not in diff_files):
                target = test_lines if TEST_PATH.search(path or "") else consumers
                target.append(f"{'used by':<13} {r['name']} ← {name}  {loc(repo, path, ln)}")
    for r in s.run(Q.CALLERS, ids=nodes, exclude=excl).data():
        if diff_files is not None and f"{r['repo']}/{r['path']}" in diff_files:
            continue
        tag = " (inferred)" if r["inferred"] else ""
        tag += " (cross-engine)" if r["cross"] else ""
        (test_lines if TEST_PATH.search(r["path"] or "") else consumers).append(
            f"{'called by' if r['rel'] == 'CALLS' else r['rel'].lower():<13} {r['target']} ← "
            f"{r['name']}{tag}  {loc(r['repo'], r['path'], r['line'])}"
        )
    tests = [f"{'test':<13} {loc(r['repo'], r['path'])}" for r in s.run(Q.TESTS, ids=sorted(tests_of)).data()]
    notes = [
        f"{r['kind']:<13} {loc(r['repo'], r['path'])} ({r['status'] or 'cites'})"
        for r in s.run(Q.NOTES, ids=sorted(notes_of)).data()
    ]
    return list(dict.fromkeys(consumers)), list(dict.fromkeys(tests + test_lines)), notes


_KINDS = {
    "graphql_field",
    "graphql_type",
    "graphql_operation",
    "mount",
    "route",
    "kafka_topic",
    "table",
    "flag",
    "env_var",
    "gem",
    "npm_package",
    "schedule",
    "external_api",
    "pilet_page",
    "extension_slot",
    "privilege",
    "channel",
}


def impact(
    target: str | None = None, diff: list[str] | None = None, project: str | None = None, show_all: bool = False
) -> str:
    p = _project(project)
    if diff is not None:
        return _impact_diff(p, diff, show_all)
    with _session() as s:
        seeds = _seeds(s, p, target)
        if not seeds:
            return emit(_head(p), [], "")
        consumers, tests, notes = _impact_lines(s, [r["id"] for r in seeds])
    named = ", ".join(sorted({r["id"].split(":", 2)[-1] for r in seeds})[:3])
    lines = [f"target        {named}"] + consumers + tests + notes
    return emit(_head(p), lines, _cmd("impact", [target]), show_all)


def _impact_diff(p, repos: list[str], show_all: bool) -> str:
    changed: dict[str, set[str]] = {}
    lines = []
    for spec in repos or [r.name for r in p.repos]:
        name, _, ref = spec.partition("@")
        r = p.repo(name)
        if r is None:
            continue
        if ref:  # a branch's commits, checked out or not: <tip>, or <base>...<tip> for one stacked on another
            base_ref, _, tip = ref.rpartition("...")
            try:
                paths = files.diff_names(r.path, files.merge_base(r.path, base_ref or f"origin/{r.ref}", tip), tip)
            except RuntimeError as exc:
                raise SystemExit(f"ai-brain: {spec}: {exc}") from exc
        else:
            base = files.merge_base(r.path, f"origin/{r.ref}", "HEAD")
            paths = files.diff_names(r.path, base)  # base against the working tree: committed and uncommitted
            paths += files.git(r.path, "ls-files", "--others", "--exclude-standard", check=False).splitlines()
        changed.setdefault(name, set()).update(paths)
        lines.append(f"diff          {spec}: {len(set(paths))} files since its merge base")
    all_paths = {f"{repo}/{path}" for repo, paths in changed.items() for path in paths}
    with _session() as s:
        rows = s.run(Q.DIFF_FILES, p=p.name, paths=sorted(all_paths)).data()
        ids = [r["id"] for r in rows]
        if ids:
            consumers, _, _ = _impact_lines(s, ids, diff_files=all_paths)
            lines += [c + "  (not in the diff)" for c in consumers]
    return emit(_head(p), lines, _cmd("impact", ["--diff", *repos]), show_all)


def consumers(target: str, project: str | None = None, show_all: bool = False) -> str:
    p = _project(project)
    with _session() as s:
        seeds = _seeds(s, p, target)
        lines, _, _ = _impact_lines(s, [r["id"] for r in seeds]) if seeds else ([], [], [])
    return emit(_head(p), lines, _cmd("consumers", [target]), show_all)


def trace(target: str, project: str | None = None, show_all: bool = False) -> str:
    p = _project(project)
    lines = []
    with _session() as s:
        seeds = [r for r in _seeds(s, p, target) if "Interface" in r["labels"]]
        gql = [r["id"] for r in seeds if r["kind"] in ("graphql_field", "graphql_operation")]
        other = [r["id"] for r in seeds if r["kind"] not in ("graphql_field", "graphql_operation")]
        for r in s.run(Q.TRACE_FIELD, ids=gql).data() if gql else []:
            for name, repo, path, line in r["users"]:
                if name and not TEST_PATH.search(path or ""):
                    lines.append(f"ui            {name}  {loc(repo, path, line)}")
            lines.append(f"operation     {r['op']}  {loc(r['op_repo'], r['op_path'], r['op_line'])}")
            for root, res, repo, path, line in r["roots"]:
                if root:
                    lines.append(f"field         {root} → {res or '(attribute)'}  {loc(repo, path, line)}")
            for name, repo, path, line, table in r["models"]:
                if name:
                    lines.append(f"model         {name} → {table or '?'}  {loc(repo, path, line)}")
        for r in s.run(Q.TRACE_OTHER, ids=other).data() if other else []:
            lines.append(f"{r['kind']:<13} {r['iface']}")
            for group in ("ins", "outs", "tail"):
                for rel, name, repo, path, line in r[group]:
                    if rel:
                        lines.append(f"  {rel.lower():<11} {name}  {loc(repo, path, line)}")
    return emit(_head(p), list(dict.fromkeys(lines)), _cmd("trace", [target]), show_all)


def notes(args: list[str], project: str | None = None, show_all: bool = False) -> str:
    p = _project(project)
    target = " ".join(args)
    with _session() as s:
        seeds = _seeds(s, p, target) if len(args) == 1 else []
        if seeds:
            rows = s.run(Q.NOTES, ids=[r["id"] for r in seeds]).data()
            lines = [f"{r['kind']:<6} {loc(r['repo'], r['path'])} ({r['status'] or 'cites'})" for r in rows]
        else:
            words = [w.lower() for w in args]
            rows = s.run(Q.NOTES_BY_WORDS, p=p.name, words=words).data()
            lines = [
                f"{r['kind']:<6} {loc(r['repo'], r['path'])}  · cites {r['cites']} files"
                + (f" · gone: {', '.join(r['gone'][:3])}" if r["gone"] else "")
                for r in rows
            ]
    return emit(_head(p), lines, _cmd("notes", args), show_all)


# ---------------------------------------------------------------- tickets, sprints and who built what


def _home(p) -> str | None:
    return next((k.name for k in p.knowledge if k.role == "sprints"), None)


def _sprint_order(slug: str | None) -> tuple[int, ...]:
    m = re.search(r"g(\d+)\.(\d+)", slug or "")  # a gN.M number wins, so an id in front of it (123-team-g1.2) does not
    return (int(m.group(1)), int(m.group(2))) if m else tuple(int(x) for x in re.findall(r"\d+", slug or ""))


def _key_order(key: str | None) -> int:
    m = re.search(r"(\d+)$", key or "")
    return int(m.group(1)) if m else 0


def _cut(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _branches(p, key: str) -> list[str]:
    """Every branch named for the ticket, local or on origin, in every repo: who is building it right now."""
    pat = re.compile(rf"(^|/){re.escape(key.lower())}-v\d+$")
    lines = []
    for r in p.repos + p.knowledge:
        if not r.path.exists():
            continue
        out = files.git(
            r.path,
            "for-each-ref",
            "--format=%(refname)%09%(authorname)%09%(committerdate:short)",
            "refs/heads",
            "refs/remotes/origin",
            check=False,
        )
        seen: dict[str, dict] = {}
        for row in out.splitlines():
            ref, author, date = (row.split("\t") + ["", ""])[:3]
            short = ref.removeprefix("refs/heads/").removeprefix("refs/remotes/origin/")
            if not pat.search(short.lower()):
                continue
            e = seen.setdefault(short, {"where": [], "author": author, "date": date})
            e["where"].append("local" if ref.startswith("refs/heads/") else "origin")
            if date > e["date"]:
                e.update(author=author, date=date)
        for branch, e in sorted(seen.items()):
            lines.append(f"{'branch':<13} {r.name} {branch} · {e['author']} · {e['date']} · {'+'.join(e['where'])}")
    return lines


def ticket(key: str, project: str | None = None, show_all: bool = False) -> str:
    """Everything the brain knows about one ticket: its plan, what it says to touch, what is still open, who built
    it and where, and the tickets that touched the same files."""
    p = _project(project)
    key = key.upper()
    home = _home(p)
    with _session() as s:
        docs = s.run(Q.TICKET_DOCS, p=p.name, key=key).data()
        own = sorted((d for d in docs if d["ticket"] == key), key=lambda d: (d["repo"] != home, d["kind"] != "plan"))
        rows = s.run(Q.TICKET_FILES, ids=[d["id"] for d in own]).data() if own else []
        commits = s.run(Q.TICKET_COMMITS, p=p.name, key=key).single()
        related = s.run(Q.RELATED, p=p.name, key=key, lim=5).data()
    plans = [d for d in own if d["kind"] == "plan"]
    plan = plans[0] if plans else None
    lines = []
    if plan:
        jira = " · ".join(x for x in (plan["jira_type"], plan["jira_status"], plan["owner"]) if x)
        lines.append(
            f"{'plan':<13} {loc(plan['repo'], plan['path'])}  · {plan['sprint'] or '-'}"
            + (f" · {jira}" if jira else "")
            + (f" · updated {plan['updated']}" if plan["updated"] else "")
        )
        lines += [f"{'title':<13} {plan['title']}"] if plan["title"] else []
        lines += [f"{'what':<13} {plan['tldr']}"] if plan["tldr"] else []
        lines += [f"{'built':<13} {plan['summary']}"] if plan["summary"] else []
        if plan["items_total"]:
            lines.append(f"{'items':<13} {plan['items_done']} of {plan['items_total']} done")
        lines += [f"{'parent':<13} {plan['parent']}"] if plan["parent"] else []
    lines += _branches(p, key)
    if commits and commits["commits"]:
        lines.append(
            f"{'commits':<13} {commits['commits']} on {', '.join(commits['repos'])} · {', '.join(commits['authors'])}"
            f" · last {commits['last']} · {commits['files']} files"
        )
    lines += [f"{'pr':<13} {pr}" for pr in dict.fromkeys(pr for d in own for pr in d["prs"])]
    units = Counter(
        (r["unit"], r["unit_kind"]) for r in {(r["repo"], r["path"]): r for r in rows}.values() if r["unit"]
    )
    lines += [f"{'service':<13} {u} ({k}) · {n} files" for (u, k), n in units.most_common()]
    if plan:
        lines += [f"{'gap':<13} {g}" for g in plan["gaps_open"]]
        lines += [f"{'open':<13} {i}" for i in plan["open_items"]]
    for r in rows:
        detail = " · ".join(x for x in (r["change"], r["item"]) if x)
        label = "touch" if r["rel"] == "PLANS" else "changed"
        lines.append(f"{label:<13} {loc(r['repo'], r['path'], r['line'])}" + (f"  · {detail}" if detail else ""))
    if plan:
        lines += [f"{'new':<13} {n}" for n in plan["planned_new"]]
    for d in own:
        if d["kind"] != "plan":
            lines.append(f"{d['kind']:<13} {loc(d['repo'], d['path'])}" + (f" · {d['status']}" if d["status"] else ""))
    for d in sorted((d for d in docs if d["ticket"] != key and d["kind"] == "plan"), key=lambda d: d["ticket"] or ""):
        lines.append(f"{'child':<13} {d['ticket'] or d['path']}  · {d['sprint'] or '-'} · {loc(d['repo'], d['path'])}")
    for r in related:
        lines.append(
            f"{'related':<13} {r['ticket']}  {r['shared']} shared · {r['sprint'] or '-'} · {', '.join(r['sample'])}"
        )
    lines += [f"{'also':<13} {loc(d['repo'], d['path'])}" for d in plans[1:]]
    return emit(_head(p), lines, _cmd("ticket", [key]), show_all)


def sprint(slug: str | None = None, project: str | None = None, show_all: bool = False) -> str:
    """One sprint's tickets with their state, then the files two of its plans both touch. `all` lists the sprints."""
    p = _project(project)
    with _session() as s:
        known = sorted(s.run(Q.SPRINTS, p=p.name).data(), key=lambda r: _sprint_order(r["sprint"]), reverse=True)
        if slug == "all":
            lines = [
                f"{r['sprint']:<13} {r['plans']} plans · {r['built']} built · {', '.join(sorted(r['repos']))}"
                for r in known
            ]
            return emit(_head(p), lines, _cmd("sprint", ["all"]), show_all)
        slug = slug or (known[0]["sprint"] if known else None)
        rows = s.run(Q.SPRINT, p=p.name, sprint=slug).data() if slug else []
        overlap = s.run(Q.OVERLAP, p=p.name, sprint=slug).data() if slug else []
    rows.sort(key=lambda r: (r["kind"] != "plan", -_key_order(r["ticket"])))
    lines = [f"{'sprint':<13} {slug} · {sum(r['kind'] == 'plan' for r in rows)} plans"] if slug else []
    for r in rows:
        if r["kind"] == "plan":
            items = f"{r['items_done']}/{r['items_total']} items" if r["items_total"] else "no items"
            lines.append(
                f"{r['ticket']:<13} {r['jira_status'] or '-'} · {'built' if r['built'] else 'planned'} · {items}"
                f" · {r['gaps']} open gaps · {r['files']} files  {_cut(r['title'] or '', 70)}"
            )
        else:
            lines.append(f"{r['kind']:<13} {loc(r['repo'], r['path'])}" + (f" · {r['status']}" if r["status"] else ""))
    lines += [f"{'overlap':<13} {loc(o['repo'], o['path'])}  · {', '.join(o['tickets'])}" for o in overlap]
    return emit(_head(p), lines, _cmd("sprint", [slug or ""]), show_all)


def _path_args(p, target: str) -> dict:
    t = target.strip().removeprefix("./").rstrip("/")
    first, _, rest = t.partition("/")
    repo, path = (first, rest) if rest and p.repo(first) else (None, t)
    return {"p": p.name, "repo": repo, "path": path, "prefix": path + "/", "suffix": "/" + path}


def history(target: str, project: str | None = None, show_all: bool = False) -> str:
    """The tickets that planned, built, committed to or cited a file or a directory, newest sprint first."""
    p = _project(project)
    with _session() as s:
        rows = s.run(Q.HISTORY, **_path_args(p, target)).data()
    rows.sort(
        key=lambda r: (max(map(_sprint_order, r["sprints"]), default=()), r["last"] or "", _key_order(r["ticket"])),
        reverse=True,
    )
    for r in rows:
        if {"planned", "built"} & set(r["how"]):
            r["how"] = [h for h in r["how"] if h != "cited"]  # a plan that touches the file cites it too
    lines = [
        f"{r['ticket']:<13} {', '.join(sorted(r['how']))} · {', '.join(sorted(x for x in r['sprints'] if x)) or '-'}"
        f" · {r['files']} files"
        + (f" · last {r['last']}" if r["last"] else "")
        + (f" · {r['docs'][0]}" if r["docs"] else "")
        for r in rows
    ]
    return emit(_head(p), lines, _cmd("history", [target]), show_all)


def who(target: str, project: str | None = None, show_all: bool = False) -> str:
    """Who wrote a file or a directory, from git at the commit the brain read, and the tickets behind it."""
    p = _project(project)
    args = _path_args(p, target)
    with _session() as s:
        hit = s.run(Q.FILE_REPO, **args).data()
        tickets = s.run(Q.HISTORY, **args).data()
    state = indexer.load_state(p)
    repo = args["repo"] or (hit[0]["repo"] if hit else None)
    path = args["path"] if args["repo"] or not hit or hit[0]["path"].startswith(args["prefix"]) else hit[0]["path"]
    r = p.repo(repo) if repo else None
    lines = []
    if r and r.path.exists():
        sha = (state.get("indexed") or {}).get(repo) or files.rev(r.path, r.ref)
        for row in files.git(r.path, "shortlog", "-sn", "--no-merges", sha, "--", path, check=False).splitlines()[:8]:
            n, _, name = row.strip().partition("\t")
            lines.append(f"{'author':<13} {name} · {n} commits")
        log = files.git(r.path, "log", "-6", "--no-merges", "--format=%cs%x09%an%x09%s", sha, "--", path, check=False)
        for row in log.splitlines():
            date, name, subject = (row.split("\t") + ["", ""])[:3]
            lines.append(f"{'commit':<13} {date}  {name}  {_cut(subject, 90)}")
    tickets.sort(key=lambda t: (t["last"] or "", _key_order(t["ticket"])), reverse=True)
    lines += [
        f"{'ticket':<13} {t['ticket']}  {', '.join(sorted(t['how']))} · last {t['last'] or '-'}" for t in tickets[:8]
    ]
    return emit(_head(p), lines, _cmd("who", [target]), show_all)


def related(key: str, project: str | None = None, show_all: bool = False) -> str:
    """Tickets whose plans or commits touched the same files, the rarest shared files counting most."""
    p = _project(project)
    key = key.upper()
    with _session() as s:
        rows = s.run(Q.RELATED, p=p.name, key=key, lim=200).data()
    lines = [
        f"{r['ticket']:<13} {r['shared']} shared · score {r['score']:.2f} · {r['sprint'] or '-'}"
        f" · {', '.join(r['sample'])}"
        for r in rows
    ]
    return emit(_head(p), lines, _cmd("related", [key]), show_all)


def gaps(scope: str | None = None, project: str | None = None, show_all: bool = False) -> str:
    """Open gaps (a gap row whose closing items are not all done) and open action items, for one ticket or a
    sprint (the newest when none is named)."""
    p = _project(project)
    key = scope.upper() if scope and re.match(r"(?i)^[a-z][a-z0-9]+-\d+$", scope) else None
    with _session() as s:
        slug = None if key else scope
        if not key and not slug:
            known = s.run(Q.SPRINTS, p=p.name).data()
            slug = max((r["sprint"] for r in known), key=_sprint_order, default=None)
        rows = s.run(Q.GAPS, p=p.name, sprint=slug, key=key).data()
    rows.sort(key=lambda r: -_key_order(r["ticket"]))
    lines = []
    for r in rows:
        lines += [f"{r['ticket']:<13} gap   {g}" for g in r["gaps"]]
        lines += [f"{r['ticket']:<13} open  {i}" for i in r["items"]]
    return emit(_head(p), lines, _cmd("gaps", [scope or ""]), show_all)


# ---------------------------------------------------------------- state


def status(project: str | None = None, skew: bool = False, show_all: bool = False) -> str:
    p = _project(project)
    state = indexer.load_state(p)
    lines = []
    if skew:
        lines = [
            f"skew          {unit}: {field} — {what}  ({repo}/{path})"
            for repo, path, unit, field, what in state.get("skew", [])
        ]
        return emit(_head(p), lines, _cmd("status", ["--skew"]), show_all)
    with _session() as s:
        counts = {}
        for r in s.run(Q.COUNTS, p=p.name).data():
            for lab in r["labels"]:
                counts[lab] = counts.get(lab, 0) + r["n"]
        edges = s.run(Q.EDGE_COUNT, p=p.name).single()["n"]
    lines.append("graph         " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) + f", edges {edges}")
    langs = sorted((state.get("languages") or {}).items(), key=lambda kv: (-kv[1], kv[0]))
    if langs:
        lines.append("languages     " + ", ".join(f"{k} {v}" for k, v in langs) + " (files parsed)")
    engines, prefix = state.get("engines", []), state.get("strip_prefix", "")
    lines.append(f"engines       {len(engines)}: " + " ".join(output.short(e, prefix) for e in engines))
    lines.append(f"externals     {len(state.get('externals', []))}: " + " ".join(state.get("externals", [])))
    by_unit = {}
    for row in state.get("skew", []):
        by_unit[row[2]] = by_unit.get(row[2], 0) + 1
    lines.append(
        "skew          " + (", ".join(f"{u} {n} fields" for u, n in by_unit.items()) or "none") + " (status --skew)"
    )
    if state.get("parse_errors"):
        lines.append(f"parse         {state['parse_errors']} files parsed with errors (partial facts)")
    for err in state.get("facts_errors", [])[:5]:
        lines.append(f"facts         {err[:120]}")
    for note in state.get("notes", [])[:5]:
        lines.append(f"note          {note[:120]}")
    if indexer.locked():
        lines.append("index         running now")
    return emit(_head(p), lines, _cmd("status", []), show_all)


def ensure_neo4j(wait: float = 90.0) -> str | None:
    """Start the container when Neo4j does not answer, so the brain is up whenever a skill asks.
    None when it was up already, a note when this call started it."""
    try:
        connect().close()
        return None
    except Unreachable:
        pass
    try:
        res = subprocess.run(
            ["docker", "compose", "-f", str(BRAIN / "compose.yaml"), "up", "-d"],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        res = None
    if res is None or res.returncode != 0:
        raise NotRun(
            "Neo4j is down and Docker did not start it: sudo systemctl start docker, then ai-brain/bin/ai-brain-up",
            output.UNREACHABLE,
        )
    started = time.time()
    while time.time() - started < wait:
        try:
            connect().close()
            return f"started Neo4j in {time.time() - started:.0f}s"
        except Unreachable:
            time.sleep(2)
    raise NotRun("Neo4j started but does not answer yet: ai-brain/bin/ai-brain-up --status", output.UNREACHABLE)


def detach(args: list[str], log_name: str) -> None:
    """Run `ai-brain <args>` detached, its output in var/log/<log_name>."""
    log = VAR / "log" / log_name
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "ab") as fh:
        subprocess.Popen(
            [sys.executable, "-m", "ai_brain.cli", *args],
            stdout=fh,
            stderr=fh,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=dict(os.environ),
        )


def fresh(project: str | None = None) -> str:
    """Bring Neo4j up if it is down, then re-index in the background when a repo moved."""
    p = _project(project)
    state = indexer.load_state(p)
    if not state:
        raise NotRun("not indexed yet: ai-brain/bin/ai-brain-up", output.NOT_SET_UP)
    note = ensure_neo4j()
    moved = _stale(p, state)
    head = output.header(state, moved) + (f"\n{note}" if note else "")
    if not moved:
        return head + "\nfresh"
    if indexer.locked():
        return head + "\nindexing"
    detach(["index", "--changed", "--pull", "--project", p.name], "index.log")
    return head + "\nstale, re-indexing in the background (ai-brain/ai-brain/var/log/index.log)"
