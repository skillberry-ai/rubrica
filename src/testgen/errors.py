"""Errors that change a CLI exit code.

UsageError lives here rather than in intake.py because it is not about intake.
It means "the harness was handed something it cannot act on", which cli.py maps
to exit 2 -- and smoke needs to raise it for a malformed agent roster without
importing the intake stage to get at the exception type.
"""

from __future__ import annotations


class UsageError(ValueError):
    """Raised when a component was called with arguments it cannot act on.

    Named rather than a bare ValueError so cli.py can map *these* to exit 2
    without also mapping every ValueError raised anywhere downstream. A coverage
    document with a non-numeric `pct` is a repairable score-stage defect, and
    reporting it as a misconfigured harness told the orchestrator to halt when
    one repair would have cleared it.
    """
