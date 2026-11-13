# LANGUAGES — what ai-brain reads in each language

ai-brain parses code with [tree-sitter](https://tree-sitter.github.io/tree-sitter/), through the grammars of
`tree-sitter-language-pack`, pinned in `ai-brain/ai-brain/requirements.lock`. Two readers share the work: walkers
that know Ruby and TypeScript in depth, and one reader for every other language, driven by that language's tags
query. Every file neither reads is still a node in the graph, with no symbols or calls of its own.

## Ruby, TypeScript and JavaScript

| Language | Files | What it reads |
|---|---|---|
| Ruby | `.rb` | classes and modules with their superclass; methods with their parameters; constants, resolved by Ruby's lexical nesting; calls on a constant or on `self`, and calls on any other receiver when the method name is defined once in that component and is not a common name such as `save` or `call`, marked `(inferred)`; `Flipper.enabled?` flags; `ENV` reads; HTTP clients (Faraday, HTTParty, Net::HTTP, RestClient); job enqueues (`perform_later`, `perform_async`, `perform_in`, `perform_at`); Kafka topics from `register_as` and `topic_name`; RSpec `describe` targets; URLs in strings |
| TypeScript, JavaScript | `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs` | functions, classes and methods, React components and hooks; imports, resolved through relative paths and the `baseUrl` and `paths` of `tsconfig.json`, following `export … from` up to three hops; calls to imported and local functions; `gql` and `graphql` documents; `fetch` paths; `process.env` reads; micro-frontend registrations (`registerPage`, `registerExtension`, `registerMenu`, `registerTile`, `registerModal`) and `ExtensionSlot` names; `hasPrivilege` checks; Action Cable channels; Playwright `goto` paths; ticket tags such as `@PROJ-123` in strings that start with `@`; URLs in strings |

JavaScript is parsed with the TSX grammar. A Rails app's routes, GraphQL schema, models, policies, jobs, mounts and
Kafka consumers are not parsed: they come from booting the app with a script you supply (`[rails]` in
`project.toml`, `ai-brain/README.md`). That boot is Rails only.

## Every other language

The pack recognises 372 languages by file name, and bundles a tags query, the definitions-and-references format
GitHub's code navigation uses, for 68 of them: Python, Elixir, Rust, Go, Java, Kotlin, Scala, Swift, PHP, C#, C,
C++, Dart, Lua, OCaml, F#, R, Elm, Gleam, Solidity, Svelte, Nix and Protocol Buffers among them. A file in any of
them is read with its query:

| Reads | How |
|---|---|
| Definitions | functions, methods, classes, modules, structs and types, named by where they sit (`Order.total`, `Shop.Orders.total`); a function inside a class is a method, and a Rust `impl` puts its methods under its type; parameters where the grammar names them |
| Calls and type references | each with the receiver written before its name, `bc` in `bc.charge(o)`. A call links to the method of the same class for `self` and `this`; to a definition in the files its receiver or its name was imported from (for a wildcard import, only that module's own names); to one in the same file; in Go and Kotlin, to the one function of that name in its package folder. A method called on a variable links only when one definition in the component has that name and the name is not a common one (`get`, `run`, `save`, `Error`), marked `(inferred)`. A receiver imported from outside the repo is never guessed. In Python and Elixir an unqualified name links only through an import or a local definition, and in Elixir a variable receiver (`conn.host`, a module held in a variable) never links, nor does a call written inside `@spec` or `@callback` |
| Ticket tags | `@PROJ-123` in strings that start with `@` |

Six languages also get their imports resolved to files, their env reads, and their tests:

| Language | Imports resolved | Env reads | Test files |
|---|---|---|---|
| Python | `import a.b`, `from .m import x`, relative and absolute, from an import root | `os.environ[…]`, `os.environ.get`, `os.getenv` | `test_*.py`, `*_test.py`, `conftest.py`, any `.py` under `test/` or `tests/` |
| Go | an import path under a `go.mod` module, to the package's files | `os.Getenv`, `os.LookupEnv` | `*_test.go` |
| Rust | `use crate::`, `self::`, `super::`, and a crate of the repo by name, to `x.rs` or `x/mod.rs` | `env::var`, `env!`, `option_env!` | any `.rs` under `tests/` |
| Elixir | `alias`, `import`, `use` and `require`, to the file that defines the module | `System.get_env`, `System.fetch_env` | `*_test.exs`, any `.exs` under `test/` |
| Java, Kotlin | `import a.b.C`, `a.b.*` and static imports, by path | `System.getenv` | under `src/test/`, and `*Test`, `*Tests`, `*IT` |

A test maps to each file it imports, and to the file it is named after: beside it, in the mirrored folder (`test/`
to `lib/`, `src/test/` to `src/main/`), or the one file of that name in the repo. The other languages get
definitions, calls and ticket tags, without import resolution, env reads or test files.

**Read as data, not as code:**

| File | For |
|---|---|
| Markdown in a `notes`, `sprints` or `plans` repo | notes, plans, review rounds, profile pages |
| `db/structure.sql`, `db/schema.rb` | tables |
| `package.json`, `yarn.lock` | npm packages |
| `tsconfig.json` | import aliases |
| `go.mod`, `Cargo.toml` | Go module paths, Rust crate names |
| the `Gemfile.lock` that `[externals] from` names | externals, and the tag a library repo is read at |

**Not parsed:** `.cjs`, `.d.ts` and `.min.js` files, `.rake` files and `Gemfile`s (the walkers read by suffix),
config formats that happen to have a tags query (`.properties`, udev rules), files over 1 MB, and anything under
`node_modules/`, `vendor/`, `public/`, `db/migrate/`, `tmp/`, `coverage/`, `dist/`, `build/` or `src/gql/`.

## Choosing and adding languages

Every language with a query is read unless the project says otherwise, in its `project.toml`:

```toml
[languages]
exclude = ["c", "cpp"]          # not read
include = ["python", "go"]      # read only these, besides Ruby and TypeScript
```

A language the pack has no query for, such as Haskell, Erlang, Clojure, Zig, Bash, Perl, Julia or Groovy, is
added with a query in the tree-sitter tags format at `ai-brain/ai-brain/projects/<name>/queries/<language>/tags.scm`,
named with the pack's language name. The same file replaces a bundled query. For Bash:

```
(function_definition name: (word) @name) @definition.function
(command name: (command_name (word) @name)) @reference.call
```

Grammars download once, on the first index that needs them, into `~/.cache/tree-sitter-language-pack/`. A language
whose grammar will not load (offline on that first index, or a query its grammar rejects) is left out of that
index, and `status` names it. `status` also counts the files each language read. The full list of bundled queries:

```
ai-brain/ai-brain/.venv/bin/python -c "import tree_sitter_language_pack as p; print(*[l for l in p.SupportedLanguage.__args__ if p.get_tags_query(l)])"
```

Import resolution, env reads and test files for a seventh language take a row in `IMPORTS` and `ENV`
(`ai-brain/ai-brain/src/ai_brain/extract/languages.py`), a branch in `_Langs.resolve`
(`ai-brain/ai-brain/src/ai_brain/link/code.py`) and its test paths in `TEST_PATH`
(`ai-brain/ai-brain/src/ai_brain/model/__init__.py`), with tests in `ai-brain/ai-brain/tests/test_languages.py`.

## Planned, not built

1. **Framework facts from any stack.** A facts command per app writes the rows the Rails boot writes today
   (routes, GraphQL fields, models, jobs, topics), and a monorepo's components are found from `pyproject.toml`,
   `mix.exs`, `Cargo.toml`, `go.mod`, `package.json`, `pom.xml` and `build.gradle`. Today the components come from
   `apps/*` and `gems/*`.
2. **Contracts in no particular language.** GraphQL schema files and OpenAPI files become interfaces.
