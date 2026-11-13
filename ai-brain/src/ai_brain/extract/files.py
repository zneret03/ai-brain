"""Git access: every read is at origin/<ref> through git objects, never the working tree (decision 13)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from . import languages

SKIP_PARTS = ("node_modules/", "vendor/", "/public/", "db/migrate/", "/tmp/", "coverage/", "dist/", "build/")
SKIP_SUFFIX = (".min.js", ".d.ts")
MAX_BYTES = 1_000_000


def git(repo: Path, *args: str, check: bool = True) -> str:
    res = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {repo}: {res.stderr.strip()}")
    return res.stdout


def is_worktree(path: Path) -> bool:
    return (path / ".git").is_file()


def fetch(repo: Path, ref: str) -> bool:
    res = subprocess.run(
        ["git", "-C", str(repo), "fetch", "--quiet", "origin", ref], capture_output=True, text=True, timeout=180
    )
    return res.returncode == 0


def pull_ff(repo: Path, ref: str) -> str:
    """Fast-forward a clean checkout that sits on its base branch to origin/<ref>. Any other checkout is left as
    it is: a ticket branch or uncommitted work is never switched, stashed or merged into."""
    branch = git(repo, "symbolic-ref", "--short", "-q", "HEAD", check=False).strip()
    if branch != ref:
        return f"skipped: on {branch or 'a detached HEAD'}, not {ref}"
    if git(repo, "status", "--porcelain", "--untracked-files=no", check=False).strip():
        return "skipped: uncommitted changes"
    before = git(repo, "rev-parse", "HEAD").strip()
    res = subprocess.run(["git", "-C", str(repo), "merge", "--ff-only", "-q", f"origin/{ref}"], capture_output=True)
    if res.returncode != 0:
        return "skipped: not a fast-forward"
    after = git(repo, "rev-parse", "HEAD").strip()
    return "up to date" if before == after else f"pulled {before[:7]}..{after[:7]}"


def fetch_age_hours(repo: Path) -> float | None:
    head = repo / ".git" / "FETCH_HEAD"
    if not head.exists():
        return None
    import time

    return (time.time() - head.stat().st_mtime) / 3600


def rev(repo: Path, ref: str) -> str:
    for candidate in (f"origin/{ref}", ref):
        out = git(repo, "rev-parse", "--verify", "-q", f"{candidate}^{{commit}}", check=False).strip()
        if out:
            return out
    raise RuntimeError(f"no ref {ref} in {repo}")


def newest_rev(repo: Path, ref: str) -> str:
    """origin/<ref>, unless the local <ref> holds commits origin lacks: a docs/ commit on main, not yet pushed."""
    remote = git(repo, "rev-parse", "--verify", "-q", f"origin/{ref}^{{commit}}", check=False).strip()
    local = git(repo, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}", check=False).strip()
    if local and remote and local != remote:
        behind = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", local, remote]).returncode == 0
        return remote if behind else local
    return remote or local or rev(repo, ref)


def ls_tree(repo: Path, sha: str) -> list[tuple[str, str, int]]:
    """(path, blob sha, size) for every tracked file at sha."""
    out = []
    for line in git(repo, "ls-tree", "-r", "-l", "-z", sha).split("\0"):
        if not line:
            continue
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) == 4 and parts[1] == "blob":
            size = int(parts[3]) if parts[3].isdigit() else 0
            out.append((path, parts[2], size))
    return out


def wanted(path: str, size: int) -> bool:
    if size > MAX_BYTES or path.endswith(SKIP_SUFFIX) or languages.language_for(path) is None:
        return False
    probe = "/" + path
    return not any(part in probe for part in SKIP_PARTS) and "/src/gql/" not in probe


def read_blobs(repo: Path, shas: list[str]) -> dict[str, bytes]:
    """Blob contents through one `git cat-file --batch`."""
    if not shas:
        return {}
    # communicate() drains stdout while stdin is written; writing all of stdin first deadlocks on big repos.
    res = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "--batch"], input=("\n".join(shas) + "\n").encode(), capture_output=True
    )
    out: dict[str, bytes] = {}
    buf, pos = res.stdout, 0
    for _ in shas:
        end = buf.find(b"\n", pos)
        if end < 0:
            break
        header = buf[pos:end].decode().split()
        pos = end + 1
        if len(header) < 3 or header[1] == "missing":
            continue
        size = int(header[2])
        out[header[0]] = buf[pos : pos + size]
        pos += size + 1
    return out


def show(repo: Path, sha: str, path: str) -> str | None:
    res = subprocess.run(["git", "-C", str(repo), "show", f"{sha}:{path}"], capture_output=True)
    return res.stdout.decode("utf-8", "replace") if res.returncode == 0 else None


def diff_names(repo: Path, base: str, head: str | None = None) -> list[str]:
    args = ["diff", "--name-only", base] + ([head] if head else [])
    return [p for p in git(repo, *args, check=False).splitlines() if p]


def merge_base(repo: Path, a: str, b: str) -> str:
    return git(repo, "merge-base", a, b).strip()
