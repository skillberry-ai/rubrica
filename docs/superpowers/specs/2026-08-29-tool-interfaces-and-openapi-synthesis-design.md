# Tool interfaces, discovered and captured as OpenAPI

## Why

[`2026-08-19-simulated-lab-environment-design.md`](2026-08-19-simulated-lab-environment-design.md)
proposed a lab: an environment where the agent under test exercises its real
tools against a world we control, so a scenario's expected trajectory can
actually be observed. It has two enhancements — interfaces in the world model,
and standing a lab up from them — and neither was ever planned or implemented.

This is the first step of the first enhancement, taken on its own so that its
output is reviewable before anything depends on it. At the end of it a run
describes the tools its target declares, groups them into the services a
simulator would stand in for, and carries one OpenAPI document per service that
a human reads at gate 1. Nothing consumes that description. Coverage arithmetic
is untouched, no simulation is generated, and a run that ignores all of it
behaves exactly as it does today.

That is the point. The lab design's own risk register says a wrong specification
"fails silently downstream" and that "nothing in the run detects this; only Gate
1 review does". Shipping the description before shipping any consumer of it
means the first thing that happens to a synthesised specification is that
somebody reads it.

## What this step is, and what it is not

The enhancement has seven pieces. This step takes five of them, and takes the
fifth in its declared-contract form only.

| # | Piece | Here |
|---|---|---|
| 1 | `extract` gains a claim subject: the tools the target declares | yes |
| 2 | Tools grouped into **services**, as a judgment with evidence | yes |
| 3 | Containment as **signals with locators**, never a `contained` boolean | yes |
| 4 | One OpenAPI document per service, synthesised backwards from the tool contract | yes |
| 5 | `responses` inferred from observed tool results in trajectories | **no** — declared contracts only |
| 6 | Gate 1 gains a per-service section, and a human selects | the section, not the selection |
| 7 | Unsimulatable services shrink the coverage `denominator` | **no** |

Piece 6 splits cleanly because `rubrica decide` already appends a decision to
`decisions.md` for any reason a human has. Recording a selection therefore needs
no new machinery; what this step omits is anything that *reads* one. Piece 7
depends on a selection being read, so it follows piece 6, not this step.

Piece 5 is deferred rather than dropped, and the reason it is safe to defer is a
measurement recorded in the next section.

## What re-verification changed

All four properties the lab design rests on were re-checked against
`simulation-harness` at `1c3b210` (`v0.1.1-2-g1c3b210`), and all four hold: no REST routes
are mounted for simulated operations (`add_api_route` appears nowhere in its
source), a second create still returns 409, `sanitize_operation_id(raw, *,
method, path)` is unchanged at `openapi/parser.py:25`, and
`startup.autostart_enabled` still lets a container boot straight into serving a
baked skill.

One claim did not hold, and correcting it is what makes this step's scope
defensible. The lab design says a specification without `responses` "risks not
generating at all", because generation "fails outright when no entity can be
derived". The failure branch it cites is real —
`skills/generation/stages/analyze/__init__.py:95` raises when `dm.entities` is
empty — but the fallback immediately above it is not mentioned.
`inline_schema_evidence` (same file, line 44) exists, in its own words, to
"synthesize a `name -> JSON schema` map from operation request/response bodies,
for RPC/tool-style specs that declare no `components.schemas`". It feeds
**request** bodies as entity evidence alongside responses, and `_op_context`
in the operations stage treats `response_schema` as optional at every use. It
landed on 2026-06-29, so it predates the lab design; the design read the raise
and not the branch that avoids it.

So a request-only document — exactly what backwards synthesis produces from a
tool contract — is not a degraded input the harness might tolerate. It is a
shape the harness was deliberately built to accept, and generation fails only
when *neither* request nor response evidence exists, which backwards synthesis
cannot produce: the requestBody is the agent's own input schema by
construction.

Response inference remains worth having, for the reason the lab design gives —
the state store's shape is otherwise inferred from inputs rather than from what
a tool returns, which is a fidelity loss. It is no longer close to a
precondition, and this step does not need it.

## The shape

Two new stages. The `01a`–`01i` dir letters are editorial — they appear in
`CLAUDE.md`, `docs/concepts/pipeline.md` and `scripts/render-pipeline-diagram.py`,
while on disk the parts are plain `01-<name>.json` — so this costs a re-render
and three table edits, not a migration.

| Dir | Stage | Runs as | Writes | Gate |
|---|---|---|---|---|
| `01i` | `reconcile-services` | `rb-reconcile-services` — barrier | `01-services.json` | validate · check-refs |
| `01j` | `synthesise-interfaces` | code — `rubrica synthesise-interfaces` | `01-interfaces/<service_id>.json` | validate · check-refs |
| `01k` | `reconcile-seal` | code, job unchanged | `01-world-model.json` | validate · check-refs · **human gate 1** |

`01j` is the only row in that block that does not *merge* claims into a
partial. It derives one document per service from `01-services.json`, reading
`01-claims/` solely to resolve the input schema each operation carries — so the
barrier property the family rests on is not its property at all; its inputs are
already sealed by the pass above it. `CLAUDE.md`'s and `pipeline.md`'s statement
that rows `01b` through `01i` are one logical step engineered as substeps, split
on *output* rather than on claims, is amended to name that row for what it is,
rather than silently widened to cover a derivation. A derivation hiding inside a
family of merge rows is precisely the kind of quiet inaccuracy this project pays
for two commits later.

Synthesis is its own stage rather than folded into `reconcile-seal` for one
reason that outweighs the cost of a longer `STAGES`: a human at gate 1 who
corrects a grouping wants to re-read the affected document, and should not have
to re-run the seal over seven partials to do it. It is separately runnable by
hand, and it gets its own `validate` gate.

The world model gains **`services`, optional**. Optional is a ruling, not a
shortcut: a run whose target declares no tools has nothing to say and should not
be made to say it, and an optional key leaves both committed live recordings
(`tests/fixtures/toy-contradiction/recorded/01-world-model.json` and the
`toy-gap` twin) valid, so this step obliges no re-record and spends nothing
live. A required key would have invalidated the only behavioural evidence the
refusal conditions have.

A service's OpenAPI document is **not** folded into the world model. It stays a
file under `01-interfaces/`, and its path is derivable from the service id, so
there is no path field in the world model to drift out of agreement with the
directory. The reasons are that an inlined document would bloat an artifact
whose byte-identity is load-bearing, and that the harness consumes a file.

## The claim kind, and the one prompt-carried fidelity requirement

`extract` gains a seventh kind, `tool`: one claim per tool the target declares.
`statement` is prose about what the tool is for, `payload` carries the tool's
input schema **verbatim**, and `evidence[].locator` is the JSON pointer the
schema was copied from.

The payload has to be there. Synthesis reads `01-services.json` and
`01-claims/`; it does not read `00-inputs/`, because the stage that reads inputs
is `extract` and threading a second reader through the pipeline would put the
same bytes behind two different readings. So the input schema reaches synthesis
through a claim or it does not reach it at all.

That makes this step's sharpest risk a prompt transcribing a JSON schema byte
for byte, with every downstream fidelity property resting on it. The mitigation
is a check rather than a hope, and it is available because `refs.check_inputs`
(`refs.py:1303`) already re-hashes every file in `00-inputs/` against
`manifest.inputs[].sha256` on each `check-refs` call. Layer 2 reading raw input
bytes is therefore precedented, not novel: the new check re-reads the input at
the recorded pointer and compares it to the claim's payload.

This does not weaken the rule that layer 2 checks whether an element
*references* a resolvable claim and never whether the claim *supports* it.
Support is semantic. Byte-for-byte identity between a payload and the document
region it names is structural, mechanically decidable, and exactly the class of
property layer 2 exists for. It converts the one unobservable step in this
design into a finding.

## Backwards synthesis is code, not a prompt

`operationId` is the agent's own tool name. The requestBody schema is the tool's
input schema. Path and method are carriers, assigned by a fixed convention. That
is a pure function of the tool contract, so two runs with identical groupings
must produce byte-identical documents — otherwise a difference in an emitted lab
can no longer be attributed to a stage. It is `emit`'s argument and
`reconcile-seal`'s argument without modification, which is why the lab design's
"a new stage writes one OpenAPI document" per service needs neither a prompt nor
a fan-out.

The golden fixture supplies the awkward case and the convention resolves it with
no judgment call. `tests/fixtures/toy/api.json` declares one tool,
`query_tickets`, whose `input_schema` carries an `action` enum dispatching two
behaviours (`find_tickets`, `get_ticket`). Backwards synthesis emits **one**
operation, `operationId: query_tickets`, whose requestBody is the entire input
schema including the enum — because one tool is what the agent sees, and the
substitution is invisible to the agent's reasoning only if that contract
survives intact. Splitting it into two operations would be a more natural REST
document and a broken contract.

A tool name that the harness's sanitisation would alter cannot have its contract
preserved. Rather than rename it and lose the property silently, that is a
finding at gate 1 and the service is not simulatable as it stands.

The survival predicate is **not** the character class alone, and getting this
wrong is the easy mistake. `sanitize_operation_id` replaces any character
outside `[a-zA-Z0-9_-]` with `_`, caps the result at 64, *and* strips leading and
trailing `_` and `-` — twice, before and after the cap. So `_query_tickets`
matches `^[a-zA-Z0-9_-]{1,64}$` and is still altered, to `query_tickets`, and a
check written as that character class would wave through exactly the silent
contract break it exists to catch. The predicate is therefore
`^[a-zA-Z0-9](?:[a-zA-Z0-9_-]{0,62}[a-zA-Z0-9])?$`: one to sixty-four characters
from the permitted set, neither first nor last a separator.

It is restated here as a regex rather than imported, so Rubrica takes no
dependency on `simulation-harness` — whether the harness accepts a document is
the harness's test, not ours. The cost of restating is that the two can drift,
which the skill's prose names: the predicate cites the harness function it
mirrors, so a reader who finds them disagreeing knows which one is the copy.

`interface-0.1.json` pins the carrier convention and the provenance we rely on:
one path per tool, `operationId` present, a requestBody schema present, and an
`x-rubrica` block naming the service and the `tool` claims each operation came
from. It does not attempt to be an OpenAPI validator.

## Grouping and the signals are where the judgment is

`rb-reconcile-services` is a barrier: it reads every file in `01-claims/` and
writes `01-services.json`. Two things in it are judgments, and both are
recorded with evidence rather than asserted.

**Grouping.** Two tools share a service when they address the same backend, and
the admissible evidence is a shared base URL, a shared client construction, a
shared credential, or a shared MCP server entry. The grouping determines how
many simulators exist, and a wrong split gives two tools disjoint databases so
that an entity created through one is invisible to the other — which is why it
is reviewable at gate 1 rather than derived.

**Signals, never a verdict.** No `contained` boolean is computed, because that
is the one place the pipeline would assert a certainty it cannot support. Each
service carries signals from a closed set, each with an evidence locator: a
remote MCP server is configured for these tools; an HTTP client or SDK is
constructed in the implementation; a credential or base-URL environment
variable is read; a network-capable dependency is imported; **no
outward-facing evidence was found in the artifacts that were read**. The last
is phrased as absence of evidence on purpose. A tool that looks self-contained
but holds a hidden call produces a suite that passes in the lab and fails in
production, and that asymmetry means uncertainty must never read as
"contained".

**One tool declared by two inputs.** A tool can be declared in an `api.json`
and observed again in a trace, so two `tool` claims can name it. They are two
pieces of evidence for one operation, not two operations, so a service's
`tools[]` entry carries a name and *one or more* claim ids. Where those claims
disagree about the input schema — which is a real case, not a hypothetical, since
a declared contract and an observed call need not match — synthesis cannot
choose: it is deterministic, and a rule for picking a winner would bury a
judgment in code. So the entry also names a `schema_claim`, the one claim whose
payload becomes the operation's requestBody, and choosing it is the pass's
recorded judgment. Its refusal condition is the matching one: where two claims
give different input schemas for one tool, name the disagreement in the service
record and pick the declared contract, never silently the first one read.

Under this step's declared-contract scope only the first and the last of those
five signals are reachable, and `docs/design/limitations.md` says why the other three
are not: no run has ever filed a claim from a source file, and only Python has a
source parser — `.ts`, `.tsx`, `.js`, `.go`, `.rs`, `.java` and `.rb`
candidates reach triage as `lines`, a `body_head` and `unsupported_language`.
The skill's prose states that the three source-derived signals exist and that
their absence from a run is not evidence about the tools, so a reader at gate 1
is not invited to read a short signal list as reassurance.

## What `check-refs` adds

All mechanical, and named rather than numbered because the set will grow with
the steps below this one:

- **Every claim id in `01-services.json` resolves** to a `tool` claim in
  `01-claims/`, and each tool's `schema_claim` is one of its own claim ids —
  not a sibling tool's, and not a claim of some other kind.
- **Every `tool` claim is referenced by exactly one service.** A partition, so
  neither an orphaned tool nor a tool claimed by two services passes.
- **Exactly one document per service** in `01-interfaces/`, and nothing else in
  that directory.
- **Each document's set of `operationId`s equals its service's tool names,**
  byte for byte. This is contract preservation made mechanical, and it is the
  check the rest of the lab design rests on.
- **Every tool name survives sanitisation unchanged**, by the predicate above
  rather than by the character class.
- **Every `schema_claim`'s payload equals the input document** at the pointer its
  evidence records.

The two document-level checks report every missing or mismatched document from
the moment `01-interfaces/` exists, so like `check_verdicts` and
`check_contradiction_parts` they are meaningful only once synthesis has
finished. `refs.check_all` runs every checker the run has inputs for, which is
why there is no stage-scoped `check-refs` to hang them off.

## Gate 1's surface

`gate-brief` gains a section per service: its tools, its signals each with a
locator, the path to its synthesised document, and `derivation`. Every service
in this step is `stated`; `reverse_engineered` arrives with response inference.

`gate-brief` remains a report, not a gate: it exits clean on a readable run. It
composes what already exists, and every number in the new section is recomputed
from the artifacts rather than read out of a field a stage wrote.

Nothing consumes what the human decides. That is the boundary of this step, and
it is stated in the brief so a reader is not left believing a selection they
record will change the run.

## What must not break

- **The exit-code contract.** `synthesise-interfaces` is new code with an
  unreadable-input surface: a missing or non-dict `01-services.json`, an
  unwritable `01-interfaces/`, a `service_id` that is not a safe path segment.
  Each is a stage defect and must arrive as exit 1 with a finding per line, never
  as 2 and never as a 1 with empty stdout. The `service_id` case follows
  `check_inputs`' handling of `stored_as`: validate the segment rather than
  joining it blindly, because `paths` raises `UnsafeSegment`, which `cli.py`
  maps to 2 — and a bad value in a stage's own output is repairable, so it owes
  a finding instead.
- **Both live recordings stay valid**, which the optional `services` key
  guarantees. Neither fixture's recording is re-recorded in this step.
- **`rb-extract`'s refusal prose.** "Record it under the closest of the six" and
  "do not invent a seventh kind" become the seven and the eighth. The same count
  appears at `refs.py:1947`, `tests/toy.py:448` and
  `docs/reference/artifacts.md:326`. A partial sweep leaves the repo asserting
  two different enum sizes.
- **`PASS_OWN_KINDS` gains `("services_part", ("tool",))`,** or the new pass is
  invisible to gate 1's per-pass read coverage — the accounting that exists
  because a pass's read of `01-claims/` was measured varying 3/23 to 23/23
  across byte-identical dispatches.
- **No dependency on `simulation-harness`** from Rubrica's source, tests or
  lockfile.

## Testing

- Every text-level predicate measured in **both** directions, in a `/tmp` copy
  under `RUBRICA_SKILLS_DIR`: blank the prose it claims to check and watch it go
  red, then reword that prose meaning-preservingly and watch it stay green.
  Scope each assertion with `skills.section_body`, never a substring over
  `body` — the five mandatory headings make an unscoped `"signal" in body`
  vacuous.
- One negative case per check: a tool in two services, an orphaned tool, a
  `schema_claim` naming a sibling tool's claim, an extra file in
  `01-interfaces/`, a document whose `operationId` was altered, and a payload
  edited away from the input it cites.
- Two sanitisation cases, because the character class alone passes one of them:
  a name carrying a character the harness would replace, **and** `_query_tickets`,
  which the character class admits and the harness would still rewrite. The
  second is the regression test for the predicate, and it is the case the first
  draft of this design got wrong.
- One case for the disagreement ruling: the same tool declared by two inputs
  with different input schemas, asserting that the service record names the
  disagreement and that the document's requestBody is the `schema_claim`'s
  payload rather than whichever claim sorted first.
- The unreadable-input paths for both new code paths (`chmod 000`, `chmod
  0444`, a non-dict part), asserting the exit code *and* that the finding names
  the right artifact.
- `tests/fixtures/toy/api.json` extended with the material a `tool` claim needs,
  and `tests/toy.py` extended to build a run through the two new stages. The
  fixture edit is unusually low-risk here — the file is already an MCP
  tool-schema document with `tools[].name` and `input_schema` — but it is still
  the model answer a skill imitates, so the negative fixtures are re-checked for
  incidental loss.
- `uv run rubrica check-skills` exits 0, `make test` green, `make check` clean.

## Documents to update

`docs/concepts/pipeline.md`, `docs/reference/cli.md`,
`docs/reference/artifacts.md`, `CLAUDE.md`, and both generated drawings via
`scripts/render-pipeline-diagram.py` and `scripts/render-readme-diagram.py` —
the second because `PHASES` must partition `paths.STAGES`, and which phase the
two new stages belong to is editorial.

## Out of scope, each with its reason

- **Response inference from trajectories.** The measurement above removed its
  urgency; it is the next step, and it is the step where a prompt is needed
  again, since generalising a schema from observed instances is judgment.
- **Consuming a selection, and the denominator.** `denominator` is
  `{version, capability_cells, goals}` with `additionalProperties: false`, so a
  new exclusion reason is a deliberate change to arithmetic four consumers
  narrow together. It belongs with the step that reads a selection.
- **Everything in the lab design's second enhancement**: generation, per-service
  database projection, the cross-service entity consistency check, `emit`'s
  `mcp_servers` and compose file, `schema_version` 1.3 → 1.4, and `smoke`
  standing the lab up.
- **Source-derived signals for non-Python targets.** Blocked on a source parser
  that does not exist, and named in the skill's prose rather than papered over.
- **Adopting an existing OpenAPI input as a service's document.** `openapi` is
  already an input kind, and a target documented by a real specification is a
  plausible case — but its `operationId`s are whatever its authors chose, and
  contract preservation requires the agent's tool names. Synthesis still wins;
  what an existing document is genuinely good for is response evidence, which
  is the next step's problem.

## Open questions

1. Is a shared credential alone sufficient evidence to group two tools into one
   service, or does grouping require a shared base URL as well? Carried
   unchanged from the lab design.
2. Should the path and method carriers be derived from the tool name or fixed by
   convention, given that only `operationId` is contractually significant?
   Convention is assumed here; deriving them would make a document marginally
   more readable at the cost of a second thing to keep stable.
