"""seshat console script.

No subcommands yet (T-11 fills them in). `main` prints usage and exits 0.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog='seshat',
        description='seshat: a ledger of verified claims about a codebase.',
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
