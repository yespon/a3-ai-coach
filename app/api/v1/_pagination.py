from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")

DEFAULT_PAGE_SIZE = 30
MAX_PAGE_SIZE = 100


def clamp_page_size(
    value: int | None,
    *,
    default: int = DEFAULT_PAGE_SIZE,
    maximum: int = MAX_PAGE_SIZE,
) -> int:
    """Return *default* if value is None or <1, otherwise min(value, maximum)."""
    if value is None or value < 1:
        return default
    return min(value, maximum)


def clamp_page(value: int | None) -> int:
    """Return 1 if value is None or <1, otherwise the value."""
    if value is None or value < 1:
        return 1
    return value


@dataclass
class Page(Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
