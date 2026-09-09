---
name: Bug report
about: Report something that isn't working as expected
title: "[bug] "
labels: bug
assignees: ""
---

**Describe the bug**
A clear and concise description of what the bug is.

**To reproduce**
1. The `rubrica` subcommand you ran, with its flags
2. The stage and run directory it was pointed at, if relevant
3. What it printed

**Expected behavior**
What you expected to happen.

**Exit code and output**
Rubrica's exit codes are contractual: `0` clean, `1` findings (one per line on
stdout), `2` a usage error or an unreadable run. Please include the exit code —
`echo $?` — and the output verbatim.

```
<paste output here>
```

**Environment**
- OS:
- Python version (`uv run python --version`):
- rubrica version or commit:
- Installed how (`uv sync`, `pip install`, from a checkout):

**Additional context**
Anything else that helps diagnose the issue. If a run directory is involved,
please say which stage it had reached — but do not paste artifacts that contain
anything you would not publish.
