# Drivable coverage denominator

Design for [issue 17](https://github.ibm.com/kaegis/rubrica/issues/17). Measured on
`run-20260827-070444` (reservation-service, `http-sse`, `breadth`) at `2f2ca2e`,
with `run-20260825-094033` and `run-20260823-112746` as comparisons.

## The defect

`reconcile.seal` computes `denominator.capability_cells` over every capability x
outcome-class pair and never consults `binding`. `emit.bindings`
(`emit.py:60`) drops capabilities that declare none, so the number the whole
experiment is scored against counts cells no emitted test can drive.

On `run-20260827-070444`: 24 capabilities, 5 bound, **37 of 56 cells (66%) on
capabilities with no tool binding**. Both gate layers exit 0 on that run.

The earliest signal today is `emit.py:105`, at stage 06 -- after propose, score,
instantiate and challenge have all run against the inflated number, and after
gates 1, 2 and 3. The denominator is frozen at the seal by design, so a wrong one
is not corrected later; it is scored against for the rest of the run.

## What the measurement changed about the diagnosis

Three claims in the issue do not survive contact with the code, and all three
change the fix.

**`refs._cells` is a reference resolver, not the denominator's arithmetic.** It
has four call sites: the denominator identity (`refs.py:1873`), batch-plan
`hole_refs` (`:2253`), scenario `capability_refs` (`:2593`), and coverage matrix
and hole cells (`:2696`). Narrowing it as the issue instructs makes every
scenario, batch plan and matrix row on an unbound cell an unresolvable
reference -- the fabricated-finding class CLAUDE.md's "a `1` must name the
*right* artifact" rule exists over. The resolver stays wide; scoring gets its own
function.

**`denominator.version` is a per-run amendment counter, not an arithmetic
generation.** `reconcile.seal:183`: "an amendment costs an explicit orchestrator
decision recorded in decisions.md, and a seal that incremented a version it found
on disk would let the number move without one." It is compared for equality
*within* a run (`refs.py:2600`, `rounds.py:772`). Defaulting it to 2 would make
every fresh run claim to have been amended once, spending the `decisions.md`
audit trail to carry a fact about the code version. The comparability worry it
was meant to answer is also unfounded: nothing in the repository compares
`capability_cells` across runs. `stability.py` implements both `compare-gold` and
`diff-runs` and never reads the field; `recall.py`'s "denominator" is the gold
task count, unrelated. The complete reader set is `reconcile.py` (writes),
`refs.py` (checks), `sizing.py` (reads), `brief.py` (renders).

**The defect predates the commits it is attributed to.** `run-20260825-094033`
(2026-08-25, `interface: agent`, executive-agent corpus) already had 9 unbound
capabilities contributing 36 of 148 cells. All four accounting commits
(`86fbdf2`, `b9de5d5`, `4888c54`, `fad7971`) landed 2026-08-26. So the *class* is
structural. The *magnitude* on this corpus is accounting-driven: of the 19 unbound
capabilities, **10 cite `pyproject-toml` among their claims and 4 cite nothing
else** (`cap-keycloak`, `cap-langchain-community`, `cap-ollama-backend`,
`cap-openai-backend`). Those are two different counts, and this line originally
gave the second as five while listing four ids; both numbers are re-measured
against `run-20260827-070444`. That distinction matters -- it means the
arithmetic fix
addresses the class and a separate prompt change addresses the magnitude, and it
removes any argument for reverting commits that work.

## Why `binding.tool` is the key, and what it costs

Absence of `binding.tool` has three distinct causes on the measured run, and code
cannot tell them apart -- the classification is semantic, which layer 2 never
mechanises.

| Cause | Caps | Cells | Example | Excluding is |
|---|---|---|---|---|
| A -- not target behaviour | 10 | 18 | `cap-keycloak`, a `pyproject.toml` dependency | correct |
| B -- real surface, other interface | 5 | 11 | `cap-a2a-task-create`, JSON-RPC on an `http-sse` run | correct |
| C -- real agent-level behaviour | 4 | 8 | `cap-empty-search-guidance`, observed in trajectory 5 | **wrong** |

`binding.tool` is therefore right for 29 of 37 cells and wrong for 8. It is
chosen anyway, because it is **one notch tighter** than the predicate
`emit.bindings` applies -- not identical to it, as this line first claimed.
`emit.bindings` tests the binding *object*'s truthiness (`emit.py:66`) while
`emit.call_spec` then reads `binding["tool"]` unguarded (`emit.py:79`), so the two
disagree on exactly one shape, a binding present with no `tool`, and that shape
crashes `call_spec`. Keying on `binding.tool` therefore makes the narrowed
denominator equal what the pipeline can actually ship today, which is
the honest scoring target. Group C is not hidden -- it is recorded as a
limitation (see below) rather than silently absorbed.

`underspecified` outcome classes are **not** part of this defect, despite being
19 of 56 cells here and 20-68% of cells in every run examined. `rb-propose`
§221-228 argues them into the denominator deliberately. Do not let the fix drag
them in.

## The design

### One concept, two functions

A cell can *exist* in the world model without being *drivable* through the
target. The two must never share a spelling, because reference resolution needs
the wide set and scoring needs the narrow one.

- `refs._cells(world)` -- every declared `(capability_id, outcome_class_id)`.
  Resolves hole refs, scenario `capability_refs`, batch `hole_refs`. **Unchanged,
  stays wide.**
- `refs.drivable_cells(world)` -- those whose capability declares
  `binding.tool`. **New.** The scoring set.

Both are set comprehensions over distinct pairs. `limitations.md`'s "One
precision" paragraph, under the coverage-denominator entry, records why: a
per-capability sum agrees with the set only until an id repeats, at which point
the sum is simply the wrong number. (Cited by heading rather than by line, which
is how it was first written; the line has since moved.)

### Four consumers narrow together

| Site | Now | After |
|---|---|---|
| `reconcile.seal:310` `capability_cells` | 56 | 19 |
| `refs.check_world_model:1873` | `len(_cells(world))` | `len(drivable_cells(world))` |
| `rounds.capability_matrix:825` rows | 56 | 19 |
| `rounds.closable_holes` round-1 universe | 56 | 19 |
| `sizing.implied_size:75` | 87 implied | 38 (reads the field; no edit) |

The seal-check identity `limitations.md` protects is preserved by changing both
spellings in one commit.

`rounds._declared_cells` is **not** where the filter goes. It doubles as the
malformed-world-model door (`rounds.py:152-186`), and an unbound capability
missing `outcome_classes` must still be caught there. Filter at `closable_holes`
and `capability_matrix`; leave the door wide.

### The one check that would otherwise fire falsely

`refs.check_coverage:2746` compares matrix rows against wide `_cells`:

```python
for missing in sorted(cells - seen):
    report("/capability_matrix/cells", f"matrix omits cell {cell_ref(*missing)}")
```

A narrowed matrix makes that report 37 fabricated findings against a correct
document. **That comparison, and only that one, moves to `drivable_cells`.**

Verified against the shipped code: hole-ref resolution at `:2841` uses wide
`cells` (so the new holes resolve), and `uncovered`/`covered` at `:2852-2859`
derive from `matrix_cells` (so extra holes for cells outside the matrix are in
neither set, and neither hole direction fires). The existing checks already
tolerate the new holes.

### Undrivable cells stay accounted for

`score-seal` emits one mechanical hole per undrivable cell, in the existing
vocabulary -- no schema change:

```json
{"ref": "cell:cap-keycloak/oc-1", "reason": "unreachable",
 "justification": "capability declares no binding.tool; emit.bindings cannot turn it into a tool call"}
```

`rb-score` §411 already defines `unreachable` as "no scenario could exercise this
row against this target at all". This is that, computed. Consequences: the
coverage report still accounts for all 56 cells; `propose` stops spending rounds
on them, since `unreachable` is not closable; `converged` becomes reachable.

This is code rather than the prompt because binding absence is a fact on disk,
not a judgment, and `score-seal` already owns the matrices. It also removes work
from the prompt without removing a decision from it.

**`sizing.implied_size:82` must not subtract these.** It subtracts
`blocked_by_gap` holes today; `unreachable` cells are already outside the
narrowed count, and subtracting twice under-reports.

### Making the exclusion visible

Three reporting changes. None asserts a cause code cannot compute.

1. **A `check-refs` finding at the seal**, naming the unbound capabilities and
   the cell count they carry. This moves the earliest signal from stage 06 to
   gate 1. Today the only report is `emit.py:105`, whose remediation -- "add
   binding.tool and binding.fixed_args in the world model" -- asks a human to
   hand-edit a frozen, sealed artifact. This is the "no silent caps" discipline
   the repository already applies: a bounded-coverage decision is logged where it
   is made.

   **This one did not ship. Reporting change 2 is the sole surface.** The finding
   was implemented (`ae1b74e`) and taken back out (`11a6c25`), because it
   miscategorised its own condition: `check-refs` exit 1 tells `rb-orchestrate` "a
   repairable stage defect, spend the one repair attempt", and an unbound
   capability is repairable by no re-dispatch at all --
   `rb-reconcile-capabilities`' section 5 tells the pass to leave `binding` off
   rather than guess a tool name, so the pass did the right thing and nothing
   downstream can add one. `check-refs` also runs *before* human gate 1, so the
   finding halted a correct run ahead of the gate it was designed to be read at,
   19 of 24 capabilities' worth on `run-20260827-070444`. **The reason is the
   exit-1 semantics, not a change of mind about visibility** -- so do not
   re-propose the finding on the grounds that the exclusion deserves an earlier
   signal. The layer for that is the one CLAUDE.md keeps for reports that always
   exit clean on a readable run, which is `gate-brief`.
2. **A `gate-brief` gate-1 listing**: each excluded capability with its cell
   count, `operation`, and citing inputs read off `01-claims/`. That makes the
   real cause legible without claiming it -- a human reading it sees that 10 of
   19 trace to `pyproject-toml`. Recording the cause *as data* would need a
   schema field and a prompt rule, which is a separate, dispatch-measured change.
3. **A new `limitations.md` entry** for group C: `binding` is
   `{tool, fixed_args}`-shaped, so the pipeline structurally cannot emit a test
   for non-tool agent behaviour. `cap-empty-search-guidance` is real, observed in
   a captured trajectory, drivable through `http-sse`, and unshippable.
   `grep -i "non-tool|conversational|agent-level"` over `limitations.md` and
   `rationale.md` returns nothing, so this is newly identified -- and the
   narrowing would otherwise absorb it silently.

## Testing

Every capability in `toy/`, `toy-gap/` and `toy-contradiction/` is bound, so the
narrowing is a no-op on all three fixtures. That is convenient -- no fixture
churn, and the parked ruling about the recorded denominators (`limitations.md`,
"The coverage denominator is arithmetic done by code") is undisturbed -- but it
also means **no existing test reaches the unbound path.** New tests must
construct one.

- `drivable_cells` and `_cells` diverge on a mixed world model, and the
  seal-check identity holds across it.
- `check_coverage` exits clean on a narrowed matrix plus mechanical `unreachable`
  holes. This is the regression guard for the fabricated-findings hazard above,
  and it must be measured in both directions: revert the `check_coverage` change
  and confirm it goes red.
- `closable_holes` omits undrivable cells on round 1.
- `implied_size` narrows and does not double-subtract.
- Unreadable-input paths for every touched check (`chmod 000`, `chmod 0444`), per
  CLAUDE.md's rule for `refs.py` and `paths.py`.

`make test` green, `make check` clean, and `uv run rubrica check-skills` exiting
0 are the gates.

## Out of scope, each with its reason

- **`underspecified` cells** -- a deliberate inclusion, argued in `rb-propose`
  §221-228.
- **Bumping `denominator.version`** -- it is a per-run amendment counter, and
  nothing compares `capability_cells` across runs.
- **The `rb-reconcile-capabilities` accounting shape** -- the issue's third
  suggestion, and the `pyproject-toml` finding argues it is the real magnitude
  driver. It is a prompt change that only a paid dispatch can validate, and
  entangling it here would block a deterministic fix behind that dispatch.
- **Making group C bindable** -- the root fix for the third reporting change
  above, requiring schema, `emit` and verifier changes.
