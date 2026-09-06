"""Entry point wiring the demo package together."""

from demo.orders import SpecialOrder
from demo.receipts import print_receipt, render_receipt
from demo.repository import OrderRepository


def main() -> None:
    repo = OrderRepository()
    repo.add('A1', {'total': 500})
    print_receipt(repo, 'A1')
    render_receipt({'total': 999})

    special = SpecialOrder()
    special.add('B2', {'total': 700})
    special.apply_discount('B2', 10)


if __name__ == '__main__':
    main()
