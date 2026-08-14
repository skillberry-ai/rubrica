# Ingestion and triage — design

**Status:** Design approved 2026-08-14. Not yet implemented.

**What this is:** the phase that runs *before* `intake`, which on every run to
date has been performed by hand in the orchestrator's own conversation and
recorded nowhere the pipeline can read. It inventories what the human handed
over, rules on what is worth extracting against a declared objective, explodes
containers into their elements, and records every decline with a reason. It is
the last part of rubrica whose judgment is invisible.

**Why now.** The project is moving from "an experiment about whether
prompt-carried judgment survives artifact handoffs" toward something a person
other than its author can run — a standalone Claude Code plugin. A plugin user
points at a repository and a capture file. Everything the orchestrator did by
hand on 2026-08-13 has to be a stage with a contract, a gate, and an artifact,
or it does not exist once the conversation that did it ends.

**Reference run:** `run-20260813-204203`, recorded in
`2026-08-13-parsec-full-run-design.md`. Its §11 and §12 pre-registered most of
the constraints below, and every number in this document was computed from that
run's artifacts rather than reasoned about.

---

## 1. The five operations the parsec run performed by hand

Reconstructed from the run's manifest, its `00-inputs/`, and §2–§4 of its
design record.

| | Operation | Kind of work |
|---|---|---|
| 1 | Walk `/tmp/parsec`, list files with sizes and kinds | mechanical |
| 2 | Declare a scope and an objective, exclude the rest — 73 modules, six personas, one surface kept | judgment |
| 3 | Split the 130-trace MLflow capture, select 7 for distinct *shape* | mechanical split + judgment select |
| 4 | Project `tool_definitions.py` (74KB of Python literals) into a 19KB eleven-tool contract | judgment + running code against the target |
| 5 | Stage at `/tmp/rubrica-lab/inputs-parsec/`, invoke `rubrica intake` | mechanical |

Operations 1, 3 and 5 are code. Operation 2 is a skill's judgment. Operation 4
is the one that needs a human or a future subagent, and §8 is how this design
hands it over.

## 2. Constraints inherited from the parsec run

§11 of that record pre-registered three, each from measured data. They are
adopted here rather than re-derived.

**The verdict on a candidate cannot be a scalar.** `tool_definitions.py` was
unusable whole and fine as a projected eleven-tool contract, whose claims came
back 7% cited and load-bearing — every capability binds to them. The useful
verdict is "container of N independent contracts, extract per-tool", not
"0.4, keep". Size was never the binding constraint; **shape** was. This design
therefore has no size-based exclusion anywhere, and a disposition carries a
reason code rather than a score.

**Utilisation is what a value indicator would be predicting**, and it is
already measurable after the fact: 148 of 815 claims cited on that run, 18%
overall, prose 2–21%, traces 36–73%, `prompt-aap2-agent-md` at 5 of 139. Triage
is therefore *not* asked to predict utilisation. It is asked to rule on
relevance to a declared objective, and `claim-utilisation` scores it afterwards.

**Declining must stay visible, or descoping becomes invisible.** A gap whose
closing evidence was declined at triage is indistinguishable, in the world
model, from a gap nothing could close — and that run has four of the first kind
presenting as the second. This is the constraint that shapes the whole design:
every candidate gets a recorded disposition, every mechanical exclusion gets a
recorded reason code, and a deficiency the admitted set cannot cover is stated
before intake mints anything.

A fourth, from §11's closing paragraph: **the objective has to be explicit.**
That run optimised for a *coherent* run — one surface, deep chains, comparable
to its predecessor. Optimising for *coverage of parsec* would have chosen the
tool-definition projection, one trajectory per persona, and almost none of the
prompt files, which were the 2–21% cohort. The objective determined the answer
and was never written down.

## 3. Decisions taken

| Decision | Ruling | Rejected alternative and why |
|---|---|---|
| How much the phase may do to the candidate set | **Explode and select.** Code splits a container into per-element candidates; the skill admits or declines among elements. Projection is declared, not performed. | *Full manufacture* — a skill running code against the target's source — was declined because it gives a stage Bash over an arbitrary tree and produces an artifact whose provenance is a command rather than a hash. §11's own claim is that the *noticing*, not the projecting, would have prevented the six refusals. *Admit/decline only* was declined because it makes the parsec run impossible without a human pre-split, which is most of what was done by hand. |
| Where the run boundary sits | **`survey` mints the run.** `intake` still writes `manifest.json`. | A reusable corpus workspace outside `runs/` was declined: gate 0 would leave no `decisions.md` entry, and the channel rule would span two roots. |
| Who supplies the objective | **The human declares it; triage is held to it and must challenge it.** | *Human declares, triage obeys* assumes the human already knows the corpus, which was untrue for parsec and will be untrue for a plugin user's first run. *Triage proposes and the human ratifies* lets one dispatch both pick the objective and select against it, so a self-serving objective yields a selection that looks coherent and can be held to nothing. |
| What `rb-triage` reads | **The catalogue only**, with `digest_insufficient` as a decline reason. | *Catalogue plus bounded corpus reads* would put an arbitrary user tree — including `.env` and `.git` — in the dispatch allow list, and make cost unbounded. *Catalogue only with no refusal path* was declined because the decision still gets made, silently and badly, which is the shape that produced four mislabelled gaps. |
| Whether the `max_scenarios` heuristic is in scope | **In scope, and split in two.** `max_scenarios` becomes a *safety ceiling* at 128 (§5) — the point past which no human reviews the output. The *sizing* question it was standing in for becomes a report computed from the world model's own denominators at a human gate (§9). | Treating one number as both was the original error: at a default of 8 a guard behaved like a design parameter, so the parsec run had to raise it by hand and the hand-raise was then mistaken for a defect. Estimating the size at survey time was also declined — it computes the least defensible of the available numbers, from the input set rather than from the capability grid. |

## 4. Pipeline shape

The `00` family gains two siblings, exactly as `01` already holds both
`01-claims/` (fan-out) and `01-world-model.json` (barrier).

| Dir | Stage | Runs as | Writes | Gate |
|---|---|---|---|---|
| `00a` | **survey** | code | `00-catalogue.json` | validate |
| `00b` | **triage** | **`rb-triage`** — barrier | `00-triage.json` | validate · check-refs · **human gate 0** |
| `00c` | intake | code | `manifest.json`, `00-inputs/` | validate · check-refs |

`intake` gains a `check-refs` gate it did not have, because §10's third check —
`manifest.inputs[]` against the admitted dispositions — can only run once the
manifest exists.

**Eleven stages, nine skills.** `paths.STAGES` gains `survey` and `triage` at
the front. `validate.STAGE_ARTIFACTS` gains `survey: ("catalogue",)` and
`triage: ("triage",)`. `paths.RunPaths` gains `catalogue` and `triage`
properties, which is what makes `check-skills` able to hold `rb-triage`'s
`reads` list to one entry.

`scripts/dispatch-stage.sh` needs no change to dispatch the new stage: it
already derives `SKILL_DIR` as `rb-$STAGE`, and triage takes no slice id.

**One artifact carries the run's parameters, not two.** A separate
`survey.json` was considered and rejected. The catalogue's `request` block holds
target, interface, objective and the run's limits, so there is one file the
human edits at gate 0 and one file `intake` reads. It also makes the right thing
happen when the objective is overridden: the catalogue changed, so triage must
be re-dispatched rather than silently kept.

**No schema is relaxed.** `manifest-0.1.json` carries `inputs.minItems: 1`.
Because `survey` mints only the directory and the catalogue, and `intake` still
writes the manifest, the manifest continues to appear only at the moment there
are inputs to name.

## 5. `rubrica survey` — the catalogue

```
rubrica survey --corpus PATH [--corpus PATH ...] --runs-dir PATH
               --target-name NAME --target-interface IFACE
               --objective {breadth,depth} [--objective-note TEXT] [--scope-note TEXT]
               [--exclude GLOB ...] [--max-candidates N] [--max-rounds N] [--max-scenarios N]
```

Mints `runs/run-<stamp>/`, writes `00-catalogue.json`, prints the run directory.
Run id and timestamp come from code for the reason `intake.py`'s docstring
already gives: a model-invented timestamp makes two otherwise-identical runs
diff.

`--objective` takes one of two values, defined here because the whole phase is
held to them:

- **`breadth`** — maximise the fraction of the target's capability surface the
  admitted set can describe.
- **`depth`** — maximise multi-hop chains within one coherent surface, accepting
  that other surfaces go undescribed.

The parsec run was `depth` without saying so. §2's fourth constraint is that
this choice determined its answer and was never written down.

`--max-scenarios` defaults to **128**, and that number comes with a change in
what the parameter *is*. It is not an estimate of the right suite size. It is a
**safety ceiling** — the point past which no human would review the output, so a
run that reaches it has gone wrong rather than gone large. `intake`'s default of
8 made a guard behave like a design parameter, which is why the parsec run had to
raise it by hand and why that hand-raise was then mistaken for a defect (§10 of
that record, error 4).

**No machinery is needed for this, because the ceiling is already enforced.**
`refs.check_scenarios` reports a finding when the count of proposed-or-active
scenarios exceeds `max_scenarios`, and `rb-propose`'s refusal conditions stop it
proposing once the cap is reached. Duplicate and rejected scenarios already do
not count against it. Only the default was wrong.

128 is defensible on both axes a ceiling guards. **Review:** 128 Harbor packages
is already past what anyone reads, and the emitted suite is what a human signs
off. **Spend:** the parsec run's recorded totals imply roughly $1.66 per scenario
across instantiate and challenge — $35.66 for 36 instantiate dispatches, and
about $20 for 30 challenge verdicts — so a run reaching the ceiling costs on the
order of $200. That per-scenario figure is arithmetic over recorded totals, not
itself a recorded figure.

**`max_rounds` is the same class of parameter, and this design does not fix it.**
Its default of 2 is binding rather than protective — the parsec run raised it to
3 — while in practice the loop should stop on `converged` or
`halted_no_progress`. A ceiling nearer 6 would make it a guard too, but that is a
change to the propose/score loop rather than to ingestion, and it belongs with
F1. Recorded in §15.

### 5.1 Walk and exclude, visibly

§2's third constraint applies to the mechanical excluder too, not only to the
skill, so every exclusion lands in `excluded[]` with a reason code:

`gitignored` · `vcs_metadata` · `binary` · `lockfile` · `vendored` ·
`duplicate` · `unreadable` · `operator_excluded`

`duplicate` is byte-identity by sha256 against an earlier path, which is
mechanical and safe. `binary` is a null byte in the first 8KB. `vendored`
covers `node_modules`, `.venv`, `site-packages`, `vendor/`, `target/`, `dist/`.

**There is deliberately no size-based exclusion.** §2's first constraint is
explicit that size was never binding and shape was, and the largest single file
in the parsec corpus was also the most load-bearing input. A file too large to
digest fully gets `digest_truncated: true` on its digest; it is never excluded
for being large.

### 5.2 Explode containers

A candidate whose content is a homogeneous JSON array of three or more objects
becomes N element candidates. The container itself stays in the catalogue marked
`admissible: false`, so a reader can see what the elements came from. The same
applies to a JSON object whose values are homogeneous objects keyed by id.

**Homogeneous** means the elements' top-level key sets share an intersection of
at least three keys. Strict key-set identity was rejected as the rule: real
captures carry optional fields, and 130 MLflow traces where one lacks an
`assessments` key are not two kinds of thing. The intersection rule is
mechanical, tolerant of that, and recorded in `policy` so a reader knows which
rule produced the split.

Nothing else is exploded. No Python literals, no multi-document markdown, no
archive members. That boundary is §3's first ruling.

The explode threshold and the homogeneity rule are recorded in the catalogue's
`policy` block, because a reader of a catalogue needs to know what shaped it.

If explosion would push the catalogue past `--max-candidates` (default 500),
`survey` exits **2** naming the container. Narrowing `--corpus` is the fix, and
the exit-code contract puts a usage error at 2 — the orchestrator cannot repair
a corpus that is too large.

### 5.3 Digest each candidate

This is the heart of the design, because `rb-triage` reads only this. A digest
that omits what mattered makes triage blind, and the digest generator is code
that cannot know what matters.

Common fields: `candidate_id`, either `path` or `container` + `json_pointer`,
`bytes`, `sha256`, and `kind` from the existing `intake.classify`.

Then, by kind:

- **prose** (`.md .rst .txt .adoc`) — the complete heading outline, the first
  `policy.digest_body_chars` characters of body text (default 2000), line count.
- **source** (`.py .ts .tsx .js .go .rs .java .rb`) — top-level `def` and
  `class` names, **top-level assignment names**, the import list, line count.
  Source is admissible: §11 retracted the parsec run's blanket exclusion of it.
  The assignment names are not decoration — they are what lets triage name
  `TOOL_DEFINITIONS` as a projection's extraction point (§8).
- **JSON** — a structural skeleton to depth 3 with types and array lengths,
  plus leaf value samples.
- **trace** — the fields that made the parsec selections reachable: `status`,
  span or step count, the request text, the tool names called, error markers.

**The trace row is where a generic digest is most likely to be insufficient,
and this design names that rather than papering over it.** It ships as the JSON
skeleton plus a small set of well-known-key heuristics (`status`, `error`,
`question`/`input`/`request`/`query`, `spans`/`steps`/`messages`/`events`
counts, tool-name arrays), and **the digest records which heuristics fired.**
When they do not fire, triage declines `digest_insufficient` and names the field
it needed, rather than guessing. That is what makes the generator's blindness a
finding instead of a silent bad decision.

Checked against the parsec run: every selection made there was reachable from
cheap digest fields. t7 was kept for being the only `status: ERROR` trace with
3 spans; t3 was identified as an icinga/aap2 crossover from its question text;
the prose documents were admitted on path and title, not content.

### 5.4 The catalogue artifact

```
{
  "schema_version": "0.1",
  "run_id": "run-YYYYmmdd-HHMMSS",
  "created_utc": "...",
  "request": {
    "target": {"name": "...", "interface": "..."},
    "objective": "breadth" | "depth",
    "objective_note": "...",              // optional prose
    "scope_note": "...",                  // optional prose
    "corpus_roots": ["..."],
    "limits": {"max_rounds": 2, "max_scenarios": 128}  // ceilings, not targets; see §5
  },
  "policy": {
    "exclusion_reasons": ["gitignored", ...],
    "explode_min_elements": 3,
    "digest_body_chars": N,
    "max_candidates": N
  },
  "candidates": [ { ...common fields..., "digest": {...}, "admissible": true,
                    "origin": "corpus" | "container_element" | "projection" } ],
  "excluded": [ {"path": "...", "reason": "vendored"} ]
}
```

## 6. `rb-triage` — the ninth skill

```toml
stage = "triage"
reads = ["catalogue"]
writes = ["triage"]
schemas = ["triage"]
invokes = ["validate"]
```

`reads` is one entry. `check-skills` already holds every contract to
`paths.RunPaths` attribute names, so once `catalogue` is a `RunPaths` property
the catalogue-only rule is enforced by the same check that enforces every other
stage's reads. No new checking machinery.

Barrier rather than fan-out: the judgment is comparative. "This trajectory is a
near-duplicate of that one" cannot be reached by a member that sees one
candidate.

### 6.1 Output — `00-triage.json`

**`objective_review`** — mandatory. The surfaces found, as
`{name, evidence: [candidate_id], weight}` where `weight` is
`{candidates: N, bytes: N}` summed over that surface's evidence — mechanical and
derivable from the catalogue, so a reader can check it rather than take it on
faith; whether the declared objective is supported by that evidence; and an
optional `recommended_objective` with reasons. A triage that cannot enumerate the surfaces has not done its job, and
this is the block the human actually rules on at gate 0. It is §2's fourth
constraint made mechanical: a triage obliged to enumerate surfaces and say
whether the declared objective is supported would have had to state that
parsec's declared scope excluded the evidence six scenarios later died for.

**`dispositions[]`** — one entry per catalogue candidate, **exactly once**. A
candidate with no disposition is a finding; a disposition naming an unknown
candidate is a finding. That coverage requirement is the mechanism that makes
declining visible: without it, "declined" and "never considered" are the same
absence, which is precisely the confusion §2's third constraint names.

Fields: `candidate_id`, `disposition` (`admit` | `decline`), `reason_code`,
`reason` (prose), `priority` (admits only), `authority`
(`triage` | `human`, the latter set by gate-0 overrides and
`adopt-projection`).

`priority` is an integer rank among the admits expressing triage's expected
evidence value. **No code acts on it.** `gate-brief` orders by it and nothing
else reads it — the same division that makes `rb-score` compute the coverage
verdict while only the orchestrator acts on it.

Decline reason codes are an enum, so they are checkable:

| Code | Meaning |
|---|---|
| `off_objective` | Real evidence about the target, but not about what this run is for |
| `out_of_scope` | Belongs to a surface `scope_note` excludes |
| `near_duplicate` | Another admitted candidate carries the same shape |
| `superseded` | A later or more authoritative candidate says the same thing |
| `implementation_detail` | Describes how, where the objective needs what |
| `no_evidence_value` | Carries no statement about the target |
| `digest_insufficient` | Cannot be ruled on from the digest; names the field needed |
| `needs_projection` | Valuable but not usable as-is; see the projection it references |

**Both of the last two declines must be referenced from elsewhere in the
artifact** — a `digest_insufficient` decline by a `deficiencies[]` entry, a
`needs_projection` decline by a `projections[]` entry. Without that, the two
reason codes whose whole purpose is to make a loss visible would be the quietest
way to lose something: a decline nothing else in the run points at reads exactly
like a decline that was fine. It is a reference requirement, not a semantic one,
so §10 can check it.

**`deficiencies[]`** — what the admitted set does not contain that the
objective needs. Each names the missing thing, and where known the candidate
that would supply it if projected. This is the block that would have printed
*"no candidate declares the result shape of these 13 tools"* before intake
minted the parsec run, and §11 claims it would have predicted all six
instantiate refusals and scn-011's rejection.

**`projections[]`** — see §8.

### 6.2 Refusal conditions

Every one has a trigger detectable from the catalogue and an action a model can
take, which is the standard §5 of a skill is held to.

1. `request.objective` absent, or contradicting `scope_note` — write nothing,
   report. A triage held to no objective is the state this design exists to end.
2. Every candidate would be declined — write nothing, report. An empty admitted
   set is a scoping failure, not a triage result.
3. The declared objective is unsupported by the surfaces found — you may still
   write, but `objective_review.supported` must be `false` and you may not
   silently re-scope. Re-scoping is the human's move at gate 0.
4. A candidate you cannot rule on from its digest — decline it
   `digest_insufficient` and name the field you would have needed. Never guess,
   and never open the file: it is not in your `reads`.
5. Nothing may appear in `dispositions[]` that is not in `candidates[]`. You
   cannot invent a candidate, and a candidate you wish existed is a
   `deficiencies[]` entry.

## 7. Gate 0 and `intake`

Gate 0 is held by a human reading `00-triage.json` against the catalogue, with
`rubrica gate-brief --gate 0` as the rendering (§11). Four moves:

1. **Accept** — run `rubrica intake --run RUN`.
2. **Override a disposition** — edit `00-triage.json`, set `authority: "human"`,
   record with `rubrica decide`.
3. **Override the objective** — edit the catalogue's `request` block, which
   obliges a triage re-dispatch, because it changes what every other disposition
   was ruled against.
4. **Satisfy a projection** — `rubrica adopt-projection` (§8.2).

As with gates 1–3, nothing mechanically enforces that the gate was held. That
is consistent, deliberate, and recorded: `rb-orchestrate` holds gates and writes
`decisions.md`, and a gate held badly but recorded is recoverable where one
skipped silently is not.

### 7.1 `intake` keeps `--input` and gains `--run`

`intake.intake()` splits into a mint step and a register step. `survey` calls
mint; a new `intake.admit_from_triage(run)` calls register; the existing
combined function keeps its present signature.

The consequence is that all twenty existing `intake()` call sites keep working
unchanged and `build_toy_run`'s existing behaviour is unmodified — it gains two
new optional checkpoints and nothing else. `rubrica intake --input ...
--runs-dir ...` survives as the direct path for someone with three files who does
not need triage: a real use case, not only a test affordance.

`--run` and `--input` are mutually exclusive, and so are `--run` and every
parameter the catalogue already carries (`--runs-dir`, `--target-name`,
`--target-interface`, the two limits). Passing both is a usage error at exit 2,
refused in the CLI rather than resolved by precedence — the same call that
`intake` already makes on a blank `--target-name`, and for the same reason:
minting a run from an ambiguous parameter set exits 0 and surfaces as findings
against an artifact no repair prompt can fix.

**A run built through `--input` has no catalogue, and that is not a finding.**
`check-refs` treats an absent catalogue as "no triage happened", on the same
ruling that already makes `intake`'s and `smoke`'s absence from
`manifest.stages` not a finding.

### 7.2 Materialisation and provenance

`00-inputs/` stops being byte-copies. An admitted trajectory is element 47 of a
130-element container, so `intake` materialises it through
`artifacts.write_json`, which is byte-stable for the same reason `emit` is code:
two runs with identical upstream artifacts must produce identical bytes, or
variance stops being attributable to a stage.

`manifest.inputs[]` gains an optional
`provenance: {container_sha256, json_pointer}` — or
`{projection_id, source_candidate_ids}` for an adopted projection. The entry's
`sha256` is of the materialised bytes, because that is what
`refs.check_inputs` re-hashes.

### 7.3 Exit codes

An internally inconsistent triage record — a disposition naming an unknown
candidate, a candidate with no disposition, zero admits — is **exit 1 with
findings naming `00-triage.json`**, repairable by re-dispatching triage. Only
unreadable or missing files are **2**. This is the exit-code contract's first
invariant: a stage defect must never surface as 2, because the orchestrator
halts instead of spending its one repair attempt.

## 8. Projections — a brief, not a complaint

`needs_projection` is the `tool_definitions.py` case: valuable, not usable
as-is, and the remedy is work someone else does. A decline that only says so is
a complaint. This block makes it a **dispatchable work order**, and is designed
so that the post-MVP stage that automates it needs no new artifact.

A separate top-level block rather than a field on the decline, because one
projection can draw on several source candidates and close several
deficiencies — and because a fan-out iterates a block, not a field.

### 8.1 The artifact

```json
{
  "projection_id": "prj-tool-contracts",
  "closes": ["def-tool-result-shapes"],
  "sources": [{
    "candidate_id": "src-agent-tool-definitions-py",
    "path": "parsec/src/agent/tool_definitions.py",
    "digest_note": "top-level assignments TOOL_DEFINITIONS, DELEGATION_TOOLS; 74KB"
  }],
  "wanted": {
    "kind": "mcp_tool_schema",
    "statement": "One JSON document holding the input schema and the result shape of every tool the admitted traces call.",
    "why": "Every capability binds to a tool, and a scenario cannot be seeded without the result shape."
  },
  "method": {
    "confidence": "high" | "medium" | "unknown",
    "steps": ["Import the module rather than parsing it -- the schemas are literals",
              "Select the entries whose names appear in tools_called across the admitted traces",
              "Emit {\"tools\": [...]}"]
  },
  "acceptance": {
    "classifies_as": "mcp_tool_schema",
    "pointers_required": ["/tools"],
    "must_contain": ["query_aap2", "query_icinga", "search_github_repo"],
    "must_not_contain": ["def ", "import ", "self."],
    "prose": "Every element of /tools carries name, input_schema and result_shape; result_shape names the keys a caller receives, not an example value."
  },
  "boundary": "Contracts only. No function bodies, no client code, no implementation."
}
```

Six parts, each earning its place. **`wanted`** and **`why`** so the worker
knows when it is done and what breaks if it is not. **`sources`** with the
digest note, so it starts where triage stopped. **`method`** with an explicit
`confidence`, because triage frequently cannot know the method from a digest and
`unknown` is an honest value — the acceptance contract binds, not the steps.
**`acceptance`**, so success is checkable without re-reading triage's mind.
**`boundary`**, because a projection that drags in implementation defeats the
objective it was requested for.

**Structural acceptance is necessary, not sufficient.** `classifies_as`,
`pointers_required`, `must_contain` and `must_not_contain` are genuinely
mechanical, and they are the same shape `tests/fixtures/toy-gap/`'s
forbidden-substring list already uses — where the spec says that list *is* the
specification. But whether `result_shape` truly describes what a caller
receives is semantic, and the rule against inventing a mechanical check for
support applies here as it applies to Layer 2. So `prose` stays, and the check
reports "structural acceptance passed", never "accepted".

### 8.2 `adopt-projection`

```
rubrica adopt-projection --run RUN --projection prj-tool-contracts --file PATH [--check-only]
```

Runs the structural acceptance checks and, on pass, appends the file to
`00-catalogue.json` as a candidate with `origin: "projection"` and
`provenance: {projection_id, source_candidate_ids}`, appends an `admit`
disposition with `authority: "human"`, and marks the deficiency closed.
`--check-only` does the first half and writes nothing. A file that fails
structural acceptance is **exit 1, one finding per failed check** — the human or
the future `rb-project` member reads the findings and tries again — and only an
unreadable file or an unknown `projection_id` is 2.

Appending to the catalogue after the fact is the same append-and-record move
`02-scenarios.json` already makes round by round, and a human authoring an
admission at their own gate is what gate 0 *is*. Overriding the *objective*
still obliges a triage re-dispatch, because that changes the basis of every
other disposition; adopting a projection does not, because it only adds.

### 8.3 What this buys post-MVP

The future stage needs **no new artifact**. `rb-project` — fan-out, one member
per `projection_id`, dispatched with the run directory, the stage name, its
skill, and its own `projection_id`, exactly the four things an `rb-instantiate`
member gets — reads the projection block plus its named sources, writes the
file, and runs `adopt-projection` as its own gate, exactly as every skill today
runs `validate`.

Stated plainly: that member would be **the first stage to read outside the run
and run code against the target**, which is precisely what "full manufacture"
was declined for in §3. The deferral is real and this block is the bridge across
it. Building the loop later costs a skill and a `STAGES` entry, not a redesign.

## 9. Implied suite size — a sizing report, not a cap

§5 makes `max_scenarios` a safety ceiling at 128. That leaves a different
question unanswered, and it is the one §12 of the parsec record actually asked:
**how big should this run's suite be, given this target?** The ceiling does not
answer it, because a guard set where output stops being reviewable says nothing
about whether 12 scenarios is thin or 60 is bloated for a particular world model.

Computed from `run-20260813-204203`'s own artifacts:

```
implied_size = ceil( (capability_cells + Σ |goals[].expected_hop_depths|)
                     / acceptance_allowance )
```

| Available at | Denominator | Implied size | Note |
|---|---|---|---|
| **Gate 1** (world model only) | 28 + 23 = **51** | **68** | No gap deduction: which cells are `blocked_by_gap` is *score's* judgment, produced at stage 03 |
| **Gate 2** (after round 1) | 51 − 5 blocked = **46** | **62** | |

The parsec cap was hand-set to **64** and the recorded floor for a real target
was **~50**. The un-deducted denominator lands within one of the floor that was
ruled by instinct, and the implied size within two of the number chosen by hand.
That agreement is the reason to believe the formula at all, and it is why F1
matters: those 23 hop-depth slots are exactly the term `coverage-0.1.json`'s
`progress` definition has no representation for.

`acceptance_allowance` is **0.75**, parsec's measured acceptance — 23 accepted of
30 instantiated. One run's constant, and it must be labelled as one rather than
as a law.

**Nothing acts on this number.** It is reported at gates 1 and 2 by
`gate-brief`, alongside coverage, for a human deciding whether the suite under
construction is the right size for the target. Its two real uses are diagnostic:
an implied size *above* the 128 ceiling means the target is too large for one run
and wants splitting, which is exactly the ruling the parsec run made by hand in
its §2; and a suite that halts far *below* the implied size — 36 proposed against
68 implied, as parsec did — is the signal that F1's stopping rule gave up early.

`rubrica set-limit --run RUN --max-scenarios N --reason TEXT` exists for
*lowering* the ceiling on a deliberately cheap probe run, and records the change
with its reason. It is not how the implied size gets applied, because the implied
size never gets applied.

## 10. `check-refs`

Layer 2 gains three reference checks, all of them resolution rather than
semantics:

- Every catalogue candidate has exactly one disposition; no disposition names an
  unknown candidate.
- Every `closes` resolves to a deficiency id; every `sources[].candidate_id`
  resolves to a candidate.
- Every `digest_insufficient` decline is referenced by a deficiency, and every
  `needs_projection` decline by a projection (§6.1).
- `manifest.inputs[]` corresponds one-to-one with the admitted dispositions —
  which is what catches an admission `intake` dropped.

**§11's headline finding cannot go in `check-refs`, and this design says so
rather than building a check that lies.** "A gap whose named closing input was
declined at triage" requires matching gap prose to decline prose. That is
semantic, and it is the thing Layer 2 is explicitly forbidden to invent a check
for, on the same grounds that it checks whether an element *references* a
resolvable claim and never whether the claim *supports* it.

It goes where `claim-utilisation` already went: a report at a human gate (§11).
Once the human names the pairing, `rubrica decide` records it and *then*
`check-refs` can verify the reference resolves. Semantic call at the gate,
reference check in Layer 2.

## 11. `gate-brief`

```
rubrica gate-brief --run RUN --gate {0,1,2,3}
```

A composer, not a new analysis. It renders the reports that already exist plus
the two this design adds:

- **Gate 0** — the catalogue and triage record made readable: surfaces found,
  objective supported or not, admits by priority, declines by reason code,
  open deficiencies and their projections.
- **Gate 1** — `claim-utilisation` (calling the existing code), §9's implied
  suite size, and the two sides of §10's semantic pairing side by side: the
  world model's gaps, and the triage record's open deficiencies. A human seeing
  `gap-decimal-serialization-root-cause` next to *"declined: src/tools/aws.py —
  implementation_detail"* makes that connection in a second; a regex never will.
- **Gates 2 and 3** — the existing coverage verdict and verdict tallies.

Gate 0's brief is also the plugin's primary human-facing surface, which is the
second reason to build one composer now rather than ship four ad-hoc reports.

`gate-brief` is a report and never a gate: it exits 0 on any readable run, on
the same ruling that governs `claim-utilisation`. Asked for gate 0 on a run built
through `intake --input`, it says no triage happened and exits 0 — §7.1's ruling
that an absent catalogue is not a finding, held consistently by the report as
well as by the check.

## 12. Surface added

This is more than one plan's worth of work; §16 is the phasing.

**Subcommands: 13 → 17.** `survey`, `adopt-projection`, `gate-brief`,
`set-limit`. `set-limit` is the most droppable of the four if the build needs
to be smaller; the other three each carry a stage or a gate.

**Schemas: 12 → 14.** `catalogue-0.1.json`, `triage-0.1.json`. Plus an additive
change to `manifest-0.1.json` for `inputs[].provenance`. `limits.max_scenarios`
keeps `minimum: 1` and gains **no `maximum`**: the ceiling is a default, so a
human who types 300 has explicitly asked for it, while an autonomous run that
sets nothing — the case §5 exists to protect — gets 128.

**The ceiling itself is a two-line change**, independent of everything else here:
`cli.py`'s `--max-scenarios` default, and `test_cli.py:330`, which is the only
test pinning it. Every other `max_scenarios=8` in the suite is an explicit
argument, and `tests/toy.py` keeps its own 8 because the toy world has five
scenarios and `test_toy_fixture.py` depends on that cap being meaningful.

**Skills: 8 → 9.** `rb-triage`, with its `exercise.md`.

**Stages: 9 → 11.** `survey`, `triage`.

`rb-orchestrate` gains the two stages and gate 0 in its dispatch table, and
`docs/running-a-stage-by-hand.md` gains the triage dispatch.

## 13. Testing

**`tests/fixtures/corpus-toy/`** — one corpus exercising every exclusion reason
code and the explosion path: a prose document, a source file with top-level
assignments, a four-element homogeneous JSON container, a binary, a lockfile,
and a byte-duplicate. Plus a committed expected catalogue. This fixture
inherits the golden fixture's elevated risk for the same reason the toy world
has it: it becomes the model answer `rb-triage` imitates, so a defect in it
teaches the skill the wrong thing.

**Negative fixtures are catalogue JSON files, not corpora**, because triage
reads only the catalogue. Each subtracts exactly one thing:
`catalogue-unsupported-objective.json` (depth declared on a one-candidate
surface, firing refusal 3) and `catalogue-all-declinable.json` (firing refusal
2). Guarded in both directions the way `test_refusal_fixtures.py` guards the
existing two — the fixture still carries its defect *and* has not silently lost
anything else, because an over-subtraction there once destroyed a capability
fact while passing every forbidden-substring check.

**`tests/toy.py`** gains `survey` and `triage` at the front of `_UPTO_STAGES`.
This module was checked first, per the standing instruction: the helper this
build wants — a catalogue builder — genuinely does not exist yet, unlike nearly
every other checkpoint requested during the skills build.

**Prose predicates on `rb-triage` measured in both directions** on a `/tmp` copy
under `RUBRICA_SKILLS_DIR`: delete the prose, confirm red; reword it
meaning-preservingly, confirm green. Scoped with `skills.section_body`, because
`"refusal" in body.lower()` is vacuous for every conforming skill and roughly
nineteen assertions in this repo were already measured satisfiable by unrelated
content.

**`test_dispatch_harness.py`** — triage's dispatch denies `decisions.md`, and
the new catalogue and triage paths must be re-measured against
`test_nothing_check_refs_reads_is_ever_denied`, since denying a path
`check-refs` reads makes a stage's own gate fabricate findings. `test_cli.py`
grows for free from `SUBCOMMANDS`.

**Unreadable-input paths for all new code** — `chmod 000` on a corpus root,
`chmod 0444`, a catalogue that is a directory, a bad `RUBRICA_SCHEMA_DIR` —
because `survey`, `adopt-projection` and `gate-brief` are new members of exactly
the class that has produced fabricated findings and misreported exit codes here
before.

**What no test can reach:** whether triage declined for the reason it wrote, and
whether a digest was truly insufficient when it said so. That needs a live
dispatch, an `exercise.md` recording what happened rather than what was
reasoned, and a transcript audit — the same and only instrument the fan-out
isolation rule has.

## 14. Risks

**The digest is the single point of failure.** Every triage decision rests on
it, it is written by code that cannot know the target, and its insufficiency is
only visible when triage notices and says so. Mitigated by the
`digest_insufficient` decline and by recording which heuristics fired, not
eliminated.

**A barrier over 500 candidates is a large context.** At roughly 400 bytes of
digest per candidate that is ~200KB, which is affordable but not free, and the
`--max-candidates` refusal is the only thing bounding it. If real corpora
routinely exceed it, triage needs a clustering pass and that is a redesign, not
a parameter.

**`objective_review` is prose a model writes about its own compliance.** A
triage that re-scoped silently and then wrote `supported: true` produces an
artifact both gates pass. Nothing mechanical catches it; gate 0 and a transcript
audit are the instruments, which is the same weakest link §8 of the main spec
already records for fan-out isolation.

**The 0.75 and the 51/68 arithmetic rest on one run.** A second target could
move both substantially.

**The 128 ceiling is a blast-radius bound, not a quality bound.** A run that
reaches it has spent on the order of $200 producing more packages than anyone
will read, and the only things that stop it earlier are `converged`,
`halted_no_progress`, and a human at gate 2. F1 records that
`halted_no_progress` is blind to goal progress, so the stopping rule that
*should* bind is the one known to be weakest. The ceiling holds either way, which
is the point of a ceiling — but a run halting for the right reason is not
something this design improves.

**`max_rounds` remains a design parameter masquerading as a guard.** §5 explains
why it is the same error at 2 that `max_scenarios` was at 8, and why fixing it
belongs with F1 rather than here. Until then a run's real bound is often the round
cap rather than its coverage.

## 15. Owed, and explicitly not solved here

- **Plugin packaging** — how a dispatched skill reaches the `rubrica` CLI when
  rubrica ships as a plugin rather than as this repository. This design is
  *compatible* with it (triage is a real stage with a contract, reads only run
  artifacts, and needs no allow-list edit), but packaging is the other half of
  "standalone plugin" and is out of scope here.
- **`rb-project`** — the projection fan-out, bridged by §8 and costed at a skill
  plus a `STAGES` entry.
- **F1's goal term in `progress`** — §9's sizing leans on the 23 hop-depth
  slots that `progress` has no representation for, so the two are related, but
  F1 is not fixed here.
- **§12's last item cuts §9 directly.** If the five internal-persona goals do
  not belong in the denominator — three of twelve goals describe one journey from
  three vantage points, and only `act-end-user` goals are exercisable through an
  `http-sse` interface — the gate-1 denominator drops from 51 to roughly 46.
  That ruling is owed before the formula is trusted.
- **`max_rounds` is the same error `max_scenarios` had.** A default of 2 is
  binding rather than protective; a ceiling nearer 6 would make it a guard, and
  the loop would then stop on `converged` or `halted_no_progress` as intended.
  Deferred rather than done because it changes the propose/score loop's
  parameters, not ingestion's, and because F1 has to be settled first — raising
  the round ceiling while `progress` stays blind to goal coverage buys rounds the
  stopping rule will refuse to use.
- **F2's entity gate on propose**, F3, F4 and F5 are untouched by this design.

## 16. Build order

This is more than one implementation plan's worth of work, so it decomposes into
a two-line change and four phases. Each ends with `make test` and `make check`
green and `rubrica check-skills` at 0, and each is useful on its own — phase 0
stands entirely alone, phase 1 replaces the manual inventory, and phases 1–3
replace the whole manual pass except projections.

| Phase | Contents | Ends usefully at |
|---|---|---|
| **0 — the ceiling** | `--max-scenarios` default 8 → 128, and the one test that pins it | Nothing else in this design is needed for it, and it removes the default that made the parsec run's hand-raise necessary |
| **1 — the catalogue** | `paths.STAGES`/`RunPaths`/`STAGE_ARTIFACTS` entries for `survey`, `catalogue-0.1.json`, `rubrica survey` with its exclusion policy, container explosion and digests, `tests/fixtures/corpus-toy/`, unreadable-input paths | A corpus becomes a reviewable inventory; operations 1 and 3 of §1 are code |
| **2 — the skill** | `triage-0.1.json`, `rb-triage` with its five sections and its `exercise.md`, the §10 reference checks over the triage record, both negative catalogue fixtures, the dispatch-harness deny coverage | Operation 2 of §1 is a stage with a contract and a gate |
| **3 — admission** | `intake` split into mint and register, `intake --run`, materialisation and `provenance`, the manifest↔dispositions check, `tests/toy.py`'s two new checkpoints | The pipeline runs end to end from a corpus; operation 5 is code |
| **4 — the human's instruments** | `projections[]`, `adopt-projection`, `gate-brief`, §9's implied-size report, `set-limit` | Gate 0 has a surface, and operation 4 is a dispatchable brief |

Phase 4 is the one to cut down if the build needs to be smaller: `set-limit`
first, then §9's implied-size report — but not `projections[]`, which is the artifact
§8.3's post-MVP stage is designed against and the only part that is expensive to
add later.
