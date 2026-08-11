# Renaming `test-generator` to Rubrica

**Date:** 2026-08-11

Replace the generic project name `test-generator`, and the `testgen` identity it
carries into the code, the CLI, the environment, the skill directories and the
emitted Harbor packages, with **Rubrica**.

This is a naming and identity change. No stage's judgment, no schema, no gate
and no exit-code behaviour changes. One thing genuinely breaks, deliberately:
the emitted scoring contract's version string (§6).

## 1. The decision

The project is **Rubrica**. The distribution, the console script and the
importable package all take that single name:

- PyPI distribution `rubrica`
- console script `rubrica`
- `import rubrica`

Latin *rubrica* is red ochre — the red pigment used for the headings a scribe
added to tell a reader how to use a text — and it is the direct ancestor of
English *rubric*, the standard term for a scoring guide. A Red Hat project whose
output is a scoring rubric, named with the Latin word for red.

## 2. Why this name, and what it cost to check

Availability was measured, not assumed. `rubrica` is unclaimed on PyPI, npm and
RubyGems. GitHub returns 2,563 name matches, but the largest is 12 stars: no
notable software competes for the name. crates.io returned 403 from the checking
environment and is the one registry still worth a manual look.

**The recorded caveat.** `rubrica` is a common word in three living languages,
and in only one of them does it mean what we intend:

| Language | Reading |
|---|---|
| English (via *rubric*) | a scoring guide — the intended reading |
| Italian | **address book / phone contacts** — the primary reading |
| Portuguese (BR) | initials, a signature |
| Spanish | signature flourish; also rubric |

The GitHub result set shows this directly: the hits are phone-book exercises and
ICP-Brasil digital-signature clients, not assessment tools. Red Hat has
substantial engineering in Italy and Brazil, so a share of the internal audience
will read the name differently than intended.

This was accepted as a cost rather than a blocker. Context disambiguates
strongly — nobody meeting an agent-evaluation tool concludes it manages contacts
— and no real software holds the name. It is recorded here so that a future
reader knows it was seen and weighed, not missed.

**Alternatives considered and rejected.** `Etalon` (metrology's word for the
artifact that *is* the reference standard) was the runner-up and remains free
everywhere; it was rejected only because it does not self-describe. `Rubrum`
(free on PyPI and npm) avoids the second-language baggage but loses the
*rubric → scoring guide* link that motivated the choice, trading a small cost for
a real loss. `Rubedo` is out: PyPI and npm both taken, plus a 488-star GitHub
project. The Socratic vein — `Elenchus`, `Elenctic` — is compromised by a live
PyPI project named `elenchus` doing *dialectical knowledge base construction*,
which is close enough to this project's domain to confuse people. Nautical names
pairing with Harbor were explored first and abandoned: the word "Harbor" is
already owned in infra by the CNCF container registry, the vocabulary is heavily
mined (11 of the first 17 obvious words are taken on PyPI), and naming this
project for its adjacency to Harbor would misdescribe an architecture in which
`emit` is deliberately the only Harbor-aware module.

## 3. Identity mapping

| | Now | After |
|---|---|---|
| Project / repo | `test-generator` | Rubrica |
| Distribution | `test-generator` | `rubrica` |
| Console script | `testgen` | `rubrica` |
| Package | `src/testgen/` | `src/rubrica/` |
| Skill directories | `tg-*` | `rb-*` |
| Schema dir override | `TESTGEN_SCHEMA_DIR` | `RUBRICA_SCHEMA_DIR` |
| Skills dir override | `TESTGEN_SKILLS_DIR` | `RUBRICA_SKILLS_DIR` |
| Suite dir override | `TESTGEN_SUITE_DIR` | `RUBRICA_SUITE_DIR` |
| Live-test gate | `TESTGEN_LIVE` | `RUBRICA_LIVE` |
| Scoring contract | `testgen/v1` | `rubrica/v1` |
| Suite name | `testgen` | `rubrica` |
| Measurement format id (recall) | `testgen-recall/1` | `rubrica-recall/1` |
| Measurement format id (review) | `testgen-review/1` | `rubrica-review/1` |
| Measurement format id (stability) | `testgen-stability/1` | `rubrica-stability/1` |

The `rb-` prefix mirrors the two-character shape of `tg-`, so the many
documentation tables that list skill names keep their column widths.

**No back-compatibility aliases.** No `TESTGEN_*` fallbacks, no `testgen`
console-script shim, no deprecation period. The project is at 0.1.0 with no
external users and no sibling repository in `~/work/kaegis/` references it — this
was checked. An alias would be permanent surface area bought for nobody.

## 4. Measured scope

The sweep touches **89 files**: roughly 478 occurrences of `testgen` and 360 of
`tg-*` skill names, across source, tests, `pyproject.toml`, the Makefile and
`README.md`.

Most of it is mechanical. The parts that are not are enumerated in §5, and they
are the reason this is a reviewed change rather than one `sed` invocation.

## 5. The five places a blind replacement does damage

1. **`skills.py` hardcodes the prefix in three places** — `ORCHESTRATOR` at
   `:41`, the expected-name tuple at `:157`, and the per-skill name check at
   `:306`. All three must move together or `check-skills` starts rejecting every
   correctly named skill.

2. **The `check-skills` negative fixtures are deliberately invalid names** —
   `tg-extractt`, `tg-bogus`, `tg-smoke` and `tg-intake` exist to prove the check
   rejects a misspelling, an unknown skill, and the two code-only stages that
   must not have skills at all. A partial rename leaves them passing for the
   wrong reason: they would still be rejected, but as *unrecognised prefixes*
   rather than as the specific defects they were written to catch. Each moves to
   its `rb-*` equivalent, and each must be confirmed to still fail **for the same
   reason** — the same message, with only the renamed prefix differing — per the
   repository's rule that a predicate nobody has watched fail is not yet a guard.

3. **`emit.py` writes the name into artifacts** — `SUITE_NAME` at `:44` and the
   "generated by testgen" provenance line at `:211`. These reach the emitted
   package, not just the source tree.

4. **`suite/test.sh` is copied verbatim into every package** — its header
   comments at `:2` and `:10` name the tool, so its bytes ship. Editing it
   changes every emitted package's contents.

5. **A guard is written in terms of the old package name.**
   `tests/unit/test_verify_reward.py:736-738` walks `verify.py`'s AST and asserts
   no import name starts with `"testgen"` — this is what keeps the verifier
   stdlib-only so it can run inside a bare container. Rename the package and
   leave the string, and the guard tests for a prefix that no longer exists: it
   passes unconditionally, forever, while appearing to hold. This is the
   substring-of-message weakness the repository already warns about, aimed at
   itself, and it is the single most dangerous line in the sweep.

## 6. The wire-format break, and why it is accepted

Two identifiers carry the name into the emitted packages, and they differ in
kind:

- `verify.CONTRACT` is a **wire format version**, written into each package's
  `expected.json` and checked by the verifier copied into that same package.
  Per the existing design, a contract the verifier cannot read is **refused, not
  scored zero**: it writes `reward-detail.json` with the error, writes no
  `reward.txt`, and exits 2, so Harbor sees a missing reward rather than a real
  one. That behaviour is correct and unchanged.
- `emit.SUITE_NAME` is **task identity in Harbor**, reaching `task.toml` as
  `name = "<suite>/<scenario_id>"` and as the `suite` field.

Both are renamed. The consequence is explicit: **a package emitted before this
change, run against a verifier from after it, is refused.** Every previously
emitted suite must be re-emitted, and newly emitted tasks carry new Harbor
identities (`rubrica/scn-empty`, not `testgen/scn-empty`), so historical results
will not line up with new ones by task name.

A third kind of identifier also carries the name but does *not* reach an
emitted package, so it does not disturb the "two identifiers" claim that opens
this section: `recall.py:238`, `stability.py:198` and `review.py:272` each
write a `format` field — `testgen-{recall,review,stability}/1` → `rubrica-*`
(§3) — into files under `measurement/`, this project's own on-disk record of a
run, never into `task.toml` or anything Harbor sees. These three are a
separate, sibling case, pinned by `tests/unit/test_measurement_contract.py:52-54`.

Freezing `testgen/v1` as a legacy wire id was considered and rejected: it would
leave the old name permanently visible in the artifacts the project exists to
produce, in exchange for compatibility with suites that, at 0.1.0, may not exist
anywhere yet. Confirm nothing is currently registered in Harbor from this
generator before re-emitting; if that holds, this break costs nothing in
practice.

Because `SUITE_NAME` changes emitted bytes, the byte-stability guarantee that
justifies `emit` being code rather than a prompt must be re-demonstrated, not
assumed — see §8.

## 7. Documentation policy

**Dated design records stay verbatim.** The `docs/` tree is already excluded from
ruff precisely so that committed design records are not reformatted, and the same
reasoning applies to a rename: a record of what was decided on 2026-08-06
describes a project that was called `test-generator` at the time. Rewriting it
would make the record describe a past that did not happen.

- `docs/superpowers/specs/2026-08-06-skill-based-test-generator-design.md` —
  unchanged except for a dated rename note at the top pointing here.
- `docs/superpowers/plans/*` — unchanged.
- `README.md`, `CLAUDE.md`, `docs/running-a-stage-by-hand.md` — rewritten. These
  are living documents; the last is a procedure that would otherwise instruct a
  reader to run commands that no longer exist.
- `src/*/skills/*/exercise.md` — **commands rewritten, measured results
  untouched.** These live beside the skill they describe *in the repository*,
  but do not ship: `pyproject.toml`'s package-data lists `skills/*/SKILL.md`
  only, so no wheel contains an `exercise.md`. That does not change the
  argument here — a repo reader following an exercise record to reproduce a
  dispatch needs a command that still exists, whether or not a wheel ever sees
  the file. An exercise record states what happened, and a rename changes no
  measurement: every number, verdict and quoted model output stays exactly as
  recorded. Only the invocation lines move.

## 8. Verification gate

All four are required, and each is a command whose output must be read, not
assumed:

1. `make test` — **1126 passed, 4 skipped**, the documented baseline. Any other
   number means something broke.
2. `make check` — ruff check and format check clean, no changes. `README.md` is
   not excluded from ruff, so this covers the rewritten README.
3. `rubrica check-skills` — exit 0, proving the eight renamed contracts still
   hold to `paths.RunPaths` attribute names, `validate.STAGE_ARTIFACTS` and
   `cli.SUBCOMMANDS`.
4. **Byte-stability re-demonstrated** — emit the toy suite twice into separate
   directories from identical stage-4 and stage-5 artifacts, and diff the trees.
   They must be byte-identical. This is the guarantee that lets run-to-run
   variance be attributed to a stage, and §6 changed the bytes it applies to.

Additionally, and separately from the suite passing: each renamed negative
fixture in §5.2 must be observed failing, with the message it produced before the
rename and only the prefix differing.

## 9. Out of scope

Left for a human, with steps to be listed at hand-off:

- Renaming the working directory and the GitHub repository.
- Registering `rubrica` on PyPI, and the manual crates.io check from §2.
- Re-emitting and re-registering any suite already present in Harbor (§6).

## 10. What this design deliberately does not do

- No back-compatibility aliases or shims (§3).
- No rewriting of dated design records (§7).
- No change to any stage's judgment, schema, gate behaviour or exit code. Every
  `SKILL.md` prompt *did* change — the CLI name a model is instructed to run
  moved — 64 occurrences across the eight files, counted at the commit before
  the skill rename rather than estimated — and all eight digests
  changed as a direct result (the ruling below concedes this) — but only in
  that one respect: the command a stage names, never what it decides, checks,
  or is graded on. A rename that altered what a stage decides would make the
  pipeline's falsifiable question harder to answer, which is the one thing
  this repository asks changes not to do.
- No re-recording of `tests/fixtures/*/recorded/01-world-model.json`. The rule
  that changing a skill obliges re-recording exists because a changed skill may
  no longer produce the recorded output. Here the recordings carry no skill
  digests — `skill_sha256` lives only in a run's uncommitted `manifest.json` —
  and renaming an invoked subcommand changes no skill's judgment, so the
  recordings still attest to what they claim. No paid re-dispatch is needed.

  **Ruling, added 2026-08-11 during implementation.** Those recordings turn out
  to name the old skills *inside the recorded model output itself* — the
  `why_it_matters` fields say "tg-propose cannot design…". They keep that
  spelling. A recording states what a model actually produced on a particular
  day, and on that day the skill was called `tg-propose`; rewriting the text to
  match today's directory names would be fabricating evidence, which this
  repository treats as its worst failure mode. The test that quotes those fields
  keeps the old spelling for the same reason, with a comment saying so. Note
  precisely what that test quotes, since the first draft of this ruling
  overstated it: the sentence in `test_refusals_live.py` is an *abridged*
  quotation of the recorded output, not a byte-exact one — what is verbatim is
  the gap id `gap-invalid-argument-behavior`. The retention argument does not
  need byte-exactness and is stronger without it: editing an abridged quotation
  still attributes words to the model that it did not produce.
  The eight `SKILL.md` digests did change, which under a literal reading of
  "changing a skill obliges re-recording" makes both recordings formally stale —
  but the obligation exists because a changed skill may no longer produce the
  recorded output, and a renamed subcommand changes no judgment. Paying for a
  re-dispatch here would buy a differently-worded artifact, not a truer one.
