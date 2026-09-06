"""In-memory order repository."""

from demo.errors import OrderNotFound


class OrderRepository:
    """Stores orders by id and looks them up on request."""

    def __init__(self) -> None:
        self._orders: dict[str, dict] = {}

    def add(self, order_id: str, payload: dict) -> None:
        self._orders[order_id] = payload

    def get(self, order_id: str) -> dict:
        """Return the order for `order_id`, raising `OrderNotFound` if absent."""
        return self._get_or_raise(order_id)

    def _get_or_raise(self, order_id: str) -> dict:
        if order_id not in self._orders:
            raise OrderNotFound(order_id)
        return self._orders[order_id]
