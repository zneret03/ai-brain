"""Plans, dev reports, hunt reports and bugs: each ticket's sprint, status, open gaps and items, the files its plan
says to touch (PLANS) and the files its dev report changed (CHANGED). Home is the sprints repo's sprints/, gitignored
and read from disk; a plans repo is the archive of earlier sprints (A10, decisions 19 and 22)."""

from __future__ import annotations

import re
import time

import yaml

from ..extract import files
from . import Ctx
from .notes import CITE, _note_node, _resolve, _suffix_index

SPRINT = re.compile(r"(?:^|/)sprints/([^/]+)/")
ROW_ID = re.compile(r"\b([BFCDS]\d+[a-z]?)\b")
PR = re.compile(r"github\.com/[\w.-]+/([\w.-]+)/pull/(\d+)|\b([\w-]+)#(\d+)\b")  # a URL, or repo#12 for a known repo
TOKEN = re.compile(r"`([^`\n]+)`")
PATH = re.compile(r"^([\w@./-]*\w\.\w+)(?::(\d+)(?:[-–]\d+)?)?$")
GAP = {"gap", "blocked", "unknown", "partial", "missing"}
ARCHIVE_DIRS = ("sprints/", "reports/", "reviews/", "bugs/")
CAP_LIST, CAP_TEXT = 30, 400


def link(ctx: Ctx) -> None:
    index = _suffix_index(ctx)
    home: set[tuple[str | None, str]] = set()
    for k in sorted(ctx.project.knowledge, key=lambda r: r.role != "sprints"):
        if k.name not in ctx.shas or k.role not in ("sprints", "plans"):
            continue
        docs = _home_docs(k, ctx.shas[k.name]) if k.role == "sprints" else _archive_docs(k)
        for path, (text, date) in sorted(docs.items()):
            where = (_sprint(path), path.rsplit("/", 1)[-1])
            if k.role == "sprints":
                home.add(where)
            elif where in home:
                continue  # imported into the home repo, whose copy is the one kept current
            _doc(ctx, k.name, path, text, date, index)


def _home_docs(k, sha: str) -> dict[str, tuple[str, str | None]]:
    """The harness's docs/ at main, local or origin, whichever is ahead; docs/ waits for its merge. sprints/ from disk:
    it is gitignored, each dev's own, so /dev reads what /plan wrote minutes ago on any branch (sprints/README.md)."""
    listing = [
        (p, b)
        for p, b, size in files.ls_tree(k.path, sha)
        if p.startswith("docs/") and p.endswith(".md") and size < 2_000_000
    ]
    blobs = files.read_blobs(k.path, [b for _, b in listing])
    docs = {p: (blobs.get(b, b"").decode("utf-8", "replace"), None) for p, b in listing}
    for f in (k.path / "sprints").rglob("*.md"):
        if f.is_file():
            day = time.strftime("%Y-%m-%d", time.localtime(f.stat().st_mtime))
            docs[f.relative_to(k.path).as_posix()] = (f.read_text("utf-8", "replace"), day)
    return docs


def _archive_docs(k) -> dict[str, tuple[str, str | None]]:
    """Plans stay on their ticket branches, often unmerged and sometimes never pushed, so every branch head is read,
    newest commit first; the first branch that holds a path wins. Never the working tree (decision 19)."""
    refs = files.git(
        k.path,
        "for-each-ref",
        "--sort=-committerdate",
        "--format=%(refname) %(committerdate:short)",
        "refs/heads",
        "refs/remotes/origin",
    ).splitlines()
    seen: dict[str, tuple[str, str]] = {}
    for line in refs:
        ref, _, date = line.partition(" ")
        if ref.endswith("/HEAD"):
            continue
        for path, blob, size in files.ls_tree(k.path, ref):
            if path.endswith(".md") and path.startswith(ARCHIVE_DIRS) and size < 2_000_000 and path not in seen:
                seen[path] = (blob, date)
    blobs = files.read_blobs(k.path, [b for b, _ in seen.values()])
    return {p: (blobs.get(b, b"").decode("utf-8", "replace"), d) for p, (b, d) in seen.items()}


def _doc(ctx: Ctx, repo: str, path: str, text: str, date: str | None, index) -> None:
    name = path.rsplit("/", 1)[-1]
    if name == "README.md" and "/tickets/" in path:
        name = path.rsplit("/", 2)[-2]  # the archive's tickets/<KEY or NEW-slug>/README.md
    kind = _kind(path)
    front = _front(text)
    title = front.get("title") or next((ln[2:].strip() for ln in text.splitlines() if ln.startswith("# ")), None)
    key = _key(path, front, title, ctx.project.ticket_prefix)
    cites: dict[tuple[str, str], str | None] = {}
    for m in CITE.finditer(text):
        hit = _resolve(ctx, m.group(1), index)
        if hit:
            cites.setdefault(hit, m.group(2))
    if not key and not cites and kind != "plan":
        return
    sections = _sections(text)
    items = _items(sections.get("action items", ""))
    rows = _parity(sections.get("parity analysis", ""))
    report = _subsections(sections.get("dev report", ""))
    meta = _header(text.split("\n## ", 1)[0])
    touch, planned_new = _touch(ctx, sections.get("files to touch", ""), items, index)
    nid = _note_node(
        ctx,
        repo,
        path,
        kind=kind,
        name=name,
        title=title,
        ticket=key,
        sprint=_sprint(path),
        parent=meta.get("parent") or front.get("parent"),
        jira_type=meta.get("type"),
        jira_status=meta.get("status"),
        owner=meta.get("owner"),
        status=str(front["status"]) if front.get("status") else None,
        updated=date,
        branches=meta.get("branches", [])[:CAP_LIST],
        prs=sorted(_prs(text, {r.name for r in ctx.project.repos + ctx.project.knowledge}))[:CAP_LIST],
        items_total=len(items),
        items_done=sum(_done(i["status"]) for i in items),
        open_items=[
            _cut(f"{i['id']} {i['action']} ({i['status'] or 'todo'})", 140) for i in items if not _done(i["status"])
        ][:CAP_LIST],
        gaps_total=sum(1 for r in rows if r["verdict"].split()[:1] and r["verdict"].split()[0] in GAP),
        gaps_open=[_cut(f"{r['id']} {r['area']} ({r['verdict']})", 140) for r in rows if _open_gap(r, items)][
            :CAP_LIST
        ],
        planned_new=planned_new[:CAP_LIST],
        tldr=_cut(_first_para(sections.get("tldr", "")), CAP_TEXT),
        summary=_cut(
            _first_para(report.get("summary") or report.get("", "")) or str(front.get("summary") or ""), CAP_TEXT
        ),
        built=bool(report),
    )
    for (hit_repo, hit_path), line in cites.items():
        ctx.g.edge("CITES", nid, ctx.g.file_id(hit_repo, hit_path), status="ok", line=int(line) if line else None)
    for (hit_repo, hit_path), props in touch.items():
        ctx.g.edge("PLANS", nid, ctx.g.file_id(hit_repo, hit_path), **props)
    for (hit_repo, hit_path), props in _rows_to_files(ctx, report.get("files changed", ""), index)[0].items():
        ctx.g.edge("CHANGED", nid, ctx.g.file_id(hit_repo, hit_path), **props)
    if key:
        ctx.g.edge("CITES", nid, ctx.g.node(f"{ctx.project.name}:ticket:{key}", "Ticket", name=key))


def _touch(ctx: Ctx, body: str, items: list[dict], index) -> tuple[dict, list[str]]:
    """The Files to touch table, then each action item's Repo + files cell, which plans before the table had."""
    out, unresolved = _rows_to_files(ctx, body, index)
    for i in items:
        for cited, line in _paths(i["files"]):
            hit = _resolve(ctx, cited, index)
            if not hit:
                continue
            cur = out.setdefault(hit, {"line": line, "change": None, "item": None})
            cur["item"] = ", ".join(dict.fromkeys(x for x in [*(cur["item"] or "").split(", "), i["id"]] if x))
            if i["side"] and not cur.get("side"):
                cur["side"] = i["side"]
    return out, unresolved


def _rows_to_files(ctx: Ctx, body: str, index) -> tuple[dict, list[str]]:
    """{(repo, path): {line, change, item}} for a table with a File column; the cells naming no file in the graph
    (a file still to be added) come back as text."""
    out: dict[tuple[str, str], dict] = {}
    unresolved: list[str] = []
    for table in _tables(body):
        for r in table:
            cell = next((v for k, v in r.items() if k in ("file", "files", "path")), None)
            if cell is None:
                continue
            change = _plain(r.get("change", "")).lower() or None
            item = _plain(r.get("items") or r.get("item") or "") or None
            hits = [(h, line) for cited, line in _paths(cell) if (h := _resolve(ctx, cited, index))]
            for hit, line in hits:
                out.setdefault(hit, {"line": line, "change": change, "item": item})
            if not hits and _plain(cell):
                unresolved.append(_cut(f"{_plain(cell)}{' (' + change + ')' if change else ''}", 160))
    return out, unresolved


def _paths(cell: str) -> list[tuple[str, int | None]]:
    """File paths in a table cell: backticked tokens (`E app/x.rb:12` keeps the part after a short repo tag) and
    bare paths the citation pattern knows."""
    found: dict[str, int | None] = {}
    for tok in TOKEN.findall(cell):
        parts = tok.split()
        if len(parts) == 2 and parts[0].isupper() and len(parts[0]) <= 4:
            parts = parts[1:]
        m = PATH.match(parts[0]) if len(parts) == 1 else None
        if m:
            found.setdefault(m.group(1).lstrip("./"), int(m.group(2)) if m.group(2) else None)
    for m in CITE.finditer(cell):
        found.setdefault(m.group(1), int(m.group(2)) if m.group(2) else None)
    return list(found.items())


def _items(body: str) -> list[dict]:
    items = []
    for table in _tables(body):
        for r in table:
            if "#" not in r or "action" not in r:
                continue
            items.append(
                {
                    "id": _plain(r["#"]),
                    "side": _plain(r.get("side", "")),
                    "action": _cut(_plain(r["action"]), 110),
                    "files": next((v for k, v in r.items() if "file" in k), ""),
                    "closes": ROW_ID.findall(r.get("closes", "")),
                    "status": _plain(r.get("status", "")).lower(),
                }
            )
    return items


def _parity(body: str) -> list[dict]:
    return [
        {"id": _plain(r["#"]), "area": _cut(_plain(r.get("area", "")), 80), "verdict": _plain(r["verdict"]).lower()}
        for table in _tables(body)
        for r in table
        if "#" in r and "verdict" in r
    ]


def _done(status: str) -> bool:
    return status.startswith(("done", "descoped", "merged", "shipped")) or "✅" in status


def _open_gap(row: dict, items: list[dict]) -> bool:
    if row["verdict"].split()[:1] == [] or row["verdict"].split()[0] not in GAP:
        return False
    closers = [i for i in items if row["id"] in i["closes"]]
    return not closers or not all(_done(i["status"]) for i in closers)


def _header(head: str) -> dict:
    meta: dict = {}
    m = re.search(r"\*\*Ticket:\*\*\s*\[?[A-Z][A-Z0-9]*-\d+\]?(?:\([^)]*\))?\s*·([^·\n]*)·([^·\n]*)·([^·\n]*)", head)
    if m:
        meta["type"], meta["status"], meta["owner"] = (_plain(x) or None for x in m.groups())
    m = re.search(r"\*\*Parent:\*\*\s*\[?([A-Z][A-Z0-9]*-\d+)", head)
    if m:
        meta["parent"] = m.group(1)
    meta["branches"] = [
        f"{_plain(r.get('repo', ''))} {b}"
        for table in _tables(head)
        for r in table
        if "branch" in r
        for b in re.findall(r"`([^`\s]*/[^`\s]*)`", r["branch"])[:1]
    ]
    return meta


def _sections(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    cur, buf = None, []
    for ln in text.splitlines() + ["## "]:
        if ln.startswith("## "):
            if cur is not None:
                out.setdefault(cur, "\n".join(buf))
            cur, buf = ln[3:].strip().lower(), []
        elif cur is not None:
            buf.append(ln)
    return out


def _subsections(body: str) -> dict[str, str]:
    if not body.strip():
        return {}
    out: dict[str, str] = {}
    cur, buf = "", []  # text before the first ### stands in for a missing Summary
    for ln in body.splitlines() + ["### "]:
        if ln.startswith("### "):
            if buf and "\n".join(buf).strip():
                out.setdefault(cur, "\n".join(buf))
            cur, buf = ln[4:].strip().lower(), []
        else:
            buf.append(ln)
    return out


def _tables(body: str) -> list[list[dict[str, str]]]:
    """Each markdown table as rows of {lowercased header: raw cell}."""
    tables, header, rows = [], None, []
    for ln in body.splitlines() + [""]:
        s = ln.strip()
        if s.startswith("|") and s.endswith("|") and len(s) > 1:
            cells = [c.strip() for c in re.split(r"(?<!\\)\|", s[1:-1])]
            if header is None:
                header = [_plain(c).lower() for c in cells]
            elif not all(set(c) <= set("-: ") for c in cells):
                rows.append(dict(zip(header, cells, strict=False)))  # a short row leaves cells out
        elif header is not None:
            tables.append(rows)
            header, rows = None, []
    return tables


def _front(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}
    return meta if isinstance(meta, dict) else {}


def _key(path: str, front: dict, title: str | None, prefix: str | None) -> str | None:
    if not prefix:
        return None
    key = re.compile(rf"\b({re.escape(prefix)}-\d+)\b")
    for src in (path.rsplit("/", 1)[-1], str(front.get("ticket") or front.get("key") or ""), title or "", path):
        m = key.search(src)
        if m:
            return m.group(1)
    return None


def _kind(path: str) -> str:
    for part, kind in (
        ("/plan/", "plan"),
        ("/tickets/", "plan"),
        ("/reports/", "report"),
        ("/bugs/", "bug"),
        ("/reviews/", "review"),
    ):
        if part in "/" + path:
            return kind
    return "doc"


def _sprint(path: str) -> str | None:
    m = SPRINT.search(path)
    return m.group(1) if m else None


def _prs(text: str, repos: set[str]) -> set[str]:
    return {f"{a}#{b}" if a else f"{c}#{d}" for a, b, c, d in PR.findall(text) if a or c in repos}


def _first_para(body: str) -> str:
    para = []
    for ln in body.strip().splitlines():
        if not ln.strip():
            if para:
                break
            continue
        if ln.lstrip().startswith(("|", "#")):
            if para:
                break
            continue
        para.append(ln.strip().lstrip("-* ").strip())
    return _plain(" ".join(para))


def _plain(s: str) -> str:
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s or "")
    return s.replace("**", "").replace("`", "").strip()


def _cut(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"
