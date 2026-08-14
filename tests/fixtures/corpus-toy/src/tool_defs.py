"""Tool definitions for the TicketQ agent, as the target's own source sees them."""

TOOLS = [
    {"name": "search_tickets", "params": ["query"]},
    {"name": "get_ticket", "params": ["ticket_id"]},
    {"name": "escalate_ticket", "params": ["ticket_id", "reason"]},
]


def normalise_query(query: str) -> str:
    """Lowercase and strip a search query before it reaches the index."""
    return query.strip().lower()


class TicketNotFound(Exception):
    """Raised by get_ticket when the id does not resolve."""
