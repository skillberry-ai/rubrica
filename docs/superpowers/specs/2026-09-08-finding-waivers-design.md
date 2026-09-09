# Findings a human may waive, and where the remedy lives

## Why

`refs.check_claim_utilisation` raises its finding against `01-world-model.json`.
No dispatchable stage declares that artifact in `writes` — its only author is
`reconcile-seal`, which is code and makes no judgments. So when the finding is
correct and unfixable, the orchestrator's one repair attempt is not *exhausted*,
it is **unspendable**: every pass it could dispatch must refuse, because the
finding names a file that is not its output. `rb-orchestrate`'s A4 has nowhere to
spend the budget, B4's halt is the only compliant move, and `check-refs` exits 1
for the rest of the run.

That last part is the cost that compounds. An exit 1 nobody can clear makes every
later exit 1 uninformative: a reader walking the remaining stages has to diff the
finding text by hand at each gate to notice whether anything new appeared.

[`../../design/limitations.md`](../../design/limitations.md) already rules on this
shape, under *"A re-seed whose remedy lies outside `rb-instantiate`'s `writes`
cannot be repaired at all"*:

> What is actually owed is a *disposition* for this case — a way for the pipeline
> to record "unrepairable here, remedy lives upstream" as a first-class outcome
> rather than as a stage declining and an `emit` exit 1.

The entry below it, *"The rejection notice cannot express an escalated re-seed"*,
is the same missing concept seen from a third place, and says so: *"both are the
same missing concept."* This design builds that concept once, so the next
instance is a registry row rather than a third patch.

## The instance that forced it

Measured on a tau2-airline run of 36 inputs. `check-refs` exited 1 from gate 1
onward with two findings, unchanged across six subsequent stages:

```
[refs] .../01-world-model.json#/: no world-model element cites any claim from episode-scores-json (11 claims)
[refs] .../01-world-model.json#/: no world-model element cites any claim from llm-agent-py (25 claims)
```

Every link in the chain is defensible on its own terms, which is what makes it a
design hole rather than a defect:

- Gate 0 admitted both files on harness-contract grounds, naming the
  harness/target boundary explicitly in each admit rationale.
- All seven reconcile passes independently declined both, each recording its own
  reason in its own `inputs_seen` — the claims describe the test harness's
  scaffolding, not the target's domain.
- The orchestrator spent its repair on `reconcile-entities`, which refused as
  out-of-domain. A further attempt on `reconcile-subjects` refused with the
  sharper argument: the finding names `01-world-model.json`, which is not its
  artifact.

So the finding is addressed to a file whose only author makes no judgments, and it
is *about* judgments seven stages made correctly. `check_claim_utilisation`'s
docstring names two causes, both real defects — `rb-extract` produced nothing
usable, or the reconcile passes ignored a whole artifact. There is a third it
cannot distinguish: extract produced good claims and every pass correctly declined
them. The check's one exemption (a claims file with zero claims) is the wrong one
for this case; it exempts the artifact extract found nothing in, and reports the
artifact the reconcile family deliberately dropped.

## What a waiver is, and what it is not

A waiver records that **a finding is correct and the remedy is not available
here.** It is not an assertion that the finding was wrong, and it is not a mute
button: the finding keeps printing.

Three properties carry that distinction, and each is load-bearing.

**A human writes it, never a stage and never the orchestrator.** The gate-0
argument in [`../../../CLAUDE.md`](../../../CLAUDE.md) applies unchanged: the same
party selecting the inputs and ratifying the selection would make the run
unfalsifiable. An orchestrator that could waive its own unspendable budget would
be diagnosing and ratifying in one move, and a stage that could waive a finding
about its own drop would be vouching for its own refusal. Both are the
arrangement gates exist to forbid. The cost is accepted deliberately: an
unattended run still halts, and a person still has to rule.

**It names where the remedy lives.** `remedy` is required. That is what makes the
record an escalation rather than a suppression, and it is the field a later reader
uses to find the actual defect. For the instance above the honest value is
`triage-rule` — the admit decision is where the disagreement began.

**It cannot be written for a finding that is not raised.** `rubrica waive` runs
the named check and refuses if nothing matches the subject. So there are no
pre-emptive waivers, no waivers left behind by a fixed defect, and `finding_text`
is copied from the finding rather than typed by hand — the same discipline as the
orchestrator appending findings verbatim, for the same reason.

## The artifact

A run-level `waivers.json`, reached as `run.waivers`, beside `manifest.json` and
`decisions.md` — a `@property` on `RunPaths` returning `self.root / "waivers.json"`.
Schema `waivers-0.1.json`, `additionalProperties: false` throughout.

```json
{ "schema_version": "0.1",
  "waivers": [
    { "id": "wv-0001",
      "check": "claim-utilisation",
      "subject": "llm-agent-py",
      "remedy": "triage-rule",
      "reason": "harness contract admitted at gate 0; every reconcile pass correctly declined it as out-of-target-domain",
      "finding_text": "no world-model element cites any claim from llm-agent-py (25 claims)",
      "recorded_at": "2026-09-08T04:12:33Z" } ] }
```

It is **not** in `validate.STAGE_ARTIFACTS`. It is nobody's stage output, so no
stage gains a `writes` entry, no skill contract changes, and `check-skills` has
nothing new to bind. It is append-only. Revoking a waiver means a human deletes
the entry, which is a visible edit to a tracked file; there is no `--revoke` until
something needs one.

`remedy` is an enum: every name in `paths.STAGES`, plus `outside-the-run` and
`none`. `none` has to exist or the ruling this design was built for is
inexpressible — the reconcile drops were *correct*, and a human who believes no
artifact should change must not be forced to name a remedy they do not believe in.
`none` therefore means "accepted, permanently", and reads differently from a
deferral everywhere it is displayed.

Why a new artifact rather than a field on the manifest: the manifest is intake's
identity-and-reproducibility document, and `diff-runs` reads its stage map. Human
rulings in there would mix a judgment record into the evidence record, which is
the confusion that makes `model` unreliable in the first place.

## The registry

A new module, `src/rubrica/waivers.py`, holding the registry, the loader, and an
`is_waived(check, subject)` predicate. Not `refs.py`, which is already the largest
module in the package and the one this repo's own instructions single out for
unreadable-input care.

```python
WAIVABLE_CHECKS: dict[str, str] = {
    "claim-utilisation": "artifact_id",   # what `subject` names for this check
}
```

The value documents what a subject *is* for that check, so the CLI can say so in
an error and a document can render it. A check absent from this mapping is not
waivable, and `waive` rejects it as a usage error rather than recording a waiver
nothing will ever read.

This is the mechanism the two parked entries reuse. Unparking each is a row here
plus a subject key on the finding that check raises — not another artifact and not
another subcommand.

## `rubrica waive`

```
rubrica waive --run R --check claim-utilisation --subject llm-agent-py \
              --remedy triage-rule --reason "..."
```

It runs the named check, matches the subject against the findings that check
returned, and appends one entry with `finding_text` taken from the matched
finding. There is no `--finding-text` flag, because a human retyping a finding is
a human who can paraphrase one. It also appends a line to `decisions.md`, so the
prose trail stays in the file a human already reads at every gate.

`id` is `wv-` and a zero-padded sequence one past the highest already present, so
two waivers written in either order never collide and the file reads
chronologically.

## What `check-refs` does with it

`Finding` gains `waived: bool = False` as its last field. The dataclass is frozen
and every existing construction is positional or keyword on the four fields it
has, so a defaulted fifth is additive.

`check_claim_utilisation` marks a finding whose `(check, subject)` pair is waived
rather than dropping it. `_report` then splits what it was handed:

- waived findings still print, each prefixed `[waived] `
- only unwaived findings decide the exit code

So the run above returns to exit 0 with both lines still on stdout. The
exit-code contract is unchanged in the way that matters: a `1` still means
unwaived findings, one per line, and still never has empty stdout.

The split lives in `_report` rather than in the `check-refs` branch so it is
uniform across every command that reports findings, and inert for every command
whose checks never set the flag.

Matching is on `(check, subject)`, never on message text. A text key would break
on a reformat that changed nothing — the failure this repo has already taken once,
recorded as a phrase pin that broke on an innocuous rewording. `finding_text` is
recorded so the pairing stays auditable and a report can show drift; it is
evidence, not a key.

## Gate 1's surface

`gate-brief` lists the active waivers at each gate: id, check, subject, remedy,
reason. A waived finding should be something a human re-reads at every subsequent
gate, not something that disappears after one ruling. `remedy: none` renders
distinctly from a stage name, because the two say different things about whether
anybody still owes work.

`gate-brief` remains a report and still always exits clean on a readable run.

## Exit codes and the failure surface

- An absent `waivers.json` is normal and silent: most runs have none.
- A malformed or unreadable `waivers.json` is **exit 2**. It is a misconfigured
  run, no stage re-dispatch repairs it, and a `1` there would spend the run's one
  repair attempt on a stage whose output was never the problem — the same ruling
  already made for an unreadable model-written part and for an unwritable
  interfaces directory. Failing open would be *safe*, since the finding would
  simply reappear, and is rejected anyway: it would hide a corrupted human record
  behind a correct-looking gate.
- An unknown `--check`, a `--remedy` outside the enum, or a `--subject` with no
  live finding is exit 2, a usage error.
- A stage defect must still never surface as 2, and nothing here introduces one:
  every path above is a bad human artifact or a bad invocation.

## What must not break

- The exit-code contract's two invariants. A waived-only run exits 0; a run with
  any unwaived finding exits 1 with those lines on stdout.
- `diff-runs`' comparability. It reads the manifest; waivers are not in it.
- The byte shape of `01-world-model.json`. Nothing here writes to it.
- Skill contracts. No `reads` or `writes` list changes, so `check-skills` is
  untouched and no stage learns about waivers. The judgment stays in code.
- A waiver must not suppress a finding it was not written for. A different
  subject, a different check, or a different run must still report.
- The rule that an **exit 2 prints no finding line**. Measured: every
  empty-stdout assertion in the suite guards an exit-2 path — a filesystem
  problem, a usage error, a misconfigured schema set — and none of them asserts
  that a clean exit-0 run prints nothing. `_report` is only reached on the
  success path, so a `[waived] ` line cannot appear under an exit 2.

## Testing

Test-first, and every predicate measured in both directions before it counts as a
guard — blank the prose or the condition it claims to check, confirm red; reword
meaning-preservingly, confirm green.

- exit 1 becomes 0 when the only finding is waived, and stays 1 when an unwaived
  finding remains beside it
- the `[waived] ` lines appear on stdout at exit 0
- a waiver whose subject differs does not suppress
- `waive` refuses a subject with no live finding, and records `finding_text`
  byte-identical to the finding it matched
- `waive` refuses an unregistered check and an out-of-enum remedy
- the unreadable-input paths named in the repo's instructions for anything
  touching `cli.py` or `refs.py`: `chmod 000`, malformed JSON, and a bad
  `RUBRICA_SCHEMA_DIR`
- `id` allocation is one past the highest present, including when the file holds
  a gap in the sequence

## Documents to update

- `docs/reference/cli.md` — a `rubrica waive` section, which
  `test_docs_accuracy.py` requires for every entry in `cli.SUBCOMMANDS`
- `docs/reference/artifacts.md` — the `waivers` kind. Documented because a
  reader needs it, **not** because a test demands it: that parametrization
  derives from `STAGE_ARTIFACTS`, which this kind is deliberately outside. It
  joins `ARTIFACT_SCHEMAS` so it can be schema-validated, and stays out of both
  `STAGE_ARTIFACTS` and `CONFIG_KINDS` — it is a fourth category, human-authored
  but living inside the run, where the config kinds never do.
- `docs/design/limitations.md` — both parked entries point at this mechanism, and
  the `check_claim_utilisation` third cause is recorded
- `CLAUDE.md` — `waive` in the deterministic-subcommands rulings, since it is a
  judgment rather than a list entry

`docs/concepts/pipeline.md` needs nothing: no stage is added, renamed, or
regated.

## Out of scope, each with its reason

- **Wiring the two parked instances.** The mechanism admits them, and each wants
  a run to test against rather than an untested registry row shipped on
  speculation.
- **Reopening the propose loop**, which the re-seed entry already rules out as the
  unbounded path.
- **Widening any stage's `writes`** to reach a barrier artifact, which the same
  entry rules out as giving a fan-out member write access to a file every sibling
  reads.
- **A `--revoke` flag.** Deleting an entry is a visible edit to a tracked file.
- **Making gate 0 and the reconcile family agree.** That is the upstream half,
  and it is a triage-guidance question rather than a pipeline-mechanism one.

## Open questions

- Whether `remedy: none` should additionally require a gate number, so a reader
  knows which human accepted it. The timestamp plus `decisions.md` may already be
  enough, and a field nothing reads is the shape this project cuts.
- Whether `waive` should refuse when the matched finding's text differs from a
  waiver already present for that `(check, subject)` — that is drift worth
  surfacing, and it may belong in `gate-brief` instead of in the writer.
