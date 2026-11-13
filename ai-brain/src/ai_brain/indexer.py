"""index: fetch, read each repo at origin/<ref>, boot Rails when a fact-bearing path moved, link, write the delta
to Neo4j, render the cards (A6 to A11, A16). One index at a time, under var/index.lock."""

from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from . import config
from .config import VAR, Project
from .extract import corpus, files, languages
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


def facts_specs(project: Project) -> list[dict]:
    """The facts commands: the Rails boot when [rails] names an app, then each [[facts]] entry (docs/AI_BRAIN.md)."""
    specs = []
    if project.rails_app:
        specs.append(
            {"name": "rails", "app": project.rails_app, "paths": BOOT_PATHS, "env": {"RAILS_ENV": project.rails_env}}
        )
    for entry in project.facts:
        paths = re.compile("|".join(f"(?:{p})" for p in entry["paths"])) if entry.get("paths") else None
        specs.append({**entry, "paths": paths, "env": entry.get("env", {})})
    return specs


def _command(project: Project, spec: dict, out: Path) -> list[str]:
    if "command" not in spec:  # the Rails boot
        app = project.root.expanduser() / spec["app"]
        ruby = (app / ".ruby-version").read_text().strip() if (app / ".ruby-version").exists() else "ruby"
        script = project.dir / "extractors" / "rails_introspect.rb"
        return ["mise", "exec", f"ruby@{ruby}", "--", "bin/rails", "runner", str(script), str(out)]
    subs = {"{out}": str(out), "{project}": str(project.dir), "{root}": str(project.root.expanduser())}
    return [re.sub(r"\{(?:out|project|root)\}", lambda m: subs[m.group(0)], arg) for arg in spec["command"]]


def boot(project: Project, log, specs: list[dict] | None = None) -> bool:
    """Run each facts command (every one by default) in its app's folder. One that fails keeps its previous facts.
    True when any wrote new facts."""
    out_dir = project.dir / "facts"
    out_dir.mkdir(parents=True, exist_ok=True)
    wrote = False
    for spec in facts_specs(project) if specs is None else specs:
        name, app = spec["name"], project.root.expanduser() / spec["app"]
        tmp = out_dir / f"{name}.jsonl.tmp"
        logfile = "boot.log" if name == "rails" else f"facts-{name}.log"
        log(
            f"booting {spec['app']} (RAILS_ENV={spec['env']['RAILS_ENV']}) for the facts"
            if "command" not in spec
            else f"facts {name}: running in {spec['app']}"
        )
        try:
            env = dict(os.environ, **spec["env"])
            res = subprocess.run(
                _command(project, spec, tmp), cwd=app, env=env, capture_output=True, text=True, timeout=900
            )
            failed, output = res.returncode != 0 or not tmp.exists(), res.stdout[-20000:] + "\n" + res.stderr[-20000:]
        except (OSError, subprocess.TimeoutExpired) as exc:  # a command that is not there, or never returns
            failed, output = True, f"{type(exc).__name__}: {exc}"
        if failed:
            (VAR / "log").mkdir(parents=True, exist_ok=True)
            (VAR / "log" / logfile).write_text(output)
            what = "boot" if name == "rails" else f"facts {name}"
            log(f"{what} failed; keeping the previous facts (var/log/{logfile})")
            continue
        tmp.replace(out_dir / f"{name}.jsonl")
        repo_root = app
        while not (repo_root / ".git").exists() and repo_root != repo_root.parent:
            repo_root = repo_root.parent
        sha = files.git(repo_root, "rev-parse", "HEAD").strip()
        (out_dir / f"{name}.meta.json").write_text(json.dumps({"sha": sha, "at": int(time.time())}))
        wrote = True
    return wrote


def load_facts(project: Project) -> tuple[dict[str, list[dict]], dict]:
    """Every facts file's rows by type, and for the header the Rails boot's meta, else the first command's; `all`
    holds each command's."""
    facts: dict[str, list[dict]] = {}
    metas: dict[str, dict] = {}
    for path in sorted((project.dir / "facts").glob("*.jsonl")):
        for line in path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                facts.setdefault(row["t"], []).append(row)
        meta_path = path.with_name(f"{path.stem}.meta.json")
        if meta_path.exists():
            metas[path.stem] = json.loads(meta_path.read_text())
    meta = metas.get("rails") or next(iter(metas.values()), {})
    return facts, {**meta, "all": metas} if metas else {}


def needs_run(project: Project, spec: dict, mode: str) -> bool:
    """A facts command runs on a full index, when it never ran, and when its repo moved a path it reads: one its
    `paths` match, or any under its app's folder."""
    meta_path = project.dir / "facts" / f"{spec['name']}.meta.json"
    if mode == "full" or not meta_path.exists():
        return True
    sha = json.loads(meta_path.read_text()).get("sha")
    repo_name, _, inside = spec["app"].partition("/")
    repo = project.repo(repo_name)
    if repo is None:
        return False
    head = files.git(repo.path, "rev-parse", "HEAD").strip()
    if head == sha:
        return False
    changed = files.diff_names(repo.path, sha, head) if sha else ["db/"]
    if spec["paths"] is None:
        prefix = inside.rstrip("/") + "/" if inside else ""
        return any(p.startswith(prefix) for p in changed)
    return any(spec["paths"].search(p) for p in changed)


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
    languages.configure(*languages.project_settings(project))
    parsed, listing = {}, {}
    for repo in project.repos:
        if repo.name in shas:
            parsed[repo.name], listing[repo.name] = corpus.parse_tree(repo.path, shas[repo.name])
    for repo in project.knowledge:
        if repo.name in shas:
            listing[repo.name] = files.ls_tree(repo.path, shas[repo.name])
    log(f"parsed {sum(len(v) for v in parsed.values())} files in {time.time() - t0:.0f}s")
    facts, facts_meta = load_facts(project)
    due = [
        s
        for s in facts_specs(project)
        if boot_mode == "always" or (boot_mode == "auto" and needs_run(project, s, mode))
    ]
    if due and boot(project, log, due):
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
    ctx.notes.extend(languages.notes())
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
        "languages": dict(Counter(f.get("lang") or "?" for files_ in parsed.values() for f in files_.values())),
        "facts_sha": facts_meta.get("sha"),
        "facts_at": facts_meta.get("at"),
        "facts_errors": (facts.get("meta") or [{}])[0].get("errors", []),
        "facts": {name: m.get("sha") for name, m in facts_meta.get("all", {}).items()},
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
