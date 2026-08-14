# TicketQ

TicketQ is a small support-ticket queue. An agent searches tickets, reads one,
and can escalate it to a human when the customer is upset.

## Tools

- `search_tickets(query)` finds tickets by free-text query.
- `get_ticket(ticket_id)` reads one ticket in full.
- `escalate_ticket(ticket_id, reason)` flags a ticket for a human.

## Entities

- A **ticket** has an id, a subject, a body, a status, and a priority.
- A **customer** has an id, a name, and an email.
