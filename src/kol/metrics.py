"""Pure functions for KOL metrics calculation.

All functions are stateless and I/O-free — easy to test.
"""

from __future__ import annotations

import re
import math


def parse_price(raw: str | int | float | None) -> float | None:
    """Parse a price from various text formats.

    Supported formats:
        450$ | $450 | 450 USD | €50 | 80$ | 1,200$ | 1.5k$
        Markdown links like [450$](url) are stripped.
        Returns None if unparseable.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if not isinstance(raw, bool) and math.isfinite(raw) and raw > 0 else None

    s = str(raw).strip()
    if not s:
        return None

    # Strip markdown links: [text](url) -> text
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)

    # Remove currency symbols and words
    s = s.replace(",", "")
    s = re.sub(r"[$€£₽¥]", "", s)
    s = re.sub(r"\s*(USD|EUR|RUB|USDT|usd|eur)\s*", "", s, flags=re.IGNORECASE)
    s = s.strip()

    if not s:
        return None

    # Handle "1.5k" notation
    match = re.match(r"^(\d+(?:\.\d+)?)\s*[kK\u043a\u041a]$", s)
    if match:
        val = float(match.group(1)) * 1000
        return val if math.isfinite(val) and val > 0 else None

    try:
        val = float(s)
        return val if math.isfinite(val) and val > 0 else None
    except ValueError:
        return None


def cpm(price: float | None, reach: int | None) -> float | None:
    """Calculate CPM (cost per mille).

    Formula: 1000 * price / reach
    Returns None if inputs are invalid.
    """
    if price is None or reach is None or not math.isfinite(price) or not math.isfinite(reach) or reach <= 0 or price <= 0:
        return None
    return 1000.0 * price / reach


def engagement_rate_check(er_pct: float | None) -> str | None:
    """Classify engagement rate tier.

    ER% is taken as-is from TGStat/analytics — NOT computed.
    Returns a tier label for context.
    """
    if er_pct is None or not math.isfinite(er_pct) or er_pct < 0:
        return None
    if er_pct >= 10:
        return "very-high"
    if er_pct >= 5:
        return "high"
    if er_pct >= 2:
        return "average"
    if er_pct >= 0.5:
        return "low"
    return "very-low"


def views_per_post(total_views: int | None, post_count: int | None) -> float | None:
    """Average views per post."""
    if total_views is None or post_count is None or not math.isfinite(total_views) or total_views < 0 or post_count <= 0:
        return None
    return total_views / post_count


def posting_frequency(post_count: int | None, days: int = 30) -> float | None:
    """Posts per week over the given period."""
    if post_count is None or post_count <= 0 or days <= 0:
        return None
    return (post_count / days) * 7
