"""Small pure pieces: tokens, Ruby constant resolution, the skeleton, the line format, the hook, exit codes."""

from __future__ import annotations

import io
import json
import tomllib

from ai_brain import cli, config, hook, output
from ai_brain.extract.skeleton import parse
from ai_brain.link import code, plans
from ai_brain.model import tokens


def test_tokens_split_every_case():
    assert tokens("formatShortRange", "start_iso", "end-date") == "format short range start iso end date"
    assert tokens("OrderApprovalQueueRow") == "order approval queue row"


class _Ctx:
    def __init__(self, known):
        self.known_cpaths = set(known)


def test_resolve_const_follows_lexical_nesting():
    ctx = _Ctx({"OrdersService", "OrdersService::Client", "Client", "SecurityService"})
    assert code.resolve_const(ctx, "Client", ["OrdersService::Foo", "OrdersService"]) == ("OrdersService::Client")
    assert code.resolve_const(ctx, "Client", ["OrdersService::Foo"]) == "Client"  # compact style: no parent
    assert code.resolve_const(ctx, "::Client", ["OrdersService"]) == "Client"
    assert code.resolve_const(ctx, "Unknown", ["OrdersService"]) is None


def test_underscore_matches_zeitwerk():
    assert code.underscore("OrdersService::SecurityBridge") == "orders_service/security_bridge"
    assert code.underscore("HTTPClient") == "http_client"


def test_skeleton_ruby():
    out = parse(
        "a.rb",
        b"module A\n  class B < C\n    def self.x(a, b: 1)\n      D::E.call(z)\n"
        b"      Flipper.enabled?(:F)\n    end\n  end\nend\n",
    )
    quals = [s[0] for s in out["symbols"]]
    assert quals == ["A", "A::B", "A::B.x"]
    assert out["symbols"][2][3] == ["a", "b"]
    assert ["A::B.x", "D::E", ["A::B", "A"], "call", "const"] == out["calls"][0][:5]
    assert out["flags"][0][1] == "F"


def test_skeleton_ts():
    src = b"import { a } from './a';\nexport const useX = (startIso: string) => { a(); return process.env.K; };\n"
    out = parse("x.ts", src)
    assert out["symbols"][0][:2] == ["useX", "function"] and out["symbols"][0][4] == "hook"
    assert out["imports"][0][:3] == ["a", "a", "./a"]
    assert out["env"][0][1] == "K"


def test_emit_caps_at_thirty_lines():
    text = output.emit("head", [str(i) for i in range(40)], "ai-brain find x")
    lines = text.splitlines()
    assert len(lines) == 32 and lines[-1] == "+10 more: ai-brain find x --all"
    assert output.emit("head", [], "") == "head\nnone"


def test_hook_is_silent_off_a_hit(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"tool_input": {"file_path": "/nowhere/x.ts"}})))
    assert hook.main() == 0
    assert capsys.readouterr().out == ""


def test_hook_survives_bad_input(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    assert hook.main() == 0
    assert capsys.readouterr().out == ""


def test_unreachable_neo4j_is_exit_4(monkeypatch, capsys):
    from ai_brain.graph import driver

    def boom():
        raise driver.Unreachable("Neo4j unreachable at 127.0.0.1:7687: ServiceUnavailable")

    monkeypatch.setattr("ai_brain.api.connect", boom)
    assert cli.main(["find", "anything"]) == output.UNREACHABLE
    assert capsys.readouterr().out.startswith("ai-brain: not run (Neo4j unreachable")


def test_quiet_fresh_prints_nothing_and_skips_a_running_index(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr("ai_brain.api.detach", lambda args, log: calls.append((args, log)))
    monkeypatch.setattr("ai_brain.indexer.locked", lambda: False)
    assert cli.main(["fresh", "--quiet"]) == 0
    monkeypatch.setattr("ai_brain.indexer.locked", lambda: True)
    assert cli.main(["fresh", "--quiet"]) == 0
    assert calls == [(["index", "--changed", "--pull"], "index.log")]
    assert capsys.readouterr().out == ""


def _repo_with_origin_ahead(tmp_path):
    import subprocess

    repo = tmp_path / "r"
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True)  # noqa: E731
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    (repo / "a.txt").write_text("1\n")
    run("add", "-A")
    run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "one")
    (repo / "a.txt").write_text("2\n")
    run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "two")
    run("update-ref", "refs/remotes/origin/main", "HEAD")
    run("reset", "-q", "--hard", "HEAD~1")  # local main one commit behind origin/main
    return repo, run


def test_pull_fast_forwards_a_clean_base_checkout(tmp_path):
    from ai_brain.extract.files import pull_ff

    repo, run = _repo_with_origin_ahead(tmp_path)
    assert pull_ff(repo, "main").startswith("pulled ")
    assert (repo / "a.txt").read_text() == "2\n"
    assert pull_ff(repo, "main") == "up to date"


def test_pull_leaves_other_branches_and_dirty_trees(tmp_path):
    from ai_brain.extract.files import pull_ff

    repo, run = _repo_with_origin_ahead(tmp_path)
    (repo / "a.txt").write_text("edited\n")
    assert pull_ff(repo, "main") == "skipped: uncommitted changes"
    assert (repo / "a.txt").read_text() == "edited\n"
    run("checkout", "-q", "--", "a.txt")
    run("switch", "-q", "-c", "dev/proj-1-v1")
    assert pull_ff(repo, "main") == "skipped: on dev/proj-1-v1, not main"


def test_ticket_keys_follow_the_configured_prefix():
    assert plans._key("sprints/s1/plan/PROJ-7.md", {}, None, "PROJ") == "PROJ-7"
    assert plans._key("sprints/s1/plan/PROJ-7.md", {}, None, None) is None  # no prefix, no ticket links


def test_the_template_root_is_the_folder_the_checkout_sits_in():
    raw = tomllib.loads((config.BRAIN / "projects" / "_template" / "project.toml").read_text())
    assert config._root(raw) == config.BRAIN.parents[1]
