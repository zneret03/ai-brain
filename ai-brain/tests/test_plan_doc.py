"""bin/plan-doc in a throwaway workspace: sprints/ is gitignored, so plans are made, read and imported on disk and never
reach git, whatever branch the checkout is on (sprints/README.md)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ID = ["-c", "user.name=t", "-c", "user.email=t@t"]


def _git(repo: Path, *args: str, env: dict | None = None) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *ID, *args], check=True, capture_output=True, text=True, env=env
    ).stdout


def _run(orch: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PLAN_DOC_ARCHIVE": str(orch.parent / "plans-archive")}
    return subprocess.run([str(orch / "bin" / "plan-doc"), *args], capture_output=True, text=True, env=env)


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    orch, docs = tmp_path / "ai-brain", tmp_path / "plans-archive"
    for repo in (orch, docs):
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    (orch / "bin").mkdir()
    shutil.copy(ROOT / "bin" / "plan-doc", orch / "bin" / "plan-doc")
    shutil.copy(ROOT / ".gitignore", orch / ".gitignore")  # the real rules, so the test pins what ships
    _git(orch, "add", "-A")
    _git(orch, "commit", "-qm", "init")
    _git(orch, "switch", "-qc", "feature")  # the checkout is busy elsewhere
    (docs / "README.md").write_text("docs\n")
    _git(docs, "add", "-A")
    _git(docs, "commit", "-qm", "init")
    for day, branch, text in ((1, "dev/proj-1-v1", "old"), (2, "dev/proj-2-v1", "new")):
        _git(docs, "switch", "-qc", branch, "main")
        plan = docs / "sprints/s1/plan/PROJ-1.md"
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text(f"# PROJ-1 — {text}\n")
        _git(docs, "add", "-A")
        when = {
            **os.environ,
            "GIT_COMMITTER_DATE": f"2026-01-0{day}T12:00:00",
            "GIT_AUTHOR_DATE": f"2026-01-0{day}T12:00:00",
        }
        _git(docs, "commit", "-qm", f"plan {text}", env=when)
    (docs / "sprints/s1/plan/PROJ-9.md").write_text("# PROJ-9 — not committed\n")
    return orch, docs


def test_plans_live_on_disk_and_never_reach_git(tmp_path):
    orch, _ = _workspace(tmp_path)
    out = _run(orch, "import")
    assert out.returncode == 0, out.stderr
    assert "import  sprints/s1/plan/PROJ-1.md" in out.stdout
    assert "left    sprints/s1/plan/PROJ-9.md: ??" in out.stdout
    assert (orch / "sprints/s1/plan/PROJ-1.md").read_text() == "# PROJ-1 — new\n"  # the newest commit wins
    assert "already in sprints/" in _run(orch, "import").stdout

    plan = Path(_run(orch, "edit", "sprints/s2/plan/PROJ-2.md").stdout.strip())
    assert plan == orch / "sprints/s2/plan/PROJ-2.md" and plan.parent.is_dir()  # a new sprint gets its folders
    plan.write_text("# PROJ-2 — planned on a feature branch\n")
    assert _run(orch, "show", "PROJ-2").stdout == "# PROJ-2 — planned on a feature branch\n"
    assert _run(orch, "path", "proj-1").stdout.strip() == "sprints/s1/plan/PROJ-1.md"
    assert _run(orch, "path", "PROJ-404").returncode == 1
    assert _run(orch, "commit", "-m", "x", "sprints/s2/plan/PROJ-2.md").returncode == 2  # nothing can commit a plan

    assert _git(orch, "status", "--porcelain", "--untracked-files=all") == ""
    _git(orch, "switch", "-q", "main")  # nothing under sprints/ blocks it
    assert "planned on a feature branch" in _run(orch, "show", "PROJ-2").stdout


def test_refuses_paths_outside_sprints(tmp_path):
    orch, _ = _workspace(tmp_path)
    out = _run(orch, "edit", "README.md")
    assert out.returncode != 0 and "only .md or .html files under sprints/" in out.stderr


def test_answers_an_unknown_command_with_its_usage(tmp_path):
    out = _run(_workspace(tmp_path)[0], "bogus")
    assert out.returncode == 2 and "plan-doc path <KEY>" in out.stderr


def test_import_needs_an_archive(tmp_path):
    orch, _ = _workspace(tmp_path)
    out = subprocess.run(
        [str(orch / "bin" / "plan-doc"), "import"],
        capture_output=True,
        text=True,
        env={k: v for k, v in os.environ.items() if k != "PLAN_DOC_ARCHIVE"},
    )
    assert out.returncode != 0 and "set PLAN_DOC_ARCHIVE" in out.stderr
