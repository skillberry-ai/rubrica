# ticketq — operator notes

`ticketq` fronts two support queues, `billing` and `shipping`. Support
engineers use it to find the ticket they need to act on and to explain why a
ticket is stuck.

## Invariants the store maintains

- `comment_count` on a ticket is always the number of comment records
  attached to it. The field is recomputed on read, so a stored value that
  disagrees is overwritten.
- `ticket_id` is unique across every queue.

## Error behaviour

`get_ticket` with an id no ticket has is an **error**, not an empty result.
Callers must handle it as a not-found condition rather than treating the
absence of fields as a ticket in an unknown state.

## What engineers actually ask

Two things, in practice. "Which ticket in this queue still needs me?" — one
lookup. And "why is this one stuck?" — find the ticket, then read its
comments, which is where the blocker is named.
