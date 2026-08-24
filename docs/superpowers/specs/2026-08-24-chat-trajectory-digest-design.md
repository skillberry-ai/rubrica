# Digesting a chat-message trajectory

**Date:** 2026-08-24
**Status:** design, approved in conversation; no implementation yet
**Issue:** #4.
**Supersedes:** §13 of the 2026-08-22 staged-triage design, three of whose
claims are measured false below. That file is recorded history and is not
edited; this section is where the correction lives.

---

## 1. The problem, root-caused

A corpus of OpenAI-style chat trajectories reaches triage as opaque rows. Every
number below was measured this session against
`tau2-bench/data/tau2/trajectories` (200 files, 4.5MB) and
`tau2-bench/src/tau2`, surveyed at defaults.

Baseline: 443 candidates, 444KB catalogue, kinds `{source_code: 224, other:
200, design_doc: 19}`, zero container elements, 7 slices. Nothing exceeds a cap;
the corpus is surveyable today and triages blind.

Issue #4 attributes this to two thresholds. **Both of its proposed levers are
measurably wrong, and neither is the root cause.**

| the issue's claim | measurement |
|---|---|
| relaxing `EXPLODE_MIN_COMMON_KEYS` to 2 admits chat messages | **0 of 200 files explode.** 895 of 5,182 messages are `{role, tool_calls}` and carry no `content`, so the per-file key intersection is `{role}` — one key — in all 200. Only a threshold of 1 admits them, and 1 is not a homogeneity test. |
| classifying the message elements `trace` fixes the digest | **4,267 of 5,182 (82%) fire zero heuristics.** Chat messages hold their text under `content`, which appears in none of `_REQUEST_KEYS`, `_STATUS_KEYS`, `_COUNT_KEYS` or `_NAME_KEYS`. Mean digest 39 bytes — thinner than the skeleton it would replace. |
| the 200 digests are "mutually indistinguishable" | **39 distinct**, largest identical group 18, differing only by message count. The conclusion survives, the wording does not. |

### 1.1 The unit is wrong, not the threshold

A tau2 trajectory is one episode: a system policy, then roughly 23 interleaved
user/assistant/tool messages in which message 7 is unreadable without 1 through
6. That is precisely `explode`'s documented *non*-exploding case — "an object
that is a single document with many sections rather than many documents", the
OpenAPI ruling — and not the case explosion exists for, which is a capture of
many independent whole records. **The file failing to explode is `explode`
working.**

The defect is one line, and it is on the digest side: `digest_for_payload`'s
trace branch guards on `isinstance(payload, dict)`, so a message *list* can
never reach it however it is classified.

### 1.2 The signal is present at file level

Measured across the 200 trajectories: **14 distinct tool names, 68 distinct
toolset signatures, 118 distinct first-user-message prefixes.** For scale, the
130-element parsec capture that motivated signature clustering carries 44
signatures. The discrimination a digest needs is there; nothing extracts it.

### 1.3 Why this is not in series behind #3

§13 of the staged-triage design says the two issues are in series and that
design is the prerequisite, on the grounds that fixing #4 turns this corpus into
~5,425 candidates and ~2.9MB. **That is true only of explosion, which §3.1
rejects.** Measured for the design in this document:

| route | candidates | catalogue | slices |
|---|---|---|---|
| today | 443 | 444KB | 7 |
| **this design** | **443** (unchanged) | **466KB** (+33KB) | ~7 |
| explosion | 5,425 (11× cap) | ~2.9MB (2.8× cap) | ~45 |

Nothing approaches a cap, so there is no ordering dependency. §13's third claim
— "on that corpus every skeleton is identical" — is false as measured (39
distinct); its *conclusion* holds for a different reason, recorded in §8.

## 2. What changes, and what does not

Changes:

- `digest.py` gains a public shape predicate and a message-list producer inside
  the trace branch (§4, §5).
- `intake.classify` gains one more way to reach `"trace"` (§5.3).
- `rb-extract` §3's capture-instant rule is widened to reach an instant stated
  in prose (§6).
- `limitations.md` records what this design does not solve (§8).

Does not change, and the spec says so because each has been proposed and is
wrong:

- **`survey.classify_payload`.** Its only caller is `survey.py:444`, on elements
  from `explode`, and `_homogeneous` requires *every* element to be a dict. It
  is never handed a list, so a message-list branch there is unreachable code.
- **`_REQUEST_KEYS`, `_STATUS_KEYS`, `_COUNT_KEYS`, `_NAME_KEYS`.** Widening any
  of them changes existing dict-shaped trace digests and obliges re-recording
  the committed fixtures. The message-list producer reads what it needs
  directly.
- **The `kind` enum** in `catalogue-0.1.json`. No new artifact kind, so no
  schema change, and `test_docs_accuracy.py` is out of scope.
- **`explode` and both caps.** See §3.

## 3. Rejected alternatives

### 3.1 Relaxing the explosion thresholds

Rejected on measurement (§1) and on meaning (§1.1). A threshold of 2 admits
nothing here; a threshold of 1 makes "any list of dicts sharing one key" a
record container; and a chat episode is not a set of independent records in the
first place.

### 3.2 A new `conversation` artifact kind

Rejected as cost without benefit. It touches the kind enum, both classifiers,
the survey and intake schemas, `docs/reference/artifacts.md`, and
`slices._signature`'s clustering eligibility, in exchange for a distinction no
consumer acts on: no code branches on `kind == "trace"` outside the classifiers
themselves. Widening `trace` leaves `heuristics_fired` — the field
`rb-triage-rule` calls the one that matters most — carried by the same kind that
already carries it.

### 3.3 Firing `error_markers` on an error-shaped tool result

Under the revised success bar (§3.5) this is rejected. The message-list producer
reuses `_has_error_key` unchanged, which fires on **0 of 200**. A rule matching
a tool result whose `content` begins with an error sentinel would fire on 12 of
200 — but that is the value inspection `digest.py` deliberately narrowed out,
and 0/200 with `heuristics_fired` saying so is the honest record the digest's
own doctrine asks for.

### 3.4 Going after the authoritative artifact instead

The corpus holds a second artifact for the same behaviour, and the trajectory
files are a lossy copy of it. `results/final/*.json` (26 files, 576MB) are
`{info, simulations, tasks, timestamp}`, where `simulations` is a list of 200
records with **13 identical keys** each: `messages`, `reward_info`,
`termination_reason`, `start_time`, `end_time`, `duration`, `task_id`, `trial`,
`seed`, `id`, and two cost fields.

Measured facts about that artifact:

- It does not explode, for a different reason than the trajectories: the
  top-level dict's values are `dict, list, list, str`, so `_homogeneous` refuses
  them. A container whose records sit under one key is invisible to explosion.
- `reward` is **1.0 for 100 records and 0.0 for 100** — a clean success/failure
  split. `termination_reason` is `user_stop` for all 200 and discriminates
  nothing.
- Its existing skeleton digest is already good: 43 nodes, **not truncated**,
  4,941 bytes, plainly showing `/simulations` as `array[200]` whose element
  carries `reward_info`, `messages` and `start_time`.
- Exploding it is not affordable today. Per-record canonical size is **mean
  38,723 bytes, max 111,626**, against `DEFAULT_SLICE_BYTES` of 65,536 — so
  `survey`'s row check exits 2 — and 200 records would put ~7.7MB against a 1MiB
  cap.

Rejected for this spec on scope, not on merit: envelope explosion changes what
every corpus yields and lands squarely in the row-bytes and catalogue-bytes
problem the staged-triage design owns. Recorded here rather than filed, by
ruling.

### 3.5 The success bar, and why it was revised

The bar was first set at *a rulable candidate* — `rb-triage-rule` admits or
declines on merit and `digest_insufficient` becomes rare. That bar is
**unreachable from these files**, and the reason is worth stating precisely
because it is not a weakness of any extractor: `rb-triage-rule` §3 step 2 rules
that "a failing trace is almost never a near-duplicate of a successful one", and
near-duplicate ruling is the dominant task on 200 trajectories carrying 68
signatures. The fact that decides it — `reward` — **is not in the trajectory
file**; it was dropped when the trajectory was projected out of the simulation
record (§3.4). No digest can carry a fact its file does not contain.

The bar is therefore *an informed decline*: a human at gate 0 can distinguish a
corpus carrying 14 tools and 68 behaviour signatures from one that is genuinely
opaque, and a member that declines names what it had. Decline rate is not a
target.

## 4. The shape rule

`digest.is_message_list(payload)`, public and in `digest.py` — a leaf module
importing only stdlib, so `intake` may import it with no cycle, and the shape
rule has one home rather than two spellings.

True when all of:

- `payload` is a list of length ≥ 2;
- every element is a dict;
- every element carries `role`;
- at least one element carries `content` or `tool_calls`;
- the number of distinct `role` values is at most `_SKELETON_MAX_CHILDREN` (32).

The role cap sits in the predicate rather than in a truncation flag, because it
bounds `element_counts` by construction and a payload with dozens of distinct
roles is not a conversation. Reusing the existing breadth constant avoids a new
number nobody has calibrated.

Measured precision: **200 of 200 tau2 trajectories; 0 of the 15 JSON fixtures
under `tests/fixtures/`; 0 of the `tau2-bench/src/tau2` tree.** Two keysets in
the corpus have only two keys (`{content, role}` and `{role, tool_calls}`), so a
key-count floor above 2 would defeat it.

## 5. The digest path

### 5.1 Structure

`digest_for_payload`'s trace branch splits into two producers that each return
`(result, fired)`, with the `heuristics_fired` tail assembled once from
`TRACE_HEURISTICS` — so the ordering keeps a single spelling. The dict producer
is the existing code, unchanged in behaviour. The message-list producer is
reached when `kind == "trace" and is_message_list(payload)`.

`digest_for_path` needs no change: it already delegates to
`digest_for_payload(payload, kind, ...)`.

### 5.2 Fields

| field | rule | tau2 |
|---|---|---|
| `element_counts` | `{"messages": N}` plus one `role_<role>` count per distinct role, bounded by §4's cap | 200/200 |
| `request_text` | the first `role: "user"` message's `content`, truncated to `body_chars`. **No fallback to the first message of any role**: the system prompt is corpus-wide boilerplate, measured at 118 distinct user prefixes against 1 system prefix, so a fallback would return the same bytes for nearly every candidate | 200/200 |
| `names` | the existing `_collect_names`, which already reaches `tool_calls[].function.name` within its depth budget, applied per message. `_MAX_NAMES` still caps it | 200/200 |
| `status` | never fired — a chat trajectory carries no terminal status field, and no key in `_STATUS_KEYS` appears in any of the 5,182 messages | 0/200 |
| `error_markers` | the existing structural `_has_error_key`, per message | 0/200 |

### 5.3 Classification

`intake.classify`'s list branch currently reaches `"trace"` only when
`payload[0]` carries `spans` or `trace_id`. It gains `is_message_list(payload)`
as a second route. Nothing else in that function changes.

### 5.4 The guard that must stay green

`test_a_non_dict_trace_payload_falls_back_to_the_generic_skeleton` passes
`["not", "a", "dict"]`, which fails §4's "every element is a dict" clause and
therefore still reaches the generic skeleton. **If that test needs editing, this
design has been implemented wrongly.**

## 6. `rb-extract`'s capture instant

Classifying these files `trace` activates §3's rule *"A state observation needs
its instant"*, which cites "the locator of the field it came from
(`/info/request_time` in an MLflow trace)". Measured: **0 of 200 trajectories
carry any time-shaped key.** The instant does exist — as prose in the system
message, `"The current time is 2024-05-15 15:00:00 EST."` at `/0/content` — so
the rule's letter is satisfiable while its worked example points somewhere this
artifact has nothing.

The rule is widened by one clause: where the capture states the instant in prose
rather than in a field, the citation is the locator of that message with the
sentence in `quote`. The widening is **additive**, and must be, because two
predicates in `test_skills_extract.py` pin six phrases inside section 3 —
`observed state`, `capture instant`, `request_time`, `declared contract`, `only
stage that reads this artifact`, `no later stage can recover`. All six survive;
a new predicate covers the added clause.

Editing a skill obliges re-recording its `exercise.md`. That obligation is
accepted here and discharged in §9, and the re-record is a reviewable diff
rather than silent drift.

## 7. Tests

In `tests/unit/test_digest.py`, in that module's style — inline payloads, each
docstring anchored to the decision the assertion protects:

- a chat trajectory digests to a trace-shaped digest carrying `element_counts`,
  `request_text` and `names`, with `request_text` taken from the user message
  and not the system prompt;
- `names` reaches `tool_calls[].function.name` specifically;
- `status` and `error_markers` are absent from `heuristics_fired` — the honesty
  assertion, mirroring the existing
  `test_a_heuristic_that_does_not_fire_is_absent_from_heuristics_fired`;
- a message-list trace digest carries no `skeleton` key, matching
  `test_trace_digests_carry_no_skeleton_key_at_all`;
- negatives, each a distinct clause of §4: a list of dicts without `role`; a
  one-element list; a list of strings (the existing guard, kept); a payload
  above the role cap.

In `tests/unit/test_intake.py`: `classify()` returns `"trace"` for a trajectory
file and `"other"` for a list of non-message dicts.

In `tests/unit/test_skills_extract.py`: one predicate for §6's added clause,
scoped with `section_body` to section 3 rather than checked against the whole
file.

Every new predicate is measured in both directions before commit — blank the
prose or shape it claims to check and confirm red, then restate it
meaning-preservingly and confirm green.

## 8. Limitations owed

Two corrections to `limitations.md`'s "Signature clustering is conditional, and
specific to traces", both measured, neither citing this document — only
`docs/README.md` may cite the recorded-history tree:

1. "on this corpus every skeleton is identical" becomes 39 distinct, largest
   group 18, differing only by message count. The entry's conclusion is
   preserved and re-grounded: clustering keys on `heuristics_fired` and `names`,
   which a skeleton digest carries neither of, so clustering is inapplicable
   regardless of how many distinct skeletons exist.
2. The series argument goes, replaced by §1.3's measurement. State what does
   *not* change: these are corpus candidates, not container elements, and
   `slices._signature` clusters only an oversized container's elements — so
   signature clustering still does not apply to them, and they are grouped by
   `(root_index, dirname)` as before.

One new entry: **a chat trajectory cannot say whether it succeeded.** The
deciding fact was dropped upstream of the corpus (§3.4), the digest is honest
about not having it, and near-duplicate ruling over 200 such candidates is
therefore unsound in a way no digest change can repair. This is the entry that
justifies §3.5's revised bar, and it names the envelope-explosion gap as the
route not taken.

## 9. Order of work

1. `is_message_list` and the producer split in `digest.py`, with the
   `test_digest.py` cases and the §4 negatives. Nothing else depends on more
   than this.
2. `intake.classify`'s branch and its two `test_intake.py` cases.
3. The end-to-end measurement on the real corpus (§10). This is where the design
   is confirmed or falsified.
4. §6's prose widening, its new predicate, and the six-phrase check.
5. `limitations.md`'s two corrections and one new entry.
6. Re-record `rb-extract`'s `exercise.md` against a real dispatch, per §6.
7. Comment on #4 with the measurements and the ruling: both proposed levers
   fail, the unit was the defect, and the fix is not downstream of #3.

## 10. Verification

The three gates: `make test`, `make check`, `uv run rubrica check-skills`.

Then the claim itself, on the real corpus:

```sh
rubrica survey \
  --corpus <tau2-bench>/src/tau2 \
  --corpus <tau2-bench>/data/tau2/trajectories \
  --runs-dir /tmp/probe --target-name tau2 --target-interface python \
  --objective breadth
rubrica validate --run "$RUN" --stage survey
```

Asserted rather than eyeballed:

- 443 candidates, unchanged; kinds `{source_code: 224, trace: 200, design_doc: 19}`
- catalogue ~466KB, under `DEFAULT_MAX_CATALOGUE_BYTES`; count under `max_candidates`
- all 200 trajectory digests fire exactly `[element_counts, request_text, names]`
- `plan_slices` yields ~7 slices, none over `DEFAULT_SLICE_BYTES`
- 68 distinct `names` signatures across the 200 — the discrimination §1.2 measured
- the dict-shaped fixture traces digest byte-identically to before
