"""Report generation — rich terminal tables + CSV/XLSX export."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field

from rich.console import Console
from rich.table import Table

console = Console()


@dataclass
class ChannelRow:
    """Unified channel row for reporting."""

    handle: str
    platform: str = ""
    title: str = ""
    subscribers: int = 0
    reach: int = 0
    avg_views: float = 0.0
    er_pct: float | None = None
    er_tier: str | None = None
    price: float | None = None
    cpm: float | None = None
    frequency: float | None = None
    fraud_flags: list[str] = field(default_factory=list)


def select_rows(
    rows: list[ChannelRow],
    sort_by: str | None = None,
    max_cpm: float | None = None,
    min_er: float | None = None,
) -> list[ChannelRow]:
    """Apply report filters and sorting without mutating the input list."""
    filtered = list(rows)

    if max_cpm is not None:
        filtered = [r for r in filtered if r.cpm is not None and r.cpm <= max_cpm]
    if min_er is not None:
        filtered = [r for r in filtered if r.er_pct is not None and r.er_pct >= min_er]

    if sort_by:
        if sort_by not in ChannelRow.__dataclass_fields__:
            raise ValueError(f"Unknown sort field: {sort_by}")
        reverse = sort_by not in ("cpm",)  # Lower CPM is better
        present = [r for r in filtered if getattr(r, sort_by) is not None]
        missing = [r for r in filtered if getattr(r, sort_by) is None]
        present.sort(key=lambda r: getattr(r, sort_by), reverse=reverse)
        filtered = present + missing

    return filtered


def render_table(
    rows: list[ChannelRow],
    sort_by: str | None = None,
    max_cpm: float | None = None,
    min_er: float | None = None,
) -> None:
    """Render a rich table of channel analytics."""
    filtered = select_rows(rows, sort_by, max_cpm, min_er)

    table = Table(title="KOL Channel Report", show_lines=True)
    table.add_column("Handle", min_width=16)
    table.add_column("Platform", width=5)
    table.add_column("Subs", justify="right")
    table.add_column("Reach", justify="right")
    table.add_column("Avg Views", justify="right")
    table.add_column("ER%", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("CPM", justify="right")
    table.add_column("Posts/wk", justify="right")
    table.add_column("Flags")

    for r in filtered:
        flags_str = ", ".join(r.fraud_flags) if r.fraud_flags else ""
        flag_style = "red" if r.fraud_flags else ""

        table.add_row(
            r.handle,
            r.platform,
            f"{r.subscribers:,}" if r.subscribers else "—",
            f"{r.reach:,}" if r.reach else "—",
            f"{r.avg_views:,.0f}" if r.avg_views else "—",
            f"{r.er_pct:.1f}" if r.er_pct is not None else "—",
            f"${r.price:,.0f}" if r.price is not None else "—",
            f"${r.cpm:,.1f}" if r.cpm is not None else "—",
            f"{r.frequency:.1f}" if r.frequency is not None else "—",
            f"[{flag_style}]{flags_str}[/{flag_style}]" if flag_style else flags_str,
        )

    console.print(table)
    console.print(f"\n[dim]{len(filtered)} channels shown[/dim]")


def export_csv(rows: list[ChannelRow], path: str) -> str:
    """Export channel rows to CSV."""
    fieldnames = [
        "handle", "platform", "title", "subscribers", "reach",
        "avg_views", "er_pct", "er_tier", "price", "cpm",
        "frequency", "fraud_flags",
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({
                "handle": r.handle,
                "platform": r.platform,
                "title": r.title,
                "subscribers": r.subscribers,
                "reach": r.reach,
                "avg_views": f"{r.avg_views:.0f}" if r.avg_views else "",
                "er_pct": f"{r.er_pct:.1f}" if r.er_pct is not None else "",
                "er_tier": r.er_tier or "",
                "price": f"{r.price:.0f}" if r.price is not None else "",
                "cpm": f"{r.cpm:.1f}" if r.cpm is not None else "",
                "frequency": f"{r.frequency:.1f}" if r.frequency is not None else "",
                "fraud_flags": "; ".join(r.fraud_flags) if r.fraud_flags else "",
            })

    return path


def export_xlsx(rows: list[ChannelRow], path: str) -> str:
    """Export channel rows to Excel."""
    import pandas as pd

    data = []
    for r in rows:
        data.append({
            "Handle": r.handle,
            "Platform": r.platform,
            "Title": r.title,
            "Subscribers": r.subscribers,
            "Reach": r.reach,
            "Avg Views": r.avg_views,
            "ER%": r.er_pct,
            "ER Tier": r.er_tier or "",
            "Price ($)": r.price,
            "CPM ($)": r.cpm,
            "Posts/week": r.frequency,
            "Fraud Flags": "; ".join(r.fraud_flags) if r.fraud_flags else "",
        })

    columns = ["Handle", "Platform", "Title", "Subscribers", "Reach", "Avg Views", "ER%", "ER Tier", "Price ($)", "CPM ($)", "Posts/week", "Fraud Flags"]
    df = pd.DataFrame(data, columns=columns)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
        for row in writer.book.active.iter_rows():
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
    return path
