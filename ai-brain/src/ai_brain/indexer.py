"""index: fetch, read each repo at origin/<ref>, boot Rails when a fact-bearing path moved, link, write the delta
to Neo4j, render the cards (A6 to A11, A16). One index at a time, under var/index.lock."""

from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

from . import config
from .config import VAR, Project
from .extract import corpus, files
from .link import Ctx
from .model import Graph

LINKERS = (
    "code",
    "graphql",
    "mounts",
    "http",
    "frontend",
    "data",
    "kafka",
    "jobs",
    "auth",
    "packages",
    "notes",
    "plans",
    "tests",
    "tickets",
    "talks",
)
BOOT_PATHS = re.compile(
    r"(^|/)(config/routes|config/karafka\.rb|karafka\.rb|app/graphql/|app/models/|app/policies/|app/jobs/|app/workers/"
    r"|app/sidekiq/|app/channels/|app/kafka/|db/|Gemfile\.lock|config/sidekiq_recurring_jobs|config/engine_initializers/)"
)


class Busy(Exception):
    pass


@contextmanager
def lock():
    path = VAR / "index.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        fh.close()
        raise Busy() from exc
    try:
        fh.write(str(os.getpid()))
        fh.flush()
        yield
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def locked() -> bool:
    try:
        with lock():
            return False
    except Busy:
        return True


def state_path(project: Project) -> Path:
    return VAR / "state" / f"{project.name}.json"


def load_state(project: Project) -> dict:
    try:
        return json.loads(state_path(project).read_text())
    except (OSError, ValueError):
        return {}


def save_state(project: Project, state: dict) -> None:
    path = state_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True))
    tmp.replace(path)


def target_shas(project: Project, lock_text: str | None) -> dict[str, str]:
    """The commit each repo is read at: origin/<ref>, the lockfile pin for a library the monolith pins, or for the
    sprints repo whichever of main and origin/main is ahead."""
    shas = {}
    for repo in project.repos + project.knowledge:
        if not repo.path.exists() or files.is_worktree(repo.path) or repo.name in project.skip:
            continue
        pin = config.git_pin(lock_text, repo.name) if repo.role == "library" else None
        if pin and files.git(repo.path, "cat-file", "-t", pin[0], check=False).strip() == "commit":
            shas[repo.name] = pin[0]
        elif repo.role == "sprints":
            shas[repo.name] = files.newest_rev(repo.path, repo.ref)
        else:
            shas[repo.name] = files.rev(repo.path, repo.ref)
    return shas


def lockfile(project: Project) -> str | None:
    if not project.externals_from:
        return None
    repo, _, path = project.externals_from.partition("/")
    r = project.repo(repo)
    return files.show(r.path, files.rev(r.path, r.ref), path) if r else None


def boot(project: Project, log) -> bool:
    """Run the Rails introspection against the monolith checkout. False keeps the previous facts."""
    if not project.rails_app:
        return False
    app = project.root.expanduser() / project.rails_app
    script = project.dir / "extractors" / "rails_introspect.rb"
    out_dir = project.dir / "facts"
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / "rails.jsonl.tmp"
    ruby = (app / ".ruby-version").read_text().strip() if (app / ".ruby-version").exists() else "ruby"
    env = dict(os.environ, RAILS_ENV=project.rails_env)
    cmd = ["mise", "exec", f"ruby@{ruby}", "--", "bin/rails", "runner", str(script), str(tmp)]
    log(f"booting {project.rails_app} (RAILS_ENV={project.rails_env}) for the facts")
    res = subprocess.run(cmd, cwd=app, env=env, capture_output=True, text=True, timeout=900)
    if res.returncode != 0 or not tmp.exists():
        (VAR / "log").mkdir(parents=True, exist_ok=True)
        (VAR / "log" / "boot.log").write_text(res.stdout[-20000:] + "\n" + res.stderr[-20000:])
        log("boot failed; keeping the previous facts (var/log/boot.log)")
        return False
    tmp.replace(out_dir / "rails.jsonl")
    repo_root = app
    while not (repo_root / ".git").exists() and repo_root != repo_root.parent:
        repo_root = repo_root.parent
    sha = files.git(repo_root, "rev-parse", "HEAD").strip()
    (out_dir / "rails.meta.json").write_text(json.dumps({"sha": sha, "at": int(time.time())}))
    return True


def load_facts(project: Project) -> tuple[dict[str, list[dict]], dict]:
    facts: dict[str, list[dict]] = {}
    path = project.dir / "facts" / "rails.jsonl"
    if path.exists():
        for line in path.read_text().splitlines():
            row = json.loads(line)
            facts.setdefault(row["t"], []).append(row)
    meta_path = project.dir / "facts" / "rails.meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    return facts, meta


def needs_boot(project: Project, mode: str, facts_meta: dict) -> bool:
    if mode == "full" or not facts_meta:
        return True
    app_repo = project.repo(project.rails_app.split("/")[0]) if project.rails_app else None
    if app_repo is None:
        return False
    head = files.git(app_repo.path, "rev-parse", "HEAD").strip()
    if head == facts_meta.get("sha"):
        return False
    changed = files.diff_names(app_repo.path, facts_meta["sha"], head) if facts_meta.get("sha") else ["db/"]
    return any(BOOT_PATHS.search(p) for p in changed)


def build(
    project: Project, mode: str = "changed", fetch: bool = True, boot_mode: str = "auto", log=print, pull: bool = False
):
    """(graph, meta) for the project. mode: changed | full."""
    t0 = time.time()
    if fetch:
        for repo in project.repos + project.knowledge:
            if repo.path.exists() and not files.is_worktree(repo.path):
                files.fetch(repo.path, repo.ref)
    if pull:
        for repo in project.repos + project.knowledge:
            if repo.path.exists() and not files.is_worktree(repo.path):
                log(f"pull {repo.name}: {files.pull_ff(repo.path, repo.ref)}")
    lock_text = lockfile(project)
    if fetch and lock_text:
        for repo in project.repos:
            pin = config.git_pin(lock_text, repo.name)
            if pin and pin[1]:
                subprocess.run(
                    ["git", "-C", str(repo.path), "fetch", "--quiet", "origin", "tag", pin[1]],
                    capture_output=True,
                    timeout=180,
                )
    shas = target_shas(project, lock_text)
    parsed, listing = {}, {}
    for repo in project.repos:
        if repo.name in shas:
            parsed[repo.name], listing[repo.name] = corpus.parse_tree(repo.path, shas[repo.name])
    for repo in project.knowledge:
        if repo.name in shas:
            listing[repo.name] = files.ls_tree(repo.path, shas[repo.name])
    log(f"parsed {sum(len(v) for v in parsed.values())} files in {time.time() - t0:.0f}s")
    facts, facts_meta = load_facts(project)
    if boot_mode == "always" or (boot_mode == "auto" and needs_boot(project, mode, facts_meta)):
        if boot(project, log):
            facts, facts_meta = load_facts(project)
    g = Graph(project.name)
    ls = {r: [p for p, _, _ in rows] for r, rows in listing.items()}
    ctx = Ctx(
        project=project,
        g=g,
        shas=shas,
        parsed=parsed,
        listing=listing,
        units=config.units(project, ls),
        facts=facts,
        lock=lock_text,
    )
    import importlib

    for name in LINKERS:
        t = time.time()
        importlib.import_module(f"ai_brain.link.{name}").link(ctx)
        log(f"  link {name}: {time.time() - t:.1f}s")
    wanted = sum(1 for repo, rows in listing.items() if repo in parsed for p, _, s in rows if files.wanted(p, s))
    ok = sum(1 for files_ in parsed.values() for f in files_.values() if not f.get("fatal"))
    errors = sum(1 for files_ in parsed.values() for f in files_.values() if f.get("error"))
    meta = {
        "project": project.name,
        "indexed": shas,
        "refs": {r.name: r.ref for r in project.repos + project.knowledge},
        "strip_prefix": project.strip_prefix,
        "coverage": round(100.0 * ok / wanted, 1) if wanted else 0.0,
        "parse_errors": errors,
        "facts_sha": facts_meta.get("sha"),
        "facts_at": facts_meta.get("at"),
        "facts_errors": (facts.get("meta") or [{}])[0].get("errors", []),
        "notes": ctx.notes,
        "skew": [list(r) for r in getattr(ctx, "skew", [])],
        "units": [u.name for u in ctx.units],
        "engines": [u.name for u in ctx.units if u.kind == "engine"],
        "externals": [e.name for e in config.externals(project, lock_text)],
        "nodes": len(g.nodes),
        "edges": len(g.edges),
        "seconds": round(time.time() - t0, 1),
        "at": int(time.time()),
    }
    return g, meta, ctx
