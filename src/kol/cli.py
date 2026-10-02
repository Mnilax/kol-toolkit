"""KOL Toolkit CLI — Typer-based interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

app = typer.Typer(
    name="kol",
    help="KOL/Influencer analytics toolkit — scrape, enrich, dedup, report.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def scrape(
    channels_file: str = typer.Argument(..., help="Path to channels.txt (one handle per line)"),
    platform: str = typer.Option("telegram", "--platform", "-p", help="Platform: telegram or youtube"),
    resume: bool = typer.Option(False, "--resume", help="Resume from checkpoint"),
    output: str = typer.Option("scraped.json", "--output", "-o", help="Output JSON path"),
    limit: int = typer.Option(50, "--limit", "-n", help="Posts/videos to fetch per channel"),
) -> None:
    """Scrape channels from a text file."""
    import asyncio

    if limit <= 0:
        raise typer.BadParameter("must be positive", param_hint="--limit")

    path = Path(channels_file)
    if not path.exists():
        console.print(f"[red]File not found: {channels_file}[/red]")
        raise typer.Exit(1)

    handles = [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip() and not line.lstrip().startswith("#")]
    console.print(f"Found {len(handles)} channels in {channels_file}")

    resume_file = f".checkpoint_{platform}.json" if resume else None

    if platform == "telegram":
        from kol.sources.telegram import scrape_channels
        results = asyncio.run(scrape_channels(handles, posts_limit=limit, resume_file=resume_file))
    elif platform == "youtube":
        from kol.sources.youtube import scrape_channels
        results = asyncio.run(scrape_channels(handles, video_count=limit, resume_file=resume_file))
    else:
        console.print(f"[red]Unknown platform: {platform}. Use 'telegram' or 'youtube'.[/red]")
        raise typer.Exit(1)

    # Save results
    from dataclasses import asdict
    data = [asdict(r) for r in results]
    Path(output).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(f"[green]✓ Scraped {len(results)} channels -> {output}[/green]")

    errors = [r for r in results if hasattr(r, "error") and r.error]
    if errors:
        console.print(f"[yellow]⚠ {len(errors)} channels had errors[/yellow]")


@app.command()
def enrich(
    data_file: str = typer.Argument(..., help="Scraped data JSON"),
    prices_file: Optional[str] = typer.Option(None, "--prices", help="Prices file (handle<TAB>price per line)"),
    output: str = typer.Option("enriched.json", "--output", "-o"),
) -> None:
    """Enrich scraped data with CPM, ER tier, and fraud flags."""
    from kol.fraud import detect_fraud
    from kol.metrics import cpm, engagement_rate_check, parse_price

    data = json.loads(Path(data_file).read_text(encoding="utf-8-sig"))

    # Load prices if provided
    prices: dict[str, str] = {}
    if prices_file and Path(prices_file).exists():
        for line in Path(prices_file).read_text(encoding="utf-8-sig").splitlines():
            if "\t" in line:
                handle, price = line.split("\t", 1)
                prices[handle.strip().lower().lstrip("@")] = price.strip()

    enriched = []
    for ch in data:
        handle_key = ch.get("handle", "").lower().lstrip("@")
        price_raw = prices.get(handle_key, ch.get("price_raw"))
        price = parse_price(price_raw)
        reach = ch.get("reach")
        if reach is None:
            reach = ch.get("total_views_last_n", 0)
        subs = ch.get("subscribers", 0)
        er_pct = ch.get("er_pct")

        ch["price"] = price
        ch["cpm"] = cpm(price, reach) if reach else None
        ch["er_tier"] = engagement_rate_check(er_pct)

        fraud_flags = detect_fraud(
            subscribers=subs,
            reach=reach,
            er_pct=er_pct,
            views_avg=ch.get("avg_views"),
            subscriber_growth_30d_pct=ch.get("growth_30d_pct"),
        )
        ch["fraud_flags"] = [f.message for f in fraud_flags]
        enriched.append(ch)

    Path(output).write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(f"[green]✓ Enriched {len(enriched)} channels -> {output}[/green]")


@app.command()
def dedup(
    data_file: str = typer.Argument(..., help="Data JSON with potential duplicates"),
    output: str = typer.Option("deduped.json", "--output", "-o"),
) -> None:
    """Deduplicate channels (case-insensitive, keep min non-zero price)."""
    from kol.dedup import ChannelEntry, dedup_channels

    data = json.loads(Path(data_file).read_text(encoding="utf-8-sig"))

    entries = [
        ChannelEntry(
            handle=ch.get("handle", ""),
            price_raw=ch.get("price_raw") or ch.get("price"),
            data=ch,
        )
        for ch in data
    ]

    deduped = dedup_channels(entries)
    result = [e.data for e in deduped]

    removed = len(data) - len(result)
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(f"[green]✓ Deduped: {len(data)} -> {len(result)} ({removed} duplicates removed)[/green]")


@app.command()
def report(
    data_file: str = typer.Argument(..., help="Enriched data JSON"),
    csv_out: Optional[str] = typer.Option(None, "--csv", help="Export to CSV"),
    xlsx_out: Optional[str] = typer.Option(None, "--xlsx", help="Export to XLSX"),
    sort: str = typer.Option("cpm", "--sort", "-s", help="Sort by field"),
    max_cpm: Optional[float] = typer.Option(None, "--max-cpm", help="Filter: max CPM"),
    min_er: Optional[float] = typer.Option(None, "--min-er", help="Filter: min ER%"),
) -> None:
    """Display a rich table and optionally export to CSV/XLSX."""
    from kol.report import ChannelRow, export_csv, export_xlsx, render_table, select_rows

    data = json.loads(Path(data_file).read_text(encoding="utf-8-sig"))

    rows = []
    for ch in data:
        rows.append(ChannelRow(
            handle=ch.get("handle", ""),
            platform=ch.get("platform", "tg"),
            title=ch.get("title", ""),
            subscribers=ch.get("subscribers", 0),
            reach=ch.get("reach", ch.get("total_views_last_n", 0)),
            avg_views=ch.get("avg_views", 0),
            er_pct=ch.get("er_pct"),
            er_tier=ch.get("er_tier"),
            price=ch.get("price"),
            cpm=ch.get("cpm"),
            frequency=ch.get("frequency", ch.get("frequency_per_week")),
            fraud_flags=ch.get("fraud_flags", []),
        ))

    try:
        rows = select_rows(rows, sort_by=sort, max_cpm=max_cpm, min_er=min_er)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--sort") from exc
    render_table(rows)

    if csv_out:
        export_csv(rows, csv_out)
        console.print(f"[green]✓ CSV exported: {csv_out}[/green]")
    if xlsx_out:
        export_xlsx(rows, xlsx_out)
        console.print(f"[green]✓ XLSX exported: {xlsx_out}[/green]")


if __name__ == "__main__":
    app()
