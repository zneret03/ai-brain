# LANGUAGES — what ai-brain reads in each language

ai-brain parses code with [tree-sitter](https://tree-sitter.github.io/tree-sitter/), through the grammars of
`tree-sitter-language-pack`, pinned in `ai-brain/ai-brain/requirements.lock`. Today it parses three languages. Every
other file in a repo is still a node in the graph, with no symbols or calls of its own.

## Parsed today

| Language | Files | What it reads |
|---|---|---|
| Ruby | `.rb` | classes and modules with their superclass; methods with their parameters; constants, resolved by Ruby's lexical nesting; calls on a constant or on `self`, and calls on any other receiver when the method name is defined once in that component and is not a common name such as `save` or `call`, marked `(inferred)`; `Flipper.enabled?` flags; `ENV` reads; HTTP clients (Faraday, HTTParty, Net::HTTP, RestClient); job enqueues (`perform_later`, `perform_async`, `perform_in`, `perform_at`); Kafka topics from `register_as` and `topic_name`; RSpec `describe` targets; URLs in strings |
| TypeScript, JavaScript | `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs` | functions, classes and methods, React components and hooks; imports, resolved through relative paths and the `baseUrl` and `paths` of `tsconfig.json`, following `export … from` up to three hops; calls to imported and local functions; `gql` and `graphql` documents; `fetch` paths; `process.env` reads; micro-frontend registrations (`registerPage`, `registerExtension`, `registerMenu`, `registerTile`, `registerModal`) and `ExtensionSlot` names; `hasPrivilege` checks; Action Cable channels; Playwright `goto` paths; ticket tags such as `@PROJ-123` in strings that start with `@`; URLs in strings |

JavaScript is parsed with the TSX grammar. A Rails app's routes, GraphQL schema, models, policies, jobs, mounts and
Kafka consumers are not parsed: they come from booting the app with a script you supply (`[rails]` in
`project.toml`, `ai-brain/README.md`). That boot is Rails only.

**Read as data, not as code:**

| File | For |
|---|---|
| Markdown in a `notes`, `sprints` or `plans` repo | notes, plans, review rounds, profile pages |
| `db/structure.sql`, `db/schema.rb` | tables |
| `package.json`, `yarn.lock` | npm packages |
| `tsconfig.json` | import aliases |
| the `Gemfile.lock` that `[externals] from` names | externals, and the tag a library repo is read at |

**Not parsed:** `.cjs`, `.d.ts` and `.min.js` files, files over 1 MB, and anything under `node_modules/`, `vendor/`,
`public/`, `db/migrate/`, `tmp/`, `coverage/`, `dist/`, `build/` or `src/gql/`. A file in any other language
(Python, Go, Rust, Elixir, Java and the rest) is a file node that notes and plans can cite, with no symbols,
imports or calls.

## Other languages — planned, not built

The pinned pack recognises 372 languages by file name, and bundles a tags query, the definitions-and-references
format GitHub's code navigation uses, for 68 of them, Ruby, TypeScript and JavaScript included. Among the others:
Python, Elixir, Rust, Go, Java, Kotlin, Scala, Swift, PHP, C#, C, C++, Dart, Lua, OCaml, F#, R, Elm, Gleam,
Solidity, Svelte, Nix and Protocol Buffers. The full list:

```
ai-brain/ai-brain/.venv/bin/python -c "import tree_sitter_language_pack as p; print(*[l for l in p.SupportedLanguage.__args__ if p.get_tags_query(l)])"
```

The plan, in order:

1. **One extractor for every language the pack covers.** It runs the language's tags query, so each of them gets
   files, symbols, imports, calls and tests with no code per language. Imports resolve to files, and tests map to the
   code they test, first for Python, Go, Rust, Elixir, Java and Kotlin; the other languages link calls by name.
2. **Framework facts from any stack.** A facts command per app writes the same rows the Rails boot writes today
   (routes, GraphQL fields, models, jobs, topics), and a monorepo's components are found from `pyproject.toml`,
   `mix.exs`, `Cargo.toml`, `go.mod`, `package.json`, `pom.xml` and `build.gradle`.
3. **Contracts in no particular language.** GraphQL schema files and OpenAPI files become interfaces.

Ruby and TypeScript keep the readers above. A call found by its name alone gets an edge only when the name is
unambiguous, and says `(inferred)`, as Ruby calls do today. A language with no bundled query, such as Haskell,
Erlang, Clojure, Zig, Bash, Perl, Julia or Groovy, will be added with a `tags.scm` file in
`ai-brain/ai-brain/projects/<name>/queries/<language>/`.

## Adding a language today

Until that extractor lands, a language needs code in four places:

1. its file suffixes in `PARSED`, in `ai-brain/ai-brain/src/ai_brain/extract/files.py`;
2. its grammar in `language_for`, in `ai-brain/ai-brain/src/ai_brain/extract/skeleton.py`;
3. a walker in `skeleton.py` that fills the keys the Ruby and TypeScript walkers fill (`KEYS`: symbols, imports,
   calls and the rest);
4. linking in `ai-brain/ai-brain/src/ai_brain/link/code.py`, for its imports and calls, with tests in
   `ai-brain/ai-brain/tests/`.
