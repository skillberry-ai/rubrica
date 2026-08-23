# This directory is a record, not a skill

`rb-reconcile` was one stage that read every claims file and wrote the whole
world model in one dispatch. It was replaced by the `reconcile-*` family and a
code seal, because a single dispatch had to think for minutes before writing its
first byte and the gateway closes a silent stream at ~300s.

`exercise.md` beside this file records what two real dispatches of that stage
measurably did. It is **not** an exercise record for any current skill and was
not relocated into one: moving it would assert that a dispatch of some
`rb-reconcile-*` pass did what the superseded stage actually did, which is the
misattribution this project has already retracted once.

There is no `SKILL.md` here, and nothing looks for one: `skills._skill_dirs`
keeps only children that have one, `expected_skill_names` derives from
`paths.STAGES`, and no code in this repository reads an `exercise.md`.

What replaced it, as it now stands: `docs/concepts/pipeline.md` ("Reconcile is one
logical step, engineered as substeps") for the shape, and
`docs/design/limitations.md` for what the split cost and what is still unmeasured.
The dated design record this file used to point at is superseded history: it was
headed "no implementation yet", which stopped being true when the family shipped.
