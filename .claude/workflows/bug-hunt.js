export const meta = {
  name: 'bug-hunt',
  description:
    'Serial browser bug hunt over the feature already in the working trees: Playwright hunters drive the real UI one at a time, the developer patches what they find, the gate runs, a hunter re-drives every fix, and the ticket evidence folder is written whether or not anything broke',
  whenToUse:
    'Hunting bugs in a feature that is already implemented — usually straight after /dev, or on a branch waiting for review. Invoked by the /bug-hunt command, which owns preflight, the branches, the commits and the write-up beside the plan in ai-brain/sprints.',
  phases: [
    {
      title: 'Scope',
      detail: 'read the diff in every repo and derive the surfaces, personas and operations the feature actually reaches',
    },
    { title: 'Hunt', detail: 'Playwright hunters drive those surfaces ONE AT A TIME — the suite shares one database and one frontend dev server' },
    { title: 'Fix', detail: 'the developer patches the confirmed defects, one writer per repo' },
    { title: 'Gate', detail: 'scoped rubocop / rspec / lint / type-check / jest on the repos the fixes touched' },
    { title: 'Verify', detail: 'a hunter re-drives every fixed finding in the browser — nothing is fixed on a claim' },
    { title: 'Evidence', detail: "write the ticket's evidence folder in the e2e repo — mandatory, findings or not" },
    { title: 'Evidence check', detail: 'the folder, notes.md and bug-hunt.md must exist on disk, or the run says so' },
  ],
};

// ---------------------------------------------------------------------------
// args: { ticket: string, today: string, base?: object, scope?: string,
//         families?: string | string[], maxRounds?: number, notes?: string,
//         moreContext?: string | string[], fixMinor?: boolean, noFix?: boolean,
//         e2eRepo?: string, repos?: string | string[], evidenceDir?: string }
//
// `e2eRepo`, `repos` and `evidenceDir` are the workspace's own facts; the /bug-hunt command reads
// them from ai-brain/profile/ (REPOS.md, E2E.md) and passes them in. The defaults are neutral.
//
// `today` is passed IN because a workflow script cannot call `new Date()` — it would
// break resume. Everything dated in this run (the evidence notes, the report the command
// writes afterwards) uses this one string, so the artefacts agree with each other.
//
// `notes` is what preflight found — branches, bases, a service that had to be started.
// `moreContext` is what the user knows and neither the ticket nor the code says; every
// worker reads it. `scope` narrows the hunt in the user's own words ("only the Process
// button gate", "the checklist header"); absent, the diff decides.
// ---------------------------------------------------------------------------

const TICKET = ((args && args.ticket) || '').trim();
const TODAY = ((args && args.today) || '').trim();
const NOTES = (args && args.notes) || '';
const SCOPE_HINT = ((args && args.scope) || '').trim();
const FIX_MINOR = Boolean(args && args.fixMinor);
const NO_FIX = Boolean(args && args.noFix);

const RAW_MORE_CONTEXT = (args && args.moreContext) || [];
const MORE_CONTEXT = (Array.isArray(RAW_MORE_CONTEXT) ? RAW_MORE_CONTEXT : [RAW_MORE_CONTEXT])
  .map((c) => String(c).trim())
  .filter(Boolean);

const RAW_FAMILIES = (args && args.families) || [];
const FAMILY_FILTER = (Array.isArray(RAW_FAMILIES) ? RAW_FAMILIES : [RAW_FAMILIES])
  .map((f) => String(f).trim())
  .filter(Boolean);

// `||` would swallow 0 and hand a non-numeric string to the loop condition, where
// `1 <= NaN` is false and the loop silently never runs.
const RAW_ROUNDS = Number(args && args.maxRounds);
const MAX_ROUNDS = Number.isInteger(RAW_ROUNDS) && RAW_ROUNDS > 0 ? RAW_ROUNDS : 3;

if (!TICKET) {
  throw new Error(
    'bug-hunt needs args.ticket — the ticket key of the feature under test (e.g. "PROJ-123"), or NEW-<slug> for a feature with no ticket yet. It names the evidence folder, so there is no unnamed run.',
  );
}
if (!TODAY) {
  throw new Error(
    'bug-hunt needs args.today (YYYY-MM-DD) — a workflow cannot read the clock, and every artefact this run writes is dated from it.',
  );
}

// The e2e repo the hunters write in, and the repos the diff is read from: ai-brain/profile/E2E.md
// § Suite and REPOS.md, passed in by the command.
const PLAYWRIGHT = ((args && args.e2eRepo) || 'e2e').trim();
const EVIDENCE_DIR = ((args && args.evidenceDir) || `${PLAYWRIGHT}/artifacts/tickets/${TICKET}`).trim();

const RAW_REPOS = (args && args.repos) || [];
const REPOS = (Array.isArray(RAW_REPOS) ? RAW_REPOS : [RAW_REPOS]).map((r) => String(r).trim()).filter(Boolean);
const REPO_LIST = REPOS.length
  ? REPOS.concat([PLAYWRIGHT, 'ai-brain'].filter((r) => REPOS.indexOf(r) === -1)).join(' ')
  : `<every repo in ai-brain/profile/REPOS.md> ${PLAYWRIGHT} ai-brain`;

const WORKSPACE = `You are working from the workspace root, which holds every repo as a sibling directory. Every path you read, write or report is relative to that root — \`<repo>/app/...\`, \`<frontend>/src/...\`, \`${PLAYWRIGHT}/tests/...\`.

The workspace's facts live in \`ai-brain/profile/\`:
- \`REPOS.md\` — what is cloned, the stack, ports, base branches, the gate command per repo
- \`MICROSERVICES.md\` — the services and which decision each one owns
- \`DEFINITIONS.md\` — personas, statuses, classifications, the domain rules
- \`GRAPHQL_SURFACES.md\` — where every existing query and mutation lives
- \`CODE_MAP.md\` — where each layer's files live, the contract files, the conventions
- \`STACK.md\` — running the app: entry points, ports, flags
- \`E2E.md\` — the e2e suite (\`${PLAYWRIGHT}\`): its folders, fixtures, seeds, commands and traps, and the evidence folder`;

// The one hard constraint of this workflow. `playwright.config.ts` sets `workers: 1` and
// `fullyParallel: false` because the whole suite shares ONE backend database whose seeds
// clear and recreate, and ONE frontend dev server. Two agents driving browsers at the same time
// do not find twice the bugs — they seed over each other and report each other's wreckage
// as defects. Every browser stage below is therefore a serial `for` loop, never
// `parallel()`, and this paragraph is in every hunter's prompt so it knows why it waits.
const SERIAL_RULE = `THE BROWSER IS EXCLUSIVELY YOURS WHILE YOU RUN, AND ONLY WHILE YOU RUN. The Playwright suite is \`workers: 1\`, \`fullyParallel: false\`, one shared backend database whose seeds clear and recreate, and one frontend dev server (\`ai-brain/profile/E2E.md\` § Suite). This orchestrator therefore runs exactly one browser agent at a time. Do not parallelise your own runs, do not raise \`--workers\`, and do not leave a server you started behind for the next agent to inherit in a strange state. If a seed you took leaves the stack dirty in a way the next hunter would misread, say so in your summary — it is the only channel between us.`;

const CONTEXT_BLOCK = MORE_CONTEXT.length
  ? [
      'EXTRA CONTEXT FROM THE USER, given with `--more-context`. Treat it as authoritative about **intent** — what the feature is for, what is deliberately out of scope, what the team decided and never wrote down.',
      'It is not authoritative about the **code**, and it does not define correctness on its own: a claim here still needs a `file:line` before you act on it, and where it contradicts the repository, report the contradiction rather than picking a side.',
      MORE_CONTEXT.map((c, i) => `(${i + 1})\n"""\n${c}\n"""`).join('\n\n'),
    ].join('\n\n')
  : '';
const CTX = CONTEXT_BLOCK ? `${CONTEXT_BLOCK}\n\n` : '';

// The feature under test is whatever is in the trees — uncommitted, or committed on a
// ticket branch, or both. `git add -A -N` first: without intent-to-add, `git diff` omits
// untracked files entirely, and a new page or a new spec is almost all untracked.
const DIFF_INSTRUCTIONS = `HOW TO SEE THE FEATURE UNDER TEST. It is whatever is in the working trees right now — some of it uncommitted, some of it possibly already committed on a ticket branch. Find it yourself; do not take a description of it on trust.

\`\`\`
for d in ${REPO_LIST}; do
  printf '%-34s %-28s %s\\n' "$d" \\
    "$(git -C "$d" rev-parse --abbrev-ref HEAD)" \\
    "$(git -C "$d" status --porcelain | wc -l) changed"
done
\`\`\`

Then, per repo that has changes or is on a ticket branch:

1. \`git -C <repo> add -A -N\` — intent-to-add, first, or the diff hides every new file.
2. \`git -C <repo> status --porcelain\` — the inventory. Anything here but absent from the diff, open directly.
3. \`git -C <repo> diff HEAD\` — the uncommitted work.
4. \`git -C <repo> diff origin/<base>...HEAD\` — what is already committed on the branch, where \`<base>\` is \`git -C <repo> symbolic-ref --short refs/remotes/origin/HEAD\`. Use the remote ref, never the local branch of the same name, which lags and widens the diff with unrelated commits.`;

// ---------------------------------------------------------------------------
// Schemas
// ---------------------------------------------------------------------------

// A finding carries its own reproduction. `scenario` is what was done, `observed` is what
// the browser did, `expected` is why that is wrong — a finding missing any of the three is
// a hunch, and the developer cannot act on a hunch.
const FINDING_ITEM = {
  type: 'object',
  additionalProperties: false,
  required: ['id', 'family', 'repo', 'file', 'line', 'severity', 'scenario', 'expected', 'observed', 'fix'],
  properties: {
    id: { type: 'string' },
    family: { type: 'string' },
    repo: { type: 'string' },
    file: { type: 'string' },
    line: { type: 'integer' },
    severity: { type: 'string', enum: ['BLOCKER', 'MAJOR', 'MINOR', 'NIT'] },
    scenario: { type: 'string' },
    expected: { type: 'string' },
    observed: { type: 'string' },
    fix: { type: 'string' },
    evidence: { type: 'string' },
    reproduces_with: { type: 'string' },
  },
};

const SCENARIO_ITEM = {
  type: 'object',
  additionalProperties: false,
  required: ['name', 'what_i_did', 'verdict'],
  properties: {
    name: { type: 'string' },
    what_i_did: { type: 'string' },
    verdict: { type: 'string', enum: ['clean', 'broken', 'blocked'] },
    note: { type: 'string' },
  },
};

const SCOPE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['ticket', 'repos', 'surfaces', 'operations', 'families', 'unreachable', 'summary'],
  properties: {
    ticket: { type: 'string' },
    repos: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['repo', 'branch', 'files_changed', 'what_changed'],
        properties: {
          repo: { type: 'string' },
          branch: { type: 'string' },
          files_changed: { type: 'integer' },
          what_changed: { type: 'string' },
        },
      },
    },
    surfaces: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['route', 'persona', 'why', 'seedable'],
        properties: {
          route: { type: 'string' },
          persona: { type: 'string' },
          why: { type: 'string' },
          seedable: { type: 'string', enum: ['yes', 'partly', 'no'] },
          page_helper: { type: 'string' },
        },
      },
    },
    operations: { type: 'array', items: { type: 'string' } },
    families: {
      type: 'array',
      minItems: 1,
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['name', 'why_reachable', 'scenarios'],
        properties: {
          name: { type: 'string' },
          why_reachable: { type: 'string' },
          scenarios: { type: 'array', minItems: 1, items: { type: 'string' } },
        },
      },
    },
    unreachable: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['what', 'why'],
        properties: { what: { type: 'string' }, why: { type: 'string' } },
      },
    },
    summary: { type: 'string' },
  },
};

const HUNT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['verdict', 'family', 'scenarios', 'findings', 'screenshots', 'artifacts_written', 'summary'],
  properties: {
    verdict: { type: 'string', enum: ['CLEAN', 'BUGS_FOUND', 'NOT_RUN'] },
    family: { type: 'string' },
    scenarios: { type: 'array', minItems: 1, items: SCENARIO_ITEM },
    findings: { type: 'array', items: FINDING_ITEM },
    screenshots: { type: 'array', items: { type: 'string' } },
    // Probes and specs are kept, not deleted — the harness is the reusable asset.
    artifacts_written: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
};

const FIX_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['patched', 'not_patched', 'tests_added', 'summary'],
  properties: {
    patched: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['finding_id', 'repo', 'files', 'root_cause', 'what_changed'],
        properties: {
          finding_id: { type: 'string' },
          repo: { type: 'string' },
          files: { type: 'array', items: { type: 'string' } },
          root_cause: { type: 'string' },
          what_changed: { type: 'string' },
        },
      },
    },
    not_patched: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['finding_id', 'why'],
        properties: {
          finding_id: { type: 'string' },
          why: { type: 'string' },
          needs: { type: 'string' },
        },
      },
    },
    tests_added: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
};

const GATE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['repos_touched', 'checks', 'summary'],
  properties: {
    repos_touched: { type: 'array', items: { type: 'string' } },
    checks: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['repo', 'name', 'result', 'evidence'],
        properties: {
          repo: { type: 'string' },
          name: { type: 'string' },
          result: { type: 'string', enum: ['pass', 'fail', 'skipped', 'not_run'] },
          evidence: { type: 'string' },
        },
      },
    },
    summary: { type: 'string' },
  },
};

const VERIFY_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['verdict', 'verified', 'regressions', 'screenshots', 'summary'],
  properties: {
    verdict: { type: 'string', enum: ['PASS', 'FAIL', 'NOT_RUN'] },
    verified: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['finding_id', 'status', 'evidence'],
        properties: {
          finding_id: { type: 'string' },
          status: { type: 'string', enum: ['fixed', 'still_broken', 'not_reachable'] },
          evidence: { type: 'string' },
        },
      },
    },
    regressions: { type: 'array', items: FINDING_ITEM },
    screenshots: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
};

const EVIDENCE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['folder', 'files', 'screenshots', 'missing', 'summary'],
  properties: {
    folder: { type: 'string' },
    files: { type: 'array', items: { type: 'string' } },
    screenshots: { type: 'array', items: { type: 'string' } },
    missing: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
};

const EVIDENCE_CHECK_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['folder_exists', 'notes_exists', 'hunt_log_exists', 'image_count', 'files', 'summary'],
  properties: {
    folder_exists: { type: 'boolean' },
    notes_exists: { type: 'boolean' },
    hunt_log_exists: { type: 'boolean' },
    image_count: { type: 'integer' },
    files: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
};

// ---------------------------------------------------------------------------
// Helpers — plain functions, no agents. Triage is arithmetic, not judgement.
// ---------------------------------------------------------------------------

const FIXABLE = FIX_MINOR ? ['BLOCKER', 'MAJOR', 'MINOR'] : ['BLOCKER', 'MAJOR'];

// Same defect reported by two families is one defect. Keyed on the place plus the
// observed behaviour, not on the prose: two hunters describe the same break differently.
function keyOf(finding) {
  return [finding.repo, finding.file, String(finding.line), (finding.observed || '').slice(0, 80)]
    .join('|')
    .toLowerCase();
}

function renderFindings(findings) {
  return findings
    .map(
      (f) =>
        `- **${f.id}** [${f.severity}] \`${f.repo}/${f.file}:${f.line}\` (family: ${f.family})\n  - scenario: ${f.scenario}\n  - expected: ${f.expected}\n  - observed: ${f.observed}\n  - hunter's suggested fix: ${f.fix}${
          f.reproduces_with ? `\n  - reproduces with: \`${f.reproduces_with}\`` : ''
        }`,
    )
    .join('\n');
}

function renderGate(gate) {
  if (!gate) return 'THE GATE DID NOT REPORT. Treat every check as not run.';
  return `GATE RESULTS (already run centrally — do not re-run them):\n${gate.checks
    .map((c) => `- ${c.repo} · ${c.name}: **${c.result}** — ${c.evidence}`)
    .join('\n')}`;
}

function gateFailed(gate) {
  return Boolean(gate && gate.checks.some((c) => c.result === 'fail'));
}

// ---------------------------------------------------------------------------
// Scope — what did we actually change, and what can a browser reach?
// ---------------------------------------------------------------------------

phase('Scope');

const scope = await agent(
  `You are scoping a browser bug hunt for **${TICKET}**. You do not hunt and you do not fix: you read the diff and say what a hunter can reach.

${WORKSPACE}

${DIFF_INSTRUCTIONS}

${CTX}${SCOPE_HINT ? `THE USER NARROWED THE HUNT: """${SCOPE_HINT}""" — honour it. Surfaces outside it belong in \`unreachable\` with that as the reason.\n\n` : ''}${NOTES ? `WHAT PREFLIGHT FOUND:\n"""\n${NOTES}\n"""\n\n` : ''}Produce:

- \`repos\` — every repo with changes or on a ticket branch, its branch, how many files, and one line on what changed.
- \`surfaces\` — the **routes a browser can open** that this diff can change, each with the persona that reaches it and why. Read the suite's page helpers (\`ai-brain/profile/E2E.md\` § Suite names their folder) and name the one that fits. A diff in an engine resolver still reaches a screen; name the screen, not the resolver.
- \`operations\` — the GraphQL operations involved, so the hunter knows what to fault with \`page.route\`.
- \`families\` — the scenario families worth running, IN THE ORDER THEY SHOULD RUN, each with why it is reachable **for this diff** and 2-6 concrete scenarios. Start from these and prune what the diff cannot reach; a family you keep for the sake of the list wastes a browser pass:
  - \`zero-one-many\` — empty, exactly one (singular copy), and a count past the page boundary.
  - \`absent-value\` — a null the type permits, a parent with nothing configured, a projection row that does not exist.
  - \`failure-isolation\` — fault ONE operation with \`page.route\` and check the other reads still paint.
  - \`identity-and-scope\` — the same screen as every persona the change touches, including the one it now denies; a client-scoped count that must not move when a table pages.
  - \`order-and-timing\` — reload mid-load, page then search then page back, Back through a guard, a second click before the first settles.
  - \`boundaries\` — a date-range edge, a non-UTC timezone, a value at the top of its range.
- \`unreachable\` — what this diff changed that a browser cannot show, and why. Be specific: an unreachable half is the honest limit of this run and the command reports it.

Read \`${PLAYWRIGHT}/CLAUDE.md\` and \`ai-brain/profile/E2E.md\` § Suite before you name a seed or a helper — what is seedable is a property of the suite's seed client, not a guess. Where a state needs a seeder that does not exist, say so in \`unreachable\` with the seeder that would be needed.

Return via the StructuredOutput tool.`,
  {
    label: 'scope',
    phase: 'Scope',
    schema: SCOPE_SCHEMA,
    agentType: 'general-purpose',
  },
);

if (!scope) {
  return {
    ticket: TICKET,
    aborted:
      'The scope agent returned nothing, so there is no surface list to hunt. That is an agent failure, not a defect in the feature — re-run rather than reading anything into it.',
    converged: false,
    rounds: 0,
  };
}

let families = scope.families;
if (FAMILY_FILTER.length) {
  const wanted = FAMILY_FILTER.map((f) => f.toLowerCase());
  const kept = families.filter((f) => wanted.indexOf(f.name.toLowerCase()) !== -1);
  const unknown = wanted.filter((w) => !families.some((f) => f.name.toLowerCase() === w));
  if (unknown.length) log(`--families named ${unknown.join(', ')}, which the scope pass did not plan — ignored`);
  if (kept.length) families = kept;
  else log('--families matched nothing the scope pass planned; running the full planned list instead');
}

log(
  `${TICKET}: ${scope.repos.length} repo(s), ${scope.surfaces.length} surface(s), ${families.length} family(ies) planned — hunters run one at a time`,
);
if (scope.unreachable.length) {
  log(`${scope.unreachable.length} part(s) of this diff a browser cannot reach — reported, not hunted`);
}

const scopeContext = `THE FEATURE UNDER TEST — **${TICKET}**, scoped from the diff:

${scope.repos.map((r) => `- \`${r.repo}\` (${r.branch}, ${r.files_changed} file(s)): ${r.what_changed}`).join('\n')}

SURFACES A BROWSER CAN REACH:
${scope.surfaces
  .map(
    (s) =>
      `- \`${s.route}\` as **${s.persona}** — ${s.why} (seedable: ${s.seedable}${s.page_helper ? `, helper: \`${s.page_helper}\`` : ''})`,
  )
  .join('\n')}

GRAPHQL OPERATIONS INVOLVED: ${scope.operations.length ? scope.operations.map((o) => `\`${o}\``).join(', ') : 'none named'}

WHAT THE SCOPE PASS COULD NOT REACH:
${scope.unreachable.length ? scope.unreachable.map((u) => `- ${u.what} — ${u.why}`).join('\n') : '- nothing recorded'}

SCOPE SUMMARY: ${scope.summary}`;

// ---------------------------------------------------------------------------
// The loop: hunt (serial) → fix → gate → verify (serial)
// ---------------------------------------------------------------------------

const history = [];
const allFindings = [];
const seen = new Set();
const fixedIds = new Set();
const unfixed = [];
let aborted = '';
let converged = false;
let round = 0;
// After round 1 the hunt narrows to the families that actually broke something: a family
// that came back clean on an unchanged surface will come back clean again, and the browser
// passes are the expensive part of this run.
let familiesThisRound = families;
// Set when a round's gate goes red. The next round then goes straight back to the
// developer: re-driving a browser over a tree that does not lint, type-check or pass its
// own unit specs grades the wrong thing, and the previous round's findings are still the
// work in hand.
let repairOnly = false;
let lastHunts = [];
// Carries a red gate's output into the next fix round, so the developer reads its own
// broken patch as the first item rather than being handed the same findings again with no
// mention that the tree stopped compiling.
let gateFailureNote = '';

while (round < MAX_ROUNDS) {
  round += 1;
  phase('Hunt');

  // A red gate last round means the tree is not worth driving: go straight back to the
  // developer with the findings that are still open, and reuse the hunt record we already
  // have so the evidence folder still shows every scenario that was driven.
  const driveBrowser = !repairOnly;
  if (repairOnly) {
    log(`round ${round}: skipping the browser — last round's gate was red, so the developer goes again first`);
    repairOnly = false;
  }
  const huntResults = driveBrowser ? [] : lastHunts.slice();
  let freshThisRound = 0;

  // SERIAL, deliberately. See SERIAL_RULE — one shared database, one frontend dev server.
  for (let i = 0; driveBrowser && i < familiesThisRound.length; i += 1) {
    const family = familiesThisRound[i];
    const known = allFindings.length
      ? `\n\nALREADY FOUND THIS RUN — do not re-report these, hunt past them:\n${renderFindings(allFindings)}`
      : '';

    const result = await agent(
      `Read \`ai-brain/.claude/agents/qa-e2e.md\` and follow it in full — it is your role definition. Read \`${PLAYWRIGHT}/CLAUDE.md\` and \`ai-brain/profile/E2E.md\` § Suite in full before you touch anything; they document traps that have produced false findings, and this lane is where they bite.

${WORKSPACE}

You are the **${family.name}** hunter on round ${round} of a bug hunt over **${TICKET}**. This is not a criteria audit: the feature is already built and its own specs are green. Your job is to make it misbehave.

${SERIAL_RULE}

${scopeContext}

${CTX}THE SCENARIOS THIS FAMILY IS FOR — ${family.why_reachable}:
${family.scenarios.map((s, n) => `${n + 1}. ${s}`).join('\n')}

Treat that list as the floor. Add what the surfaces suggest, and drop a scenario the seeds genuinely cannot reach — recording it as \`blocked\` with the reason, never as \`clean\`.${known}

HOW TO WORK

1. Preflight the stack and **bring it up yourself if it is down**: the services, ports and flag \`ai-brain/profile/E2E.md\` § Suite and \`STACK.md\` § Entry points name; Playwright boots its own frontend dev server. \`NOT_RUN\` is for an obstacle you cannot clear, named with the command that clears it.
2. Drive the surfaces with the suite's network instrument (\`E2E.md\` § Suite names it) attached before the first \`goto\` — a GraphQL \`200\` carrying an \`errors[]\` body is the failure mode that looks like a working page.
3. Write exploratory work as a probe in the suite's probe folder (\`E2E.md\` § Suite) — probes log, they never assert. A probe that pins real behaviour gets **promoted** into the suite's role folder, tagged \`@${TICKET}\` in the suite's tag format. Keep both; they are the record that a state was checked.
4. Take a screenshot with the suite's helper at every moment that evidences a finding, and at the ones that evidence a clean state. Name each after what it shows, never \`screenshot-1\`.
5. **Reproduce before you report.** Re-run the scenario once. A wall of \`ERR_CONNECTION_REFUSED\` is a dead frontend dev server, not a wall of defects, and it degrades after heavy seeding and route interception — restart it and re-run before you read anything into a large failure count.
6. Assert outcomes through the backend, with the seed client's reads (\`E2E.md\` § Suite), not through chips the frontend hardcodes.

RULES

- **You do not fix.** A defect is a finding with a severity, a \`file:line\` in the repo responsible, and a scenario that reproduces it. The developer patches it in the next phase, and you re-drive it after. Naming the wrong file is worse than naming none — if you cannot locate it, say so in \`fix\` and leave \`file\` as the probe.
- **Log the clean scenarios too**, in \`scenarios\` with \`verdict: "clean"\`. A hunt that reports only breaks cannot be told apart from a hunt that stopped early, and the clean list is what the evidence folder is for.
- Severity is about the user, not the code: \`BLOCKER\` = wrong data, lost work, or a persona seeing what it must not; \`MAJOR\` = the feature does not do its job in a reachable state; \`MINOR\`/\`NIT\` = wrong copy, cosmetic, or a state nobody hits.
- Do not commit and do not push. The command owns git.

Return via the StructuredOutput tool.`,
      {
        label: `hunt:${family.name}-r${round}`,
        phase: 'Hunt',
        schema: HUNT_SCHEMA,
        agentType: 'qa-e2e',
      },
    );

    if (!result) {
      log(`round ${round}: the ${family.name} hunter returned no verdict — recorded as not run, hunt continues`);
      huntResults.push({ verdict: 'NOT_RUN', family: family.name, scenarios: [], findings: [], screenshots: [], artifacts_written: [], summary: 'agent returned no verdict' });
      continue;
    }

    huntResults.push(result);
    const fresh = result.findings.filter((f) => {
      const k = keyOf(f);
      if (seen.has(k)) return false;
      seen.add(k);
      return true;
    });
    fresh.forEach((f) => allFindings.push(f));
    freshThisRound += fresh.length;
    log(
      `round ${round} · ${family.name}: ${result.verdict} — ${result.scenarios.length} scenario(s), ${fresh.length} new finding(s)`,
    );
  }

  lastHunts = huntResults;

  const ranAtAll = huntResults.some((h) => h.verdict !== 'NOT_RUN');
  if (!ranAtAll) {
    aborted = `Every hunter on round ${round} came back NOT_RUN: the stack could not be driven, so nothing about this feature was verified. Fix the stack and re-run — do not read a clean result into a hunt that never happened. Hunter reasons: ${huntResults
      .map((h) => h.summary)
      .join(' | ')}`;
    history.push({ round, stage: 'hunt', hunts: huntResults, fix: null, gate: null, verify: null });
    break;
  }

  // Triage is arithmetic: dedupe already happened, so this is the severity split.
  const outstanding = allFindings.filter((f) => !fixedIds.has(f.id) && !unfixed.some((u) => u.finding_id === f.id));
  const toFix = outstanding.filter((f) => FIXABLE.indexOf(f.severity) !== -1);
  const recordedOnly = outstanding.filter((f) => FIXABLE.indexOf(f.severity) === -1);

  if (recordedOnly.length) {
    log(
      `round ${round}: ${recordedOnly.length} ${FIX_MINOR ? 'NIT' : 'MINOR/NIT'} finding(s) recorded, not patched — pass --fix-minor to include them`,
    );
    // Recorded with a reason, not silently dropped: the evidence folder has to be able to
    // say why a finding it lists was left alone, and "below the fix threshold" is a
    // decision this run made rather than something the hunter observed.
    recordedOnly.forEach((f) => {
      if (!unfixed.some((u) => u.finding_id === f.id)) {
        unfixed.push({
          finding_id: f.id,
          why: `${f.severity} is below this run's fix threshold (${FIXABLE.join('/')}) — reported, not patched`,
          needs: 'a decision, or a re-run with --fix-minor',
        });
      }
    });
  }

  if (NO_FIX) {
    history.push({ round, stage: 'hunt', hunts: huntResults, fix: null, gate: null, verify: null });
    // Report-only, so there is no fix stage for a round to be spent on. `--rounds N` therefore
    // buys DEPTH instead: hunt again, with everything already found in the prompt as
    // "do not re-report these, hunt past them", until a round turns up nothing new or the
    // budget runs out. Loop-until-dry, not a fixed count — a simple counter stops mid-tail,
    // and re-running a family that produced nothing new is the cheapest coverage left.
    const dry = freshThisRound === 0;
    if (dry || round >= MAX_ROUNDS) {
      converged = true;
      toFix.forEach((f) => unfixed.push({ finding_id: f.id, why: '--no-fix: reported for a human to decide' }));
      log(
        dry
          ? `--no-fix: round ${round} turned up nothing new — the hunt is dry after ${allFindings.length} finding(s)`
          : `--no-fix: round budget (${MAX_ROUNDS}) spent with round ${round} still finding new defects — there is more here`,
      );
      break;
    }
    log(
      `--no-fix: round ${round} found ${freshThisRound} new defect(s); hunting again past all ${allFindings.length} of them`,
    );
    // Every family again, not just the ones that broke: under --no-fix nothing changed in the
    // trees between rounds, so a family that came back clean is still worth a second, better-
    // informed pass — the hunters now know what the others found.
    familiesThisRound = families;
    continue;
  }

  if (!toFix.length) {
    converged = true;
    history.push({ round, stage: 'hunt', hunts: huntResults, fix: null, gate: null, verify: null });
    log(
      `round ${round}: nothing left to fix at ${FIXABLE.join('/')} severity — the hunt converged after ${round} round(s)`,
    );
    break;
  }

  // ---- Fix. One writer per repo, and the repos go one at a time: two developers in one
  // ---- tree race on the same files, and a frontend fix routinely pairs with a backend fix.
  phase('Fix');

  const repos = [];
  toFix.forEach((f) => {
    if (repos.indexOf(f.repo) === -1) repos.push(f.repo);
  });

  const fixes = [];
  for (let i = 0; i < repos.length; i += 1) {
    const repo = repos[i];
    const mine = toFix.filter((f) => f.repo === repo);
    const elsewhere = toFix.filter((f) => f.repo !== repo);

    const fix = await agent(
      `Read \`ai-brain/.claude/agents/developer.md\` and follow it in full — it is your role definition. Read \`${repo}/CLAUDE.md\` before you edit anything in it.

${WORKSPACE}

You are fixing defects a browser bug hunt found in **${TICKET}**, round ${round}. **You edit \`${repo}\` and nothing else** — another agent owns the other repos this round, and two writers in one tree lose each other's work.

${scopeContext}

${CTX}${gateFailureNote ? `${gateFailureNote}\n\n` : ''}FINDINGS ASSIGNED TO YOU (in \`${repo}\`):
${renderFindings(mine)}

${elsewhere.length ? `FOR CONTEXT ONLY — being fixed in parallel by another agent, do not touch them:\n${renderFindings(elsewhere)}\n` : ''}
HOW TO FIX

1. **Reproduce the cause in the code before you edit.** The hunter saw a browser; it inferred the file. Confirm the \`file:line\` explains the observed behaviour, and if it does not, fix the real cause and say so in \`root_cause\` — a patch at the wrong layer passes the verify pass and breaks something else next sprint.
2. **Fix the cause, not the symptom.** Do not hide a defect behind a guard on the surface the hunter happened to use. If the same wrongness is reachable from a second surface, fix it once and say where.
3. **Add the regression test in the owning repo**, not only in Playwright: an RSpec example for a backend fix, a Jest test for a frontend fix. Name it in \`tests_added\`. A browser-only proof leaves nothing behind for CI.
4. **Do not touch the Playwright repo.** The hunter owns the specs and probes there.
5. Scope discipline: fix what is listed. A defect you notice outside these findings is worth reporting in \`summary\` — it is not yours to patch in this round, because nothing has hunted it and nothing will verify it.
6. Where a finding cannot be fixed — it needs a schema change, a seeder that does not exist, a product decision — put it in \`not_patched\` with what it needs. An honest \`not_patched\` is better than a patch nobody can verify.
7. Do not commit and do not push. The command owns git.

Return via the StructuredOutput tool.`,
      {
        label: `fix:${repo}-r${round}`,
        phase: 'Fix',
        schema: FIX_SCHEMA,
        agentType: 'developer',
      },
    );

    if (!fix) {
      log(`round ${round}: the developer for ${repo} returned no report — its findings stay open`);
      mine.forEach((f) => unfixed.push({ finding_id: f.id, why: `the developer agent for ${repo} returned no report` }));
      continue;
    }
    fixes.push({ repo, fix });
    fix.not_patched.forEach((n) => unfixed.push(n));
    log(
      `round ${round} · ${repo}: ${fix.patched.length} patched, ${fix.not_patched.length} left open, ${fix.tests_added.length} test(s) added`,
    );
  }

  gateFailureNote = '';

  const patched = fixes.flatMap((f) => f.fix.patched);
  if (!patched.length) {
    history.push({ round, stage: 'fix', hunts: huntResults, fix: fixes, gate: null, verify: null });
    aborted = `Round ${round} found ${toFix.length} fixable defect(s) and patched none. Nothing further will change on another round — read the \`not_patched\` reasons and decide by hand.`;
    break;
  }

  // ---- Gate. Once, centrally, on the repos the fixes touched.
  phase('Gate');

  const gate = await agent(
    `You are the gate for a bug-hunt fix round in this workspace. Run the checks once and report exactly what happened. You do not review code and you do not edit files.

${WORKSPACE}

The fixes for **${TICKET}** round ${round} are uncommitted in these repos: ${repos.map((r) => `\`${r}\``).join(', ')}. Determine \`repos_touched\` yourself from \`git -C <repo> status --porcelain\` rather than trusting that list, then run each touched repo's gate from \`ai-brain/profile/REPOS.md\` § Gates:

- Rails services and the monolith: \`bundle exec rubocop\` **scoped to the .rb files the diff touches** — \`files=$(git status --porcelain | awk '{print $NF}' | grep '\\.rb$'); [ -n "$files" ] && bundle exec rubocop $files\` — then \`bundle exec rspec\` **scoped to the specs the diff touches**. Record the scope you used in \`evidence\` for both: a scoped green run reported as "the suite passed" is a false gate. Never run rubocop repo-wide on a repo \`REPOS.md\` § Gates says carries a pre-existing baseline — a repo-wide run there is red on a clean tree.
- The frontends and the shell: the lint, type-check and test commands \`REPOS.md\` § Gates names for each.
- \`${PLAYWRIGHT}\`: its type-check only. The suite belongs to the hunters; do not run it here — it would fight the browser pass that follows.
- \`ai-brain\`: no gate; its \`sprints/\` write-up is docs. Record \`skipped\` with that reason.

Never guess a result. \`skipped\` and \`not_run\` are honest; a smoothed-over gate is not.

Return via the StructuredOutput tool.`,
    {
      label: `gate:r${round}`,
      phase: 'Gate',
      schema: GATE_SCHEMA,
      agentType: 'general-purpose',
      effort: 'low',
    },
  );

  if (gateFailed(gate)) {
    const failed = gate.checks.filter((c) => c.result === 'fail');
    log(`round ${round}: gate failed (${failed.map((c) => `${c.repo}:${c.name}`).join(', ')}) — next round starts there`);
    history.push({ round, stage: 'gate', hunts: huntResults, fix: fixes, gate, verify: null });
    // A red gate means the fix is not ready for a browser: re-hunting now would grade a
    // tree that does not compile. Next round goes straight back to the developer.
    repairOnly = true;
    gateFailureNote = `THE GATE WENT RED ON THE LAST FIX ROUND. Fix these first; they are your own patch failing its repo's own checks, not a new browser finding:\n${failed
      .map((c) => `- ${c.repo} · ${c.name}: ${c.evidence}`)
      .join('\n')}`;
    continue;
  }

  // ---- Verify. Serial, one agent, in the browser. A fix is a claim until this passes.
  phase('Verify');

  const verify = await agent(
    `Read \`ai-brain/.claude/agents/qa-e2e.md\` and follow it in full — it is your role definition.

${WORKSPACE}

You are the verify pass for round ${round} of the bug hunt on **${TICKET}**. Developers have patched the findings below. **A fix is a claim until you have re-driven it in a browser** — re-run each finding's own scenario, on the same surface, as the same persona.

${SERIAL_RULE}

${scopeContext}

${renderGate(gate)}

${CTX}WHAT WAS PATCHED, AND THE SCENARIO THAT FOUND IT:
${patched
  .map((p) => {
    const f = allFindings.filter((x) => x.id === p.finding_id)[0];
    return `- **${p.finding_id}** in \`${p.repo}\` — files: ${p.files.map((x) => `\`${x}\``).join(', ')}\n  - root cause the developer names: ${p.root_cause}\n  - what changed: ${p.what_changed}\n  - the scenario to re-drive: ${f ? f.scenario : '(finding not in the register — say so)'}\n  - what was observed before: ${f ? f.observed : 'unknown'}\n  - what should happen now: ${f ? f.expected : 'unknown'}`;
  })
  .join('\n')}

HOW TO VERIFY

1. Re-run the ticket-tagged specs first — the suite's tag filter (\`ai-brain/profile/E2E.md\` § Suite) for \`@${TICKET}\` — plus the promoted specs from this hunt.
2. Then re-drive each scenario yourself. \`fixed\` needs the browser to show the expected behaviour; \`still_broken\` needs what you saw instead; \`not_reachable\` needs the obstacle. Do not mark a finding \`fixed\` off a green spec that does not exercise it.
3. **Hunt the patch, not just the finding.** A fix that hides a state is a new defect: check the states around it — the persona now denied, the empty case, the value the guard rejects — and report anything new in \`regressions\` with the same severity vocabulary. Regressions from a fix are the highest-value thing this pass can find.
4. Capture a screenshot per verified finding, named after the finding id and what it shows.
5. Restart the suite's frontend dev server (\`E2E.md\` § Suite) before trusting any failure that arrives in a cluster: it degrades after repeated seeding and route interception.
6. You do not fix, and you do not commit.

Return via the StructuredOutput tool.`,
    {
      label: `verify:r${round}`,
      phase: 'Verify',
      schema: VERIFY_SCHEMA,
      agentType: 'qa-e2e',
    },
  );

  history.push({ round, stage: 'verify', hunts: huntResults, fix: fixes, gate, verify });

  if (!verify || verify.verdict === 'NOT_RUN') {
    aborted = `Round ${round}'s verify pass ${verify ? 'could not run' : 'returned nothing'}, so ${patched.length} patch(es) are unverified. They are in the trees and they may be wrong: ${
      verify ? verify.summary : 'the agent returned no verdict'
    }`;
    break;
  }

  verify.verified.forEach((v) => {
    if (v.status === 'fixed') fixedIds.add(v.finding_id);
    else unfixed.push({ finding_id: v.finding_id, why: `${v.status}: ${v.evidence}` });
  });

  const fresh = verify.regressions.filter((f) => {
    const k = keyOf(f);
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
  fresh.forEach((f) => allFindings.push(f));

  const stillBroken = verify.verified.filter((v) => v.status !== 'fixed');
  log(
    `round ${round}: verify ${verify.verdict} — ${verify.verified.filter((v) => v.status === 'fixed').length} fixed, ${stillBroken.length} not, ${fresh.length} regression(s)`,
  );

  if (verify.verdict === 'PASS' && !fresh.length && !stillBroken.length) {
    converged = true;
    break;
  }

  // Next round re-hunts only where something is still wrong.
  const openNow = allFindings.filter((f) => !fixedIds.has(f.id));
  familiesThisRound = families.filter((f) => openNow.some((o) => o.family === f.name));
  if (!familiesThisRound.length) familiesThisRound = families;
}

// ---------------------------------------------------------------------------
// Evidence — mandatory. This runs on every exit path that got as far as a hunt,
// including an aborted one: the folder is the deliverable, and a run that found
// nothing still has to prove which states it drove.
// ---------------------------------------------------------------------------

const fixedFindings = allFindings.filter((f) => fixedIds.has(f.id));
const openFindings = allFindings.filter((f) => !fixedIds.has(f.id));
const allScenarios = history.flatMap((h) => (h.hunts || []).flatMap((x) => x.scenarios || []));
const allShots = history.flatMap((h) =>
  (h.hunts || []).flatMap((x) => x.screenshots || []).concat(h.verify ? h.verify.screenshots : []),
);

phase('Evidence');

const evidence = await agent(
  `Read \`ai-brain/.claude/agents/qa-e2e.md\` for your boundaries — **you write inside \`${PLAYWRIGHT}\` and nowhere else.** You are not hunting now; you are writing the record of a hunt that has finished.

${WORKSPACE}

Write the evidence folder for the bug hunt on **${TICKET}**, run ${TODAY}.

\`\`\`
${EVIDENCE_DIR}/
├── notes.md        what this is, when, which specs and probes, the screenshot table, how to refresh
├── bug-hunt.md     the hunt log: every scenario with its verdict, every finding, what was fixed
└── <named>.png     the screenshots, named after what they show
\`\`\`

**This folder is written whether or not anything broke.** A hunt that found nothing is a result, and the scenario list is the only record that those states were ever driven. Mirror the model \`notes.md\` that \`ai-brain/profile/E2E.md\` § Evidence names — a title line, what the feature is in plain words, the spec and doc pointers, the capture conditions (date, stack, seeded client/employee, timezone), a screenshot table, and a \`## Refresh\` block with the exact commands.

\`notes.md\` carries: the feature in two or three sentences, the specs and probes this hunt added or promoted, the plan doc under \`ai-brain/sprints/\` if one exists (\`ai-brain/bin/plan-doc path <KEY>\`; do not invent a path), \`Captured: ${TODAY}\`, and the refresh commands.

\`bug-hunt.md\` carries, in this order:

1. **Verdict** — one paragraph a reviewer can read instead of the file. ${converged ? 'The loop converged.' : 'The loop did NOT converge — say so first.'}${aborted ? ' It was cut short; the reason is below and it belongs at the top of this file.' : ''}
2. **Scope and environment** — the repos, branches and SHAs under test (\`git -C <repo> rev-parse --short HEAD\`), the stack (the services and ports \`E2E.md\` § Suite names, the seeded accounts), and the browser-local vs server date if they differ.
3. **Scenarios driven** — every one, with its verdict, INCLUDING the clean ones and the blocked ones. This is the table that makes the run auditable:
${allScenarios.length ? allScenarios.map((s) => `   - [${s.verdict}] ${s.name} — ${s.what_i_did}${s.note ? ` (${s.note})` : ''}`).join('\n') : '   - (no scenarios were recorded — say that plainly)'}
4. **Findings fixed in this run** — each with severity, \`file:line\`, what was observed, the root cause, what changed, and how the verify pass confirmed it:
${fixedFindings.length ? renderFindings(fixedFindings) : '   - none'}
5. **Findings still open** — each with severity, \`file:line\`, the reproduction, and why it was not fixed:
${openFindings.length ? renderFindings(openFindings) : '   - none'}
${unfixed.length ? `   Reasons recorded by the loop:\n${unfixed.map((u) => `   - ${u.finding_id}: ${u.why}`).join('\n')}\n` : ''}6. **What this hunt could not reach**, and why:
${scope.unreachable.length ? scope.unreachable.map((u) => `   - ${u.what} — ${u.why}`).join('\n') : '   - nothing recorded'}
7. **Specs and probes left behind** — paths, and one line each on what they pin. Probes are kept, not deleted.

Screenshots the hunters captured, to copy in from \`${PLAYWRIGHT}/test-results/\` — copy what exists, and list in \`missing\` anything you were told about but could not find:
${allShots.length ? allShots.map((s) => `- ${s}`).join('\n') : '- (none reported)'}

Rules: no praise, no invented paths, no screenshot renamed to look like a criterion it does not show. Where a fact is not available to you — a SHA, a seeded id — write what you checked and that it was unavailable, rather than a plausible value. Do not commit and do not push.

Return via the StructuredOutput tool.`,
  {
    label: 'evidence',
    phase: 'Evidence',
    schema: EVIDENCE_SCHEMA,
    agentType: 'qa-e2e',
  },
);

// The user's invariant for this command is that the folder exists afterwards. Trusting the
// writer's own word on that is exactly the mistake /dev's "no plan, no build" rule
// exists to prevent, so it is checked on disk, cheaply, by someone else.
phase('Evidence check');

const evidenceCheck = await agent(
  `Check on disk, and report only what \`ls\` and \`head\` show you. Do not create anything and do not fix anything.

\`\`\`
ls -la ${EVIDENCE_DIR}
head -30 ${EVIDENCE_DIR}/notes.md
head -40 ${EVIDENCE_DIR}/bug-hunt.md
\`\`\`

Report: whether the folder exists, whether \`notes.md\` exists and is non-empty, whether \`bug-hunt.md\` exists and is non-empty, how many image files are in it, and the full file list. If a file is missing or empty, say so plainly — this check exists because "the evidence was written" is a claim the run must not take on trust.

Return via the StructuredOutput tool.`,
  {
    label: 'evidence-check',
    phase: 'Evidence check',
    schema: EVIDENCE_CHECK_SCHEMA,
    agentType: 'general-purpose',
    effort: 'low',
  },
);

if (evidenceCheck && (!evidenceCheck.folder_exists || !evidenceCheck.notes_exists || !evidenceCheck.hunt_log_exists)) {
  log(`the evidence folder at ${EVIDENCE_DIR} is incomplete — the command must not report this run as recorded`);
}

return {
  ticket: TICKET,
  today: TODAY,
  converged,
  aborted,
  rounds: round,
  maxRounds: MAX_ROUNDS,
  fixPolicy: NO_FIX ? 'report-only (--no-fix)' : `patch ${FIXABLE.join('/')}`,
  scope,
  families: families.map((f) => f.name),
  scenariosDriven: allScenarios.length,
  scenariosClean: allScenarios.filter((s) => s.verdict === 'clean').length,
  scenariosBlocked: allScenarios.filter((s) => s.verdict === 'blocked').length,
  findings: allFindings,
  fixed: fixedFindings.map((f) => f.id),
  open: openFindings.map((f) => ({ id: f.id, severity: f.severity, where: `${f.repo}/${f.file}:${f.line}`, problem: f.observed })),
  notFixedReasons: unfixed,
  evidence,
  evidenceCheck,
  evidenceDir: EVIDENCE_DIR,
  history: history.map((h) => ({
    round: h.round,
    stage: h.stage,
    hunts: (h.hunts || []).map((x) => `${x.family}:${x.verdict}(${x.findings.length})`).join(' '),
    fix: h.fix ? h.fix.map((f) => `${f.repo}:${f.fix.patched.length}p/${f.fix.not_patched.length}o`).join(' ') : null,
    gate: h.gate ? h.gate.checks.map((c) => `${c.repo}/${c.name}:${c.result}`).join(' ') : null,
    verify: h.verify ? h.verify.verdict : null,
  })),
};
