"""A specialised order repository, for the `extends` edge in the fixture graph."""

from demo.repository import OrderRepository


class SpecialOrder(OrderRepository):
    """An `OrderRepository` that also supports applying a discount."""

    def apply_discount(self, order_id: str, percent: int) -> dict:
        order = self.get(order_id)
        order['discount'] = percent
        return order
