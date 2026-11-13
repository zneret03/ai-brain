"""A tiny workspace built at test time: a monorepo (app + two engines), a pilet, a shell, a library, an e2e suite,
notes and plans, and the facts a Rails boot would emit. One fixture covers every edge type in A4."""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

import pytest

from ai_brain import config, indexer
from ai_brain.extract import corpus
from ai_brain.graph import ingest


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def _repo(root: Path, name: str, files: dict[str, str], message: str = "init") -> str:
    repo = root / name
    for path, text in files.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(textwrap.dedent(text).lstrip("\n"))
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", message)
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return _git(repo, "rev-parse", "HEAD")


LIB = {"lib/lib.rb": "module Lib\nend\n"}

MONO = {
    "apps/app/app/models/application_record.rb": "class ApplicationRecord\nend\n",
    "apps/app/app/models/client.rb": """
        class Client < ApplicationRecord
          has_many :orders
        end
    """,
    "apps/app/app/models/order.rb": "class Order < ApplicationRecord\nend\n",
    "apps/app/app/policies/client_policy.rb": "class ClientPolicy\nend\n",
    "apps/app/app/controllers/clients_controller.rb": """
        class ClientsController
          def index
            authorize Client
            Flipper.enabled?(:F1)
            ENV.fetch('API_URL')
            ProcessJob.perform_later(1)
          end
        end
    """,
    "apps/app/app/controllers/items_controller.rb": "class ItemsController\n  def index\n  end\nend\n",
    "apps/app/app/jobs/process_job.rb": """
        class ProcessJob < ApplicationJob
          def perform(id)
            Faraday.new(url: 'https://api.vendor.com')
          end
        end
    """,
    "apps/app/lib/topics.rb": "module Topics\n  CLIENTS = 'clients.events'\nend\n",
    "apps/app/app/kafka/producers/client_producer.rb": """
        class ClientProducer
          self.topic_name = Topics::CLIENTS
        end
    """,
    "apps/app/app/channels/client_channel.rb": "class ClientChannel\nend\n",
    "apps/app/app/javascript/cable.ts": "export function watch() { consumer.subscriptions.create({ channel: 'ClientChannel' }); }\n",
    "apps/app/app/javascript/piral-embed/Slot.tsx": 'export const Slot = () => <ExtensionSlot name="bottom-status" />;\n',
    "apps/app/db/schema.rb": """
        ActiveRecord::Schema[7.1].define(version: 1) do
          create_table "clients", force: :cascade do |t|
            t.string "name"
            t.bigint "parent_id"
          end
          create_table "orders", force: :cascade do |t|
            t.bigint "client_id"
          end
          add_foreign_key "orders", "clients"
          add_foreign_key "clients", "clients", column: "parent_id"
        end
    """,
    "apps/app/spec/models/client_spec.rb": "RSpec.describe Client do\nend\n",
    "apps/app/package.json": json.dumps({"name": "app", "dependencies": {"react": "^18.0.0"}}),
    "apps/app/yarn.lock": 'react@^18.0.0:\n  version "18.3.1"\n',
    "gems/eng-a/eng-a.gemspec": "Gem::Specification.new\n",
    "gems/eng-a/lib/eng_a.rb": "module EngA\nend\n",
    "gems/eng-a/app/graphql/eng_a/resolvers/thing.rb": """
        module EngA
          module Resolvers
            class Thing
              def resolve
                ::Client.find(1)
                EngB::Helper.call(1)
              end
            end
          end
        end
    """,
    "gems/eng-a/app/graphql/eng_a/schema.rb": "module EngA\n  class Schema\n  end\nend\n",
    "gems/eng-a/app/kafka/consumers/client_consumer.rb": """
        module EngA
          class ClientConsumer
            register_as(topic: 'clients.events')
          end
        end
    """,
    "gems/eng-b/eng-b.gemspec": "Gem::Specification.new\n",
    "gems/eng-b/lib/eng_b/helper.rb": """
        module EngB
          class Helper
            def self.call(x)
              x
            end
          end
        end
    """,
}

PILET = {
    "package.json": json.dumps(
        {"name": "@x/pilet", "piral": {"name": "@x/shell"}, "dependencies": {"@x/shell": "^1.0.0", "@x/ui": "^2.0.0"}}
    ),
    "yarn.lock": '"@x/ui@^2.0.0":\n  version "2.1.0"\n\n"@x/shell@^1.0.0":\n  version "1.4.0"\n',
    "tsconfig.json": json.dumps({"compilerOptions": {"baseUrl": "./src", "paths": {"@graphql/*": ["graphql/*"]}}}),
    "src/graphql/queries/things.ts": "export const THINGS = graphql(`\n  query Things { thing { id name } }\n`);\n",
    "src/graphql/mutations/save.ts": "export const SAVE = graphql(`mutation SaveThing { saveThing { id } }`);\n",
    "src/graphql/cacheUpdates/invalidations.ts": "export const SAVE_INVALIDATES = ['Things'] as const;\n",
    "src/graphql/cacheUpdates/thingCache.ts": (
        "export function writeThing(cache) {\n  cache.modify({ id: cache.identify({ __typename: 'Thing', id: 1 }) });\n}\n"
    ),
    "src/types/privileges.ts": "export const PRIVILEGE = { EDIT: 'Security::Edit' } as const;\n",
    "src/hooks/useThings.ts": """
        import { THINGS } from '@graphql/queries/things';
        import { SAVE } from '@graphql/mutations/save';
        import { SAVE_INVALIDATES } from '@graphql/cacheUpdates/invalidations';
        import { writeThing } from '@graphql/cacheUpdates/thingCache';
        import { PRIVILEGE } from '../types/privileges';
        export function useThings() {
          useQuery(THINGS);
          useMutation(SAVE);
          SAVE_INVALIDATES.forEach((n) => n);
          writeThing(cache);
          hasPrivilege(PRIVILEGE.EDIT);
          fetch('/api/v1/items');
          return process.env.PILET_KEY;
        }
    """,
    "src/pages/ThingsPage.tsx": "export function ThingsPage() {\n  return null;\n}\n",
    "src/index.tsx": """
        import { ThingsPage } from './pages/ThingsPage';
        export function setup(app) {
          const page = (p) => p;
          app.registerPage(page('things'), ThingsPage);
          app.registerExtension('bottom-status', () => null);
          app.registerMenu({});
        }
    """,
    "src/__tests__/useThings.test.ts": "import { useThings } from '../hooks/useThings';\ntest('x', () => useThings());\n",
}

SHELL = {"package.json": json.dumps({"name": "@x/shell"})}

E2E = {
    "pages/things.ts": "export async function open(page) {\n  await page.goto('/p/things');\n}\n",
    "tests/things.spec.ts": (
        "import { open } from '../pages/things';\n"
        "test.describe('things', { tag: ['@ticket', '@PROJ-1'] }, () => { test('x', async ({ page }) => open(page)); });\n"
    ),
}

ROUTING = """
def router(ctx, repo):
    return lambda op: "eng-a" if repo == "pilet" else None
"""


@pytest.fixture(scope="session")
def workspace(tmp_path_factory):
    root = tmp_path_factory.mktemp("ws")
    lib_sha = _repo(root, "lib", LIB)
    lock = textwrap.dedent(f"""
        GIT
          remote: https://github.com/x/lib.git
          revision: {lib_sha}
          tag: 1.0.0
          specs:
            lib (1.0.0)

        GIT
          remote: https://github.com/x/outside.git
          revision: abc123
          specs:
            outside (0.1.0)

        GEM
          remote: https://rubygems.org/
          specs:
            faraday (2.9.0)
    """).lstrip("\n")
    _repo(root, "mono", {**MONO, "apps/app/Gemfile.lock": lock}, message="PROJ-1 add clients")
    _repo(root, "pilet", PILET)
    _repo(root, "shell", SHELL)
    _repo(root, "e2e", E2E)
    _repo(
        root,
        "notes",
        {
            "projects/client.md": textwrap.dedent("""
        ---
        id: client-note
        title: Clients
        status: verified
        sources:
          - repo: x/mono
            ref: main
            paths:
              - apps/app/app/models/client.rb
          - repo: x/eng-a
            ref: main
            paths:
              - lib/eng_a.rb
          - repo: x/gone-repo
            ref: main
            paths:
              - README.md
        ---
        Body.
    """).lstrip("\n")
        },
    )
    _repo(
        root,
        "docs",
        {
            "sprints/s1/plan/PROJ-1.md": "Plan. See `apps/app/app/models/client.rb:3` and `useThings.ts`.\n",
            "sprints/s2/plan/PROJ-2.md": "# PROJ-2 — the archive copy\n\nSee `apps/app/app/models/order.rb`.\n",
        },
    )
    _repo(
        root,
        "orch",
        {
            "sprints/s2/plan/PROJ-2.md": HOME_PLAN,
            "sprints/s2/plan/PROJ-4.md": "# PROJ-4 — Sort things\n\n## Files to touch\n\n| File | Change |\n|---|---|\n"
            "| `pilet/src/pages/ThingsPage.tsx` | edit |\n",
            "sprints/README.md": "# sprints\n",
            "sprints/s2/reviews/PROJ-2.md": "# PROJ-2 — branch review\n\n## Round 1\n\n"
            "1. Request changes: `pilet/src/pages/ThingsPage.tsx:1` drops the empty state.\n",
            "docs/GUIDE.md": "# GUIDE — how orders are kept\n\nOne model, `apps/app/app/models/order.rb:1`.\n",
            "profile/STACK.md": "# STACK — how the app runs\n\nThe app's model, `apps/app/app/models/order.rb:1`.\n",
            ".gitignore": "/sprints/\n/profile/\n",  # as in a real sprints repo: both stay untracked
        },
    )
    (root / "orch" / "sprints" / "s2" / "plan" / "PROJ-3.md").write_text("# PROJ-3 — drafted, not committed\n")
    return root


HOME_PLAN = textwrap.dedent("""
    # PROJ-2 — Show things on the page

    **Ticket:** [PROJ-2](https://x/browse/PROJ-2) · Story · In Progress · Dev One ·
    **Parent:** [PROJ-1](https://x/browse/PROJ-1) Clients

    | Repo | Branch | Base | Base SHA |
    |---|---|---|---|
    | `pilet` | `dev/proj-2-v1`, checked out | `origin/main` | `abc1234` |

    ## TLDR

    - **What this is** — the page lists things.

    ## Parity analysis

    ### Frontend

    | # | Area | Exists on `main` | Should (ticket) | Verdict | Gap → action | Test |
    |---|---|---|---|---|---|---|
    | F1 | Page | `src/pages/ThingsPage.tsx:1` renders nothing | lists things | gap | A1 | Jest |
    | F2 | Hook | `useThings.ts` | same | match | none | Jest |
    | F3 | Save | none | saves | gap | A2 | Jest |

    ## Files to touch

    | File | Change | Items | Why |
    |---|---|---|---|
    | `pilet/src/pages/ThingsPage.tsx:1` | edit | A1 | render the list |
    | `pilet/src/pages/ThingsList.tsx` | add | A1 | the list itself |

    ## Action items

    | # | Phase | Side | Action | Repo + files | Closes | Depends on | Verifies by | Status |
    |---|---|---|---|---|---|---|---|---|
    | A1 | 1 | FE | Render the list | `pilet/src/pages/ThingsPage.tsx` | F1 | — | Jest | done |
    | A2 | 1 | FE | Save a thing | `TS src/graphql/mutations/save.ts` | F3 | A1 | Jest | todo |

    ## Dev report

    _Written by /dev._

    ### Summary

    The page now lists things.

    ### Files changed

    | File | Change | Item |
    |---|---|---|
    | `pilet/src/pages/ThingsPage.tsx` | edit | A1 |

    ### PRs

    - https://github.com/x/pilet/pull/7
""").lstrip("\n")


def _facts(root: Path) -> list[dict]:
    m = f"{root}/mono"
    return [
        {"t": "cpath", "file": f"{m}/apps/app/app/models/client.rb", "cpath": "Client"},
        {
            "t": "mount",
            "path": "/eng-a",
            "engine": "EngA::Engine",
            "root": f"{m}/gems/eng-a",
            "gates": [{"src": f"{m}/apps/app/config/routes.rb:3", "flags": ["ENG_A_ON"]}],
        },
        {
            "t": "route",
            "verb": "GET",
            "path": "/api/v1/items",
            "controller": "items",
            "action": "index",
            "engine": None,
            "gates": [{"src": f"{m}/apps/app/config/routes.rb:5", "flags": ["F2"]}],
        },
        {
            "t": "route",
            "verb": "GET",
            "path": "/clients",
            "controller": "clients",
            "action": "index",
            "engine": None,
            "gates": [],
        },
        {
            "t": "schema",
            "name": "EngA::Schema",
            "file": f"{m}/gems/eng-a/app/graphql/eng_a/schema.rb",
            "sdl": "type Query { thing: Thing }\ntype Mutation { saveThing: Thing }\ntype Thing { id: ID name: String }\n",
        },
        {
            "t": "field",
            "schema": "EngA::Schema",
            "type": "Query",
            "field": "thing",
            "args": [],
            "resolver": {
                "cls": "EngA::Resolvers::Thing",
                "file": f"{m}/gems/eng-a/app/graphql/eng_a/resolvers/thing.rb",
            },
        },
        {
            "t": "field",
            "schema": "EngA::Schema",
            "type": "Mutation",
            "field": "saveThing",
            "args": [],
            "resolver": None,
        },
        {"t": "field", "schema": "EngA::Schema", "type": "Thing", "field": "id", "args": [], "resolver": None},
        {"t": "field", "schema": "EngA::Schema", "type": "Thing", "field": "name", "args": [], "resolver": None},
        {
            "t": "consumer",
            "topic": "clients.events",
            "consumer": "EngA::ClientConsumer",
            "group": "g",
            "file": f"{m}/gems/eng-a/app/kafka/consumers/client_consumer.rb",
        },
        {
            "t": "model",
            "class": "Client",
            "table": "clients",
            "file": f"{m}/apps/app/app/models/client.rb",
            "assocs": [{"macro": "has_many", "name": "orders", "class_name": "Order"}],
        },
        {"t": "model", "class": "Order", "table": "orders", "file": f"{m}/apps/app/app/models/order.rb", "assocs": []},
        {"t": "job", "class": "ProcessJob", "kind": "active_job", "file": f"{m}/apps/app/app/jobs/process_job.rb"},
        {"t": "channel", "class": "ClientChannel", "file": f"{m}/apps/app/app/channels/client_channel.rb"},
        {
            "t": "schedule",
            "job": "ProcessJob",
            "cron": "0 1 * * *",
            "source": f"{m}/apps/app/config/sidekiq_recurring_jobs.yml.erb",
        },
        {"t": "meta", "errors": []},
    ]


@pytest.fixture(scope="session")
def project_dir(workspace, tmp_path_factory):
    projects = tmp_path_factory.mktemp("projects")
    pdir = projects / "fixture"
    (pdir / "extractors").mkdir(parents=True)
    (pdir / "facts").mkdir()
    (pdir / "extractors" / "pilet_routing.py").write_text(ROUTING)
    (pdir / "facts" / "rails.jsonl").write_text("\n".join(json.dumps(r) for r in _facts(workspace)) + "\n")
    (pdir / "facts" / "rails.meta.json").write_text(json.dumps({"sha": "fixture", "at": 0}))
    (pdir / "project.toml").write_text(
        textwrap.dedent(f"""
        [project]
        name = "fixture"
        root = "{workspace}"
        [[repos]]
        name = "mono"
        role = "monorepo"
        ref = "main"
        [[repos]]
        name = "pilet"
        role = "pilet"
        ref = "main"
        [[repos]]
        name = "shell"
        role = "shell"
        ref = "main"
        [[repos]]
        name = "lib"
        role = "library"
        ref = "main"
        [[repos]]
        name = "e2e"
        role = "e2e"
        ref = "main"
        [[knowledge]]
        name = "notes"
        kind = "notes"
        ref = "main"
        [[knowledge]]
        name = "docs"
        kind = "plans"
        ref = "main"
        [[knowledge]]
        name = "orch"
        kind = "sprints"
        ref = "main"
        [externals]
        from = "mono/apps/app/Gemfile.lock"
        [extractors]
        pilet_routing = "extractors/pilet_routing.py"
        [tickets]
        prefix = "PROJ"
    """)
    )
    return projects


@pytest.fixture(scope="session")
def built(project_dir, tmp_path_factory):
    var = tmp_path_factory.mktemp("var")
    patch = pytest.MonkeyPatch()
    for mod in (config, indexer, corpus, ingest):
        if hasattr(mod, "VAR"):
            patch.setattr(mod, "VAR", var)
    patch.setattr(config, "PROJECTS", project_dir)
    p = config.load_project("fixture")
    g, meta, ctx = indexer.build(p, fetch=False, boot_mode="never", log=lambda m: None)
    yield g, meta, ctx
    patch.undo()
