"""A decorator defined in the repo (as opposed to `functools.lru_cache`)."""

from collections.abc import Callable


def logged(fn: Callable) -> Callable:
    """Wrap `fn` so calls to it are traceable. Trivial on purpose: a probe, not a demo."""

    def wrapper(*args: object, **kwargs: object) -> object:
        return fn(*args, **kwargs)

    return wrapper
