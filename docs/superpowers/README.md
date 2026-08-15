# This tree is history, not documentation

Everything under `docs/superpowers/` is a dated design record or
implementation plan, written during this project's build. Each one is
accurate as of the date in its filename or its own text — nothing more.

**This is not documentation.** It is not maintained: counts, statuses, and
"current state" statements here are snapshots from whenever they were
written, not facts about the repository today. Some of it even names skills
by a `tg-` prefix that was later renamed to `rb-`; that rename is real and
current, and this tree was never updated to reflect it.

**Do not cite anything here as current.** For the current documentation,
start at [`docs/README.md`](../README.md). For why the system is shaped the
way it is, see [`docs/design/rationale.md`](../design/rationale.md). For what
does not work yet, and the ruling that parked each item, see
[`docs/design/limitations.md`](../design/limitations.md).

**Do not edit anything in this tree.** A dated record is not updated to track
a later rename, a later fix, or a later ruling — being left exactly as
written is what makes it a record rather than a stale draft.

**Why it is kept:** the reasoning behind a decision often survives only in
the record that made it. A fixture or a test may legitimately cite a plan or
a spec in this tree as provenance for why it exists in its current form.
