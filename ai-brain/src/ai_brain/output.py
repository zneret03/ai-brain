"""Line format every verb prints: one header line, plain lines of id plus file:line, a 30-line cap (A12)."""

from __future__ import annotations

import time

CAP = 30
NOT_SET_UP, UNREACHABLE = 3, 4


def short(repo: str, prefix: str = "") -> str:
    return repo.removeprefix(prefix)


def header(state: dict, stale: dict[str, int] | None = None) -> str:
    if not state:
        return "ai-brain · not indexed yet (ai-brain/bin/ai-brain index --full)"
    parts = []
    prefix = state.get("strip_prefix", "")
    for repo, sha in sorted(state.get("indexed", {}).items()):
        parts.append(f"{short(repo, prefix)}@{sha[:7]}")
    line = "ai-brain · indexed " + " ".join(parts)
    if state.get("facts_sha"):
        line += f" · facts@{state['facts_sha'][:7]}"
    line += f" · coverage {state.get('coverage', 0):g}%"
    age = (time.time() - state.get("at", time.time())) / 3600
    line += f" · {age:.0f}h old" if age >= 1 else " · fresh index"
    if stale:
        line += " · stale: " + ", ".join(short(r, prefix) for r in sorted(stale))
    return line


def loc(repo: str | None, path: str | None, line: int | None = None) -> str:
    if not path:
        return ""
    where = f"{repo}/{path}" if repo else path
    return f"{where}:{line}" if line else where


def emit(head: str, lines: list[str], more_cmd: str, show_all: bool = False) -> str:
    out = [head]
    if not lines:
        out.append("none")
    elif show_all or len(lines) <= CAP:
        out.extend(lines)
    else:
        out.extend(lines[:CAP])
        out.append(f"+{len(lines) - CAP} more: {more_cmd} --all")
    return "\n".join(out)
