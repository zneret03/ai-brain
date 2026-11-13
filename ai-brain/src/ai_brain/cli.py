"""ai-brain <verb>: fixed verbs over api.py; exit 0 answered, 3 not set up, 4 Neo4j unreachable (A12)."""

from __future__ import annotations

import argparse
import sys
import time

from . import api, indexer, output
from .config import BRAIN, list_projects, load_env, load_project


def _index(args) -> str:
    from .cards.render import render
    from .graph import ingest
    from .graph.driver import Unreachable, connect

    p = load_project(args.project)
    mode = "full" if args.full else "changed"
    boot = "always" if args.boot else "never" if args.no_boot else "auto"
    try:
        with indexer.lock():
            g, meta, _ = indexer.build(
                p, mode=mode, fetch=not args.no_fetch, boot_mode=boot, log=_log, pull=args.pull and not args.no_fetch
            )
            cards = render(g, p.dir / "cards")
            _log(f"cards: {cards}")
            try:
                started = api.ensure_neo4j()
                if started:
                    _log(started)
                driver = connect()
            except (Unreachable, api.NotRun) as exc:
                indexer.save_state(p, {**indexer.load_state(p), "cards_at": int(time.time())})
                raise api.NotRun(f"{exc}; cards written, graph not", output.UNREACHABLE) from exc
            try:
                with driver.session() as s:
                    ingest.schema_apply(s)
                    if args.full:
                        ingest.wipe(s, p.name)
                t = time.time()
                counts = ingest.write(driver, g, log=_log)
                _log(f"wrote {counts} in {time.time() - t:.0f}s")
            finally:
                driver.close()
            meta["write"] = counts
            meta["seconds"] = round(meta["seconds"] + time.time() - t, 1)
            indexer.save_state(p, meta)
    except indexer.Busy:
        return output.header(indexer.load_state(p)) + "\nindexing (another index holds var/index.lock)"
    return (
        output.header(meta) + f"\nindexed {meta['nodes']} nodes, {meta['edges']} edges in {meta['seconds']}s; "
        f"wrote {counts}"
    )


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def _cards(args) -> str:
    from .cards.render import render

    p = load_project(args.project)
    g, meta, _ = indexer.build(p, fetch=False, boot_mode="never", log=_log)
    return output.header(indexer.load_state(p)) + f"\ncards: {render(g, p.dir / 'cards')}"


def _schema(args) -> str:
    from .graph import ingest

    with api._session() as s:
        applied = ingest.schema_apply(s)
        shown = [r["name"] for r in s.run("SHOW CONSTRAINTS YIELD name RETURN name").data()]
    return f"schema: {len(applied)} statements applied; constraints: {', '.join(sorted(shown))}"


def _projects(args) -> str:
    from . import config
    from .extract import files

    lines = []
    for name in list_projects():
        p = load_project(name)
        lock = indexer.lockfile(p)
        shas = indexer.target_shas(p, lock)
        lines.append(f"project       {p.name} (root {p.root})")
        for r in p.repos:
            state = (
                "missing"
                if not r.path.exists()
                else "worktree, skipped"
                if files.is_worktree(r.path)
                else f"{r.ref} @ {shas.get(r.name, '?')[:7]}"
            )
            if r.role not in config.ROLES:
                state += f" · unknown role {r.role}"
            lines.append(f"repo          {r.name:<34} {r.role:<9} {state}")
        for k in p.knowledge:
            lines.append(f"knowledge     {k.name:<34} {k.role:<9} {k.ref} @ {shas.get(k.name, '?')[:7]}")
        ls = {
            r.name: files.git(r.path, "ls-tree", "-r", "--name-only", shas[r.name]).splitlines()
            for r in p.repos
            if r.name in shas
        }
        units = config.units(p, ls)
        engines = [u.name for u in units if u.kind == "engine"]
        lines.append(f"engines       {len(engines)}: " + " ".join(output.short(e, p.strip_prefix) for e in engines))
        ext = config.externals(p, lock)
        lines.append(f"externals     {len(ext)}: " + " ".join(f"{e.name}@{(e.tag or e.revision)[:12]}" for e in ext))
        for d in p.skip:
            path = p.root.expanduser() / d
            kind = "a git worktree" if files.is_worktree(path) else "missing" if not path.exists() else "a directory"
            lines.append(f"skipped       {d} ({kind})")
    return "\n".join(lines)


def _doctor(args) -> str:
    lines, worst = [], 0
    venv = (BRAIN / ".venv" / "bin" / "python").exists()
    lines.append(
        f"{'ok ' if venv else 'BAD'} venv        {BRAIN / '.venv'}  python {sys.version.split()[0]} prefix {sys.prefix}"
    )
    env = load_env()
    lines.append(
        f"{'ok ' if env.get('NEO4J_PASSWORD') else 'BAD'} .env        NEO4J_PASSWORD "
        f"{'set' if env.get('NEO4J_PASSWORD') else 'missing'} (value never printed)"
    )
    try:
        from .graph.driver import connect

        d = connect()
        version = d.execute_query("CALL dbms.components() YIELD versions RETURN versions[0] AS v").records[0]["v"]
        d.close()
        lines.append(f"ok  neo4j       bolt://127.0.0.1:7687 {version}")
    except Exception as exc:
        lines.append(f"BAD neo4j       {exc}")
        worst = output.UNREACHABLE
    for name in list_projects():
        p = load_project(name)
        state = indexer.load_state(p)
        lines.append(
            f"{'ok ' if state else '-- '} index       {name}: " + (output.header(state) if state else "none yet")
        )
        found = sorted((p.dir / "facts").glob("*.jsonl")) if (p.dir / "facts").is_dir() else []
        for facts in found or [p.dir / "facts" / "rails.jsonl"]:
            lines.append(
                f"{'ok ' if facts.exists() else '-- '} facts       {facts.relative_to(BRAIN)}"
                + (
                    f" ({time.strftime('%Y-%m-%d %H:%M', time.localtime(facts.stat().st_mtime))})"
                    if facts.exists()
                    else ""
                )
            )
    return "\n".join(lines), worst


EPILOG = """\
examples, from the workspace root:
  ai-brain/bin/ai-brain ticket PROJ-123             everything about one ticket
  ai-brain/bin/ai-brain surface order queue         interfaces by name
  ai-brain/bin/ai-brain impact Order.status
  ai-brain/bin/ai-brain history web-app/src/pages/Orders

Each line is a lead with a path:line: open the file before building on it.
Exit 0 answered, 3 not set up, 4 Neo4j unreachable. `ai-brain <verb> --help` shows a verb's options;
ai-brain/bin/help lists every script. Contract: ai-brain/docs/AI_BRAIN.md."""

PROJECT = "a registered project other than the one your directory is in"
EVERY = "print every line, not only the first 30"
TARGET = "repo/path, a path inside a repo, or a directory"


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="ai-brain",
        description=(
            "Ask the cross-repo graph of a workspace's repos, their plans and their notes. "
            "Run it from the workspace root."
        ),
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--project", help=PROJECT)
    sub = ap.add_subparsers(dest="verb", required=True, metavar="<verb>", title="verbs")

    def verb(name: str, summary: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, help=summary, description=summary)

    sp = verb("surface", "interfaces by name: GraphQL fields and operations, routes, topics, tables, flags, pages")
    sp.add_argument("words", nargs="+", help="words that must all match")
    sp.add_argument("--all", action="store_true", help=EVERY)
    sp = verb("find", "code by what it does: symbol and parameter names, in every repo")
    sp.add_argument("words", nargs="+", help="words that must all match")
    sp.add_argument("--all", action="store_true", help=EVERY)
    sp = verb("impact", "what reaches a field, operation, route, topic, table, symbol or file, with its tests")
    sp.add_argument("target", nargs="?", help="Type.field, an operation, a route, a topic, a table, a symbol or a path")
    sp.add_argument(
        "--diff",
        nargs="*",
        metavar="REPO[@REF]",
        help="instead: what the branches' changes reach outside them; REPO is the checkout as it stands, "
        "REPO@REF a branch's commits wherever the checkout sits, REPO@BASE...REF one stacked on another branch",
    )
    sp.add_argument("--all", action="store_true", help=EVERY)
    sp = verb("consumers", "only the direct consumers of an interface")
    sp.add_argument("target", help="Type.field, an operation, a route, a topic or a table")
    sp.add_argument("--all", action="store_true", help=EVERY)
    sp = verb("trace", "UI to operation to resolver to model to table; producer to topic to consumer")
    sp.add_argument("target", help="a field, an operation or a topic")
    sp.add_argument("--all", action="store_true", help=EVERY)
    sp = verb("notes", "notes and plans that cite a file or match words, each ok, moved or gone")
    sp.add_argument("words", nargs="+", help="a repo/path, or words that must all match")
    sp.add_argument("--all", action="store_true", help=EVERY)
    sp = verb("ticket", "one ticket: plan, files to touch, services, open gaps, branches, commits, PRs, related")
    sp.add_argument("key", help="a ticket key, e.g. PROJ-123")
    sp.add_argument("--all", action="store_true", help=EVERY)
    sp = verb("sprint", "a sprint's tickets with their state, then the files two of its plans both touch")
    sp.add_argument("slug", nargs="?", help="a sprints/ folder; none for the newest sprint; all to list the sprints")
    sp.add_argument("--all", action="store_true", help=EVERY)
    sp = verb("gaps", "open gaps and open action items, for one ticket or one sprint")
    sp.add_argument("scope", nargs="?", help="a ticket key or a sprint folder; none for the newest sprint")
    sp.add_argument("--all", action="store_true", help=EVERY)
    sp = verb("history", "the tickets that planned, built, committed to or cited a file or directory")
    sp.add_argument("target", help=TARGET)
    sp.add_argument("--all", action="store_true", help=EVERY)
    sp = verb("who", "who wrote a file or directory (git authors, recent commits) and the tickets behind it")
    sp.add_argument("target", help=TARGET)
    sp.add_argument("--all", action="store_true", help=EVERY)
    sp = verb("related", "tickets that touched the same files, the rarest shared files counting most")
    sp.add_argument("key", help="a ticket key, e.g. PROJ-123")
    sp.add_argument("--all", action="store_true", help=EVERY)
    sp = verb("status", "graph size, coverage, engines, externals and schema skew")
    sp.add_argument("--skew", action="store_true", help="list the schema skew between engines and pilets")
    sp.add_argument("--all", action="store_true", help=EVERY)
    sp = verb("fresh", "start Neo4j if it is down; re-index in the background when a repo moved")
    sp.add_argument(
        "--quiet", action="store_true", help="print nothing; fetch, pull and re-index detached (SessionStart)"
    )
    sp = verb("index", "rebuild the graph: fetch, parse, link, and write only what changed")
    sp.add_argument("--full", action="store_true", help="wipe the project's graph and rebuild it from empty")
    sp.add_argument("--changed", action="store_true", help="the default: write only what changed")
    sp.add_argument("--no-fetch", action="store_true", help="read what is already fetched; implies no pull")
    sp.add_argument("--boot", action="store_true", help="always boot Rails for the facts")
    sp.add_argument("--no-boot", action="store_true", help="keep the last Rails facts")
    sp.add_argument("--pull", action="store_true", help="fast-forward clean checkouts on their base branch")
    sp.add_argument("--background", action="store_true", help="run detached; output in var/log/index.log")
    verb("cards", "re-render the cards the edit hook shows, from what is already fetched")
    sp = verb("schema", "Neo4j constraints and indexes")
    sp.add_argument("action", choices=["apply"], help="apply: create what is missing")
    verb("projects", "the registered projects")
    verb("doctor", "check the venv, Neo4j, each project's index and its Rails facts")
    for p in sub.choices.values():
        p.add_argument("--project", dest="project_sub", help=PROJECT)
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = parser()
    args = ap.parse_args(argv)
    args.project = getattr(args, "project_sub", None) or args.project
    try:
        if args.verb == "surface":
            text = api.surface(args.words, args.project, args.all)
        elif args.verb == "find":
            text = api.find(args.words, args.project, args.all)
        elif args.verb == "impact":
            if args.target is None and args.diff is None:
                ap.error("impact needs a target or --diff <repo>...")
            text = api.impact(args.target, args.diff, args.project, args.all)
        elif args.verb == "consumers":
            text = api.consumers(args.target, args.project, args.all)
        elif args.verb == "trace":
            text = api.trace(args.target, args.project, args.all)
        elif args.verb == "notes":
            text = api.notes(args.words, args.project, args.all)
        elif args.verb in ("ticket", "related"):
            text = getattr(api, args.verb)(args.key, args.project, args.all)
        elif args.verb in ("history", "who"):
            text = getattr(api, args.verb)(args.target, args.project, args.all)
        elif args.verb == "sprint":
            text = api.sprint(args.slug, args.project, args.all)
        elif args.verb == "gaps":
            text = api.gaps(args.scope, args.project, args.all)
        elif args.verb == "status":
            text = api.status(args.project, args.skew, args.all)
        elif args.verb == "fresh":
            if args.quiet:
                # SessionStart: fetch and pull too, which the plain check skips so a skill never waits on the network
                if not indexer.locked():
                    api.detach(
                        ["index", "--changed", "--pull"] + (["--project", args.project] if args.project else []),
                        "index.log",
                    )
                return 0
            text = api.fresh(args.project)
        elif args.verb == "index":
            if args.background:
                if indexer.locked():
                    print("indexing already (var/index.lock is held)")
                    return 0
                rest = [a for a in (argv if argv is not None else sys.argv[1:]) if a != "--background"]
                api.detach(rest, "index.log")
                print("indexing in the background (ai-brain/ai-brain/var/log/index.log)")
                return 0
            text = _index(args)
        elif args.verb == "cards":
            text = _cards(args)
        elif args.verb == "schema":
            text = _schema(args)
        elif args.verb == "projects":
            text = _projects(args)
        elif args.verb == "doctor":
            text, code = _doctor(args)
            print(text)
            return code
        else:
            ap.error(f"unknown verb {args.verb}")
    except api.NotRun as exc:
        print(f"ai-brain: not run ({exc.reason})")
        return exc.code
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
