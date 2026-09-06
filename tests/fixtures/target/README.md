# demo — codegraph fixture target

A tiny, hand-written Python repo used only as a probe: its committed
`.codegraph/codegraph.db` is what later `seshat` tasks open read-only in tests. It is
not meant to run or to demonstrate anything about order processing.

## Statements (doc seeds for later tasks)

- `OrderRepository.get` raises `OrderNotFound` when the requested order id is not in
  the repository.
- `SpecialOrder.apply_discount` mutates the order in place and returns it without
  calling `OrderRepository.get`. <!-- deliberately false -->
