"""Project registry, paths and discovery of engines and externals (plan section 6, A5)."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

BRAIN = Path(__file__).resolve().parents[2]
VAR = BRAIN / "var"
PROJECTS = BRAIN / "projects"
ROLES = {"monorepo", "app", "pilet", "shell", "library", "e2e"}


@dataclass
class Repo:
    name: str
    role: str
    ref: str
    path: Path


@dataclass
class Unit:
    """A Component: the monolith app, an engine, a pilet, the shell, a library or the e2e suite."""

    name: str
    repo: str
    prefix: str  # path inside the repo, "" for the whole repo
    kind: str  # app | engine | pilet | shell | library | e2e
    deployable: bool


@dataclass
class External:
    name: str
    remote: str
    revision: str
    tag: str


@dataclass
class Project:
    name: str
    root: Path
    dir: Path
    repos: list[Repo]
    knowledge: list[Repo]
    skip: list[str]
    externals_from: str | None
    rails_app: str | None
    rails_env: str
    extractors: dict[str, str] = field(default_factory=dict)
    ticket_prefix: str | None = None
    strip_prefix: str = ""
    app_names: dict[str, str] = field(default_factory=dict)
    own_hosts: tuple[str, ...] = ()
    snapshots: dict[tuple[str, str], str] = field(default_factory=dict)
    languages: dict[str, list[str]] = field(default_factory=dict)  # [languages] include / exclude
    facts: list[dict] = field(default_factory=list)  # [[facts]]: name, app, command, paths, env
    roots: dict[str, str] = field(default_factory=dict)  # [monorepo] roots: folder -> component kind

    def repo(self, name: str) -> Repo | None:
        return next((r for r in self.repos + self.knowledge if r.name == name), None)


def list_projects() -> list[str]:
    return sorted(p.name for p in PROJECTS.iterdir() if (p / "project.toml").is_file() and p.name != "_template")


def load_project(name: str | None = None, cwd: Path | None = None) -> Project:
    names = list_projects()
    if name is None:
        cwd = (cwd or Path.cwd()).resolve()
        for n in names:
            root = _root(_read(n)).resolve()
            if cwd == root or root in cwd.parents:
                name = n
                break
        name = name or (names[0] if len(names) == 1 else None)
    if name not in names:
        raise SystemExit(f"ai-brain: no project {name!r}; known: {', '.join(names) or 'none'}")
    raw = _read(name)
    root = _root(raw)

    def repo(entry: dict, role_key: str) -> Repo:
        return Repo(entry["name"], entry.get(role_key, ""), entry.get("ref", "main"), root / entry["name"])

    return Project(
        name=name,
        root=root,
        dir=PROJECTS / name,
        repos=[repo(e, "role") for e in raw.get("repos", [])],
        knowledge=[repo(e, "kind") for e in raw.get("knowledge", [])],
        skip=raw.get("skip", {}).get("dirs", []),
        externals_from=raw.get("externals", {}).get("from"),
        rails_app=raw.get("rails", {}).get("app"),
        rails_env=raw.get("rails", {}).get("env", "development"),
        extractors=raw.get("extractors", {}),
        ticket_prefix=raw.get("tickets", {}).get("prefix"),
        strip_prefix=raw.get("names", {}).get("strip_prefix", ""),
        app_names=raw.get("names", {}).get("apps", {}),
        own_hosts=tuple(raw.get("http", {}).get("own_hosts", [])),
        snapshots={(s["repo"], s["path"]): s["engine"] for s in raw.get("graphql", {}).get("snapshots", [])},
        languages=raw.get("languages", {}),
        facts=raw.get("facts", []),
        roots=raw.get("monorepo", {}).get("roots", {}),
    )


def _root(raw: dict) -> Path:
    """The workspace root; a relative one is read from the ai-brain checkout, so `..` is the folder it sits in."""
    root = Path(raw["project"]["root"]).expanduser()
    return root if root.is_absolute() else (BRAIN.parent / root).resolve()


def _read(name: str) -> dict:
    with open(PROJECTS / name / "project.toml", "rb") as fh:
        return tomllib.load(fh)


def load_env() -> dict[str, str]:
    env = {}
    path = BRAIN / ".env"
    if path.is_file():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()
    return env


MANIFESTS = {
    "pyproject.toml",
    "setup.py",
    "mix.exs",
    "Cargo.toml",
    "go.mod",
    "package.json",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
}
ROOTS = {"packages": "package", "libs": "package", "crates": "package", "services": "service", "cmd": "service"}
DEPLOYABLE = {"app", "pilet", "shell", "service"}


def units(project: Project, ls: dict[str, list[str]]) -> list[Unit]:
    """Components from the registry and the tracked trees; engines come from gems/*, never a list. In a monorepo, a
    subfolder of packages/, services/, libs/, crates/, cmd/ or a [monorepo] root that holds a manifest is one too."""
    out: list[Unit] = []
    for r in project.repos:
        files = ls.get(r.name, [])
        if r.role == "monorepo":
            for app in sorted({p.split("/")[1] for p in files if p.startswith("apps/") and p.count("/") > 1}):
                out.append(Unit(project.app_names.get(app, app), r.name, f"apps/{app}/", "app", True))
            gemspecs = sorted({p.split("/")[1] for p in files if re.match(r"gems/[^/]+/[^/]+\.gemspec$", p)})
            for gem in gemspecs:
                out.append(Unit(gem, r.name, f"gems/{gem}/", "engine", False))
            present = set(files)
            for root, kind in {**ROOTS, **project.roots}.items():
                found = {p.split("/")[1] for p in files if p.count("/") == 2 and p.startswith(root + "/")}
                for folder in sorted(d for d in found if any(f"{root}/{d}/{m}" in present for m in MANIFESTS)):
                    taken = {u.name for u in out}
                    name = folder if folder not in taken else f"{root}-{folder}"  # crates/core beside packages/core
                    out.append(Unit(name, r.name, f"{root}/{folder}/", kind, kind in DEPLOYABLE))
        elif r.role in {"pilet", "shell", "app"}:
            out.append(Unit(r.name, r.name, "", r.role, True))
        else:
            out.append(Unit(r.name, r.name, "", r.role, False))
    return out


def externals(project: Project, lockfile_text: str | None) -> list[External]:
    """GIT sources in the lockfile whose repo is not cloned here."""
    if not lockfile_text:
        return []
    cloned = {r.name for r in project.repos}
    out = []
    for block in re.split(r"\n(?=GIT\n)", lockfile_text):
        if not block.startswith("GIT\n"):
            continue
        remote = _field(block, "remote")
        name = remote.rstrip("/").split("/")[-1].removesuffix(".git")
        if name not in cloned:
            out.append(External(name, remote, _field(block, "revision"), _field(block, "tag")))
    return sorted(out, key=lambda e: e.name)


def git_pin(lockfile_text: str | None, repo_name: str) -> tuple[str, str] | None:
    """(revision, tag) the lockfile pins a cloned GIT source to, e.g. a shared library repo."""
    for block in re.split(r"\n(?=GIT\n)", lockfile_text or ""):
        if block.startswith("GIT\n") and _field(block, "remote").rstrip("/").removesuffix(".git").endswith(
            "/" + repo_name
        ):
            return _field(block, "revision"), _field(block, "tag")
    return None


def _field(block: str, key: str) -> str:
    m = re.search(rf"^\s+{key}: (\S+)", block, re.M)
    return m.group(1) if m else ""
