"""Shared state the linkers read and write. Each linker module owns one join key (plan section 4)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Project, Unit
from ..extract import files
from ..model import Graph


@dataclass
class Ctx:
    project: Project
    g: Graph
    shas: dict[str, str]
    parsed: dict[str, dict[str, dict]]
    listing: dict[str, list[tuple[str, str, int]]]
    units: list[Unit]
    facts: dict[str, list[dict]]
    lock: str | None
    notes: list[str] = field(default_factory=list)  # coverage notes for the header and doctor
    # indexes the code linker fills for the others
    sym: dict[tuple[str, str, str], str] = field(default_factory=dict)  # (repo, path, qual) -> id
    ruby_defs: dict[str, list[tuple[str, str, str]]] = field(default_factory=lambda: defaultdict(list))
    known_cpaths: set[str] = field(default_factory=set)
    const_owner: dict[str, list[str]] = field(default_factory=dict)  # value constant -> classes assigning it
    exports: dict[tuple[str, str], dict[str, str]] = field(default_factory=dict)  # (repo, path) -> name -> id
    imports: dict[tuple[str, str], dict[str, tuple[str, str, str]]] = field(default_factory=dict)

    def unit(self, repo: str, path: str) -> Unit | None:
        best = None
        for u in self.units:
            if u.repo == repo and path.startswith(u.prefix) and (best is None or len(u.prefix) > len(best.prefix)):
                best = u
        return best

    def rel(self, abspath: str | None) -> tuple[str, str] | None:
        """(repo, path) for an absolute path inside the workspace root."""
        if not abspath:
            return None
        root = str(self.project.root.expanduser().resolve()) + "/"
        if not abspath.startswith(root):
            return None
        repo, _, path = abspath[len(root) :].partition("/")
        return (repo, path) if repo in self.parsed else None

    def text(self, repo: str, path: str) -> str | None:
        repo_obj = self.project.repo(repo)
        if repo_obj is None or repo not in self.shas:
            return None
        return files.show(repo_obj.path, self.shas[repo], path)

    def paths(self, repo: str) -> set[str]:
        return {p for p, _, _ in self.listing.get(repo, [])}

    def owner_id(self, repo: str, path: str, qual: str) -> str:
        """The symbol a fact belongs to, or the file when the fact sits at the top level."""
        return self.sym.get((repo, path, qual)) or self.g.file_id(repo, path)


def repo_path(project: Project, name: str) -> Path:
    repo = project.repo(name)
    return repo.path if repo else project.root / name
