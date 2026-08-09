# tg-extract -- live exercise

`tests/unit/test_skills_extract.py` and `skills.check_contract` can confirm
this skill's *shape*. Neither can confirm that a model actually dispatched
with this prompt behaves the way the design intends. This file records what
the live exercise checks instead, so the controller running it -- and
anyone reading its result later -- knows what "passed" is supposed to mean.

## Setup

Build a toy run stopped after `intake`:

```python
build_toy_run(runs_dir, upto="intake")
```

Dispatch `tg-extract` three times, once per registered input artifact
(`api-json`, `notes-md`, `trace-json`), each dispatch told only the one
`artifact_id` it is responsible for -- never the other two.

## Pass criteria

- Three files exist under `01-claims/`: `api-json.json`, `notes-md.json`,
  and `trace-json.json`. Note the second one in particular: the claims
  filename is `<artifact_id>.json` regardless of the input file's own
  suffix, because `paths.claims` builds it from the `artifact_id`, not from
  `stored_as`. The input was registered as `notes-md.md`; a run that
  mirrors the input's own suffix would write `notes-md.md.json` or
  `notes-md.md` instead, either of which `refs.check_manifest` reports as a
  filename that disagrees with its own declared `artifact_id`.
- `testgen validate --stage extract` exits 0.
- `testgen check-refs` exits 0.
- No claim id appears in two files.

## The property no automated test can check

There are two versions of this, one blatant and one subtle. No test in
`test_skills_extract.py` can catch either -- reading the actual claims text
by hand is the only check for both.

**The blatant version.** Does the subagent dispatched for `trace-json`
record something `clm-trace-002`-shaped -- that calling `get_ticket` with an
id no ticket has returned an empty object, read straight off the trace,
`derivation: reverse_engineered` -- *without* also asserting the documented
error behaviour ("`get_ticket` with an unknown id is an error, not an empty
result") that lives in `notes.md`, an artifact this subagent never read? If
the `trace-json` output imports that error-behaviour claim outright, the
fan-out isolation is not holding: information crossed from one subagent's
context into another's that the contract's `reads` list was supposed to make
impossible for it to see.

**The subtle version, and the more likely one.** Read every `trace-json`
claim's `statement` for a word characterizing the observed response as
`unusual`, `unexpected`, `atypical`, `surprising`, or as probably a bug --
or any paraphrase of "APIs typically ...", "usually ...", "one would expect
...". Treat the presence of any such characterization as a finding, *even
when* no sibling file was read and no undocumented error class was
invented outright. A claim can satisfy every mechanical rule in this
skill -- read only its own file, invent no new error class -- and still
smuggle in exactly the judgment `notes.md` states, just phrased as the
subagent's own observation about what is normal rather than as a citation
of the document that says so. That is the leak Refusal condition 5 in
`SKILL.md` names, and this read is the only way to confirm the trigger
actually fires rather than merely existing on the page. If characterizing
language shows up in a `trace-json` claim, the fix is not a patch to this
run -- it is Refusal condition 5 needing sharper trigger wording or a
stronger worked example.
