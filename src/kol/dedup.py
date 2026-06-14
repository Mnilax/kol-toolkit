"""Deduplication logic for KOL channel lists.

Telegram usernames are case-insensitive: @CryptoAlpha == @cryptoalpha.
When duplicates are found, keep the entry with the minimum non-zero price.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kol.metrics import parse_price


@dataclass
class ChannelEntry:
    """Minimal channel entry for dedup."""

    handle: str
    price_raw: str | None = None
    data: dict = field(default_factory=dict)


def dedup_channels(entries: list[ChannelEntry]) -> list[ChannelEntry]:
    """Deduplicate channels by case-insensitive handle.

    When duplicates are found, keep the entry with the minimum non-zero price.
    If no entry has a valid price, keep the first occurrence.
    """
    seen: dict[str, ChannelEntry] = {}

    for entry in entries:
        key = entry.handle.lower().lstrip("@")

        if key not in seen:
            seen[key] = entry
            continue

        # Duplicate found — keep the one with lower non-zero price
        existing = seen[key]
        existing_price = parse_price(existing.price_raw)
        new_price = parse_price(entry.price_raw)

        if existing_price is None and new_price is not None:
            seen[key] = entry
        elif existing_price is not None and new_price is not None:
            if new_price < existing_price:
                seen[key] = entry

    return list(seen.values())
