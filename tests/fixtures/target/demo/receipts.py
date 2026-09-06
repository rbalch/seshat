"""Receipt formatting: a stdlib call (`json.dumps`) and two decorated functions."""

import json
from functools import lru_cache

from demo.decorators import logged
from demo.repository import OrderRepository


@lru_cache
def format_currency(cents: int) -> str:
    return f'${cents / 100:.2f}'


@logged
def render_receipt(order: dict) -> str:
    """Called from both `receipts.py` and `main.py`, so inbound_calls >= 2."""
    return json.dumps(order)


def print_receipt(repo: OrderRepository, order_id: str) -> str:
    order = repo.get(order_id)
    return render_receipt(order)
