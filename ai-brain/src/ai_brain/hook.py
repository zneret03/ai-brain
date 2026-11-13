"""PostToolUse on Edit|Write: print a file's card once per session, only when the file crosses a boundary (A13).
Standard library only, no database: it reads cards/files.tsv. Any failure exits 0 silently."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from .config import PROJECTS, VAR, list_projects, load_project


def card_for(abspath: str) -> tuple[str, str] | None:
    """(project, card) for an absolute path, if a registered repo holds it and the file has a card."""
    target = Path(abspath).resolve()
    for name in list_projects():
        project = load_project(name)
        root = project.root.expanduser().resolve()
        if root not in target.parents:
            continue
        rel = target.relative_to(root).as_posix()
        if rel.split("/", 1)[0] not in {r.name for r in project.repos}:
            return None
        tsv = PROJECTS / name / "cards" / "files.tsv"
        if not tsv.exists():
            return None
        prefix = rel + "\t"
        with open(tsv, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith(prefix):
                    return name, line[len(prefix) :].rstrip("\n").replace("\\n", "\n")
        return None
    return None


def main() -> int:
    try:
        data = json.load(sys.stdin)
        path = (data.get("tool_input") or {}).get("file_path")
        session = str(data.get("session_id") or "nosession")
        if not path:
            return 0
        hit = card_for(path)
        if not hit:
            return 0
        marker = (
            VAR
            / "sessions"
            / hashlib.sha1(session.encode()).hexdigest()[:16]
            / hashlib.sha1(path.encode()).hexdigest()[:16]
        )
        if marker.exists():
            return 0
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": hit[1]}}))
    except Exception:  # the hook must never block or disturb an edit
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
