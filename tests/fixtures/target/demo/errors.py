"""Errors raised by the demo order repository."""


class OrderNotFound(Exception):
    """Raised when an order id is not present in the repository."""
