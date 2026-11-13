"""Every script in bin/ answers --help at once, from its own header, and bin/help lists them all."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from ai_brain import cli

BIN = Path(__file__).resolve().parents[2] / "bin"
SCRIPTS = sorted(p for p in BIN.iterdir() if p.is_file() and os.access(p, os.X_OK))


def _run(*args: str, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=30, cwd=cwd, stdin=subprocess.DEVNULL)


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_every_script_answers_help_before_doing_anything(script, tmp_path):
    out = _run(str(script), "--help", cwd=tmp_path)  # a guard after a side effect would show here as a slow run
    assert out.returncode == 0, out.stderr
    if script.name == "ai-brain":  # with the venv in place, argparse answers
        assert "verbs:" in out.stdout and "ticket" in out.stdout
    else:
        assert out.stdout.splitlines()[0] == script.read_text().splitlines()[1].removeprefix("#").strip()


def test_help_lists_every_script():
    out = _run(str(BIN / "help")).stdout
    assert all(f"  {script.name} " in out for script in SCRIPTS)


def test_every_verb_and_option_says_what_it_is_for():
    verbs = next(a for a in cli.parser()._actions if isinstance(a, argparse._SubParsersAction))
    for name, sp in verbs.choices.items():
        assert sp.description, name
        assert all(a.help for a in sp._actions if a.dest not in ("help", "project_sub")), name


@pytest.mark.skipif(not shutil.which("node"), reason="no Node.js")
def test_pr_images_swaps_each_placeholder_for_its_link():
    js = (
        f"import {{ placeholders, rewrite }} from '{(BIN.parent / 'evidence' / 'pr-images.mjs').as_uri()}';"
        "const b = 'a ![x](evidence:x.png) b ![v](evidence:v.mp4) c ![x](evidence:x.png) d ![k](evidence:keep.png)';"
        "console.log(JSON.stringify([placeholders(b), rewrite(b, { 'x.png': 'U1', 'v.mp4': 'U2' })]));"
    )
    files, body = json.loads(_run("node", "--input-type=module", "-e", js).stdout)
    assert files == ["x.png", "v.mp4", "keep.png"]
    assert (
        body == "a ![x](U1) b \nU2\n c ![x](U1) d ![k](evidence:keep.png)"
    )  # a video is a bare link; no link, no swap
