# Design notes

Working notes from the TicketQ integration, kept separate from the top-level
README because they are process, not product.

## Open questions

Nobody has decided yet whether `escalate_ticket` should require a reason of
non-zero length, or whether an empty reason should silently fall back to
"unspecified".

## Known gaps

The capture we have access to never exercises a ticket in `closed` status, so
any scenario about reopening a closed ticket is unverifiable against evidence.

## Non-goals

This integration does not cover ticket creation. TicketQ tickets arrive only
through an external channel this agent does not have access to.
