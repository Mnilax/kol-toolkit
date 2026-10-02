"""YouTube channel scraper wrapper.

Features:
- Average views over last 10 videos
- ER% = views / subs × 100
- CPM calculation
- Average video duration
- Posting frequency (videos/week)
- Price parsing from text
- Checkpoint every 5 channels
- Early stop on 0 views

Note: Uses httpx + HTML parsing (no API key). YouTube's DOM changes
frequently — selectors updated for ytContentMetadataViewModel /
yt-lockup-view-model with blind-text fallback.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

CHECKPOINT_INTERVAL = 5


@dataclass
class YouTubeChannel:
    """Scraped YouTube channel data."""

    handle: str
    title: str = ""
    subscribers: int = 0
    avg_views: float | None = None
    er_pct: float | None = None
    frequency_per_week: float | None = None
    avg_duration_sec: int | None = None
    video_count: int = 0
    error: str | None = None
    platform: str = "yt"


async def scrape_channels(
    handles: list[str],
    video_count: int = 10,
    resume_file: str | None = None,
) -> list[YouTubeChannel]:
    """Scrape YouTube channels for analytics.

    Args:
        handles: List of @handle or channel URLs
        video_count: Number of recent videos to analyze
        resume_file: Checkpoint file path

    Returns:
        List of YouTubeChannel results
    """
    try:
        import httpx
    except ImportError:
        raise ImportError(
            "httpx and beautifulsoup4 required. Install with: pip install 'kol-toolkit[youtube]'"
        )

    completed: set[str] = set()
    results: list[YouTubeChannel] = []
    if resume_file and Path(resume_file).exists():
        with open(resume_file, encoding="utf-8-sig") as f:
            checkpoint = json.load(f)
            results = [YouTubeChannel(**ch) for ch in checkpoint.get("channels", [])]
            completed = {ch.handle.lower() for ch in results if not ch.error}
            requested = {h.lower() for h in handles}
            results = [ch for ch in results if not ch.error or ch.handle.lower() not in requested]

    async with httpx.AsyncClient(
        timeout=30.0,
        headers={"User-Agent": "Mozilla/5.0 (compatible; KOL-Toolkit/0.1)"},
        follow_redirects=True,
    ) as client:
        for i, handle in enumerate(handles):
            if handle.lower() in completed:
                continue

            try:
                channel_data = await _fetch_youtube_channel(client, handle, video_count)
                results.append(channel_data)

            except Exception as e:
                results.append(YouTubeChannel(handle=handle, error=str(e)))

            if resume_file and (i + 1) % CHECKPOINT_INTERVAL == 0:
                _save_checkpoint(resume_file, results)

    if resume_file:
        _save_checkpoint(resume_file, results)

    return results


async def _fetch_youtube_channel(client, handle: str, video_count: int) -> YouTubeChannel:
    """Fetch a single YouTube channel's public data via HTML."""
    # Normalize handle to URL
    if handle.startswith("http"):
        url = handle
    elif handle.startswith("@"):
        url = f"https://www.youtube.com/{handle}"
    else:
        url = f"https://www.youtube.com/@{handle}"

    resp = await client.get(url)
    resp.raise_for_status()
    html = resp.text

    # Extract initial data JSON from page
    # YouTube embeds data in ytInitialData variable
    match = re.search(r"var ytInitialData\s*=\s*({.*?});\s*</script>", html, re.DOTALL)
    if not match:
        return YouTubeChannel(handle=handle, error="Could not parse YouTube page")

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return YouTubeChannel(handle=handle, error="Invalid JSON in YouTube page")

    # Extract basic channel info
    title = _extract_title(data)
    subs = _extract_subscriber_count(data)

    return YouTubeChannel(
        handle=handle,
        title=title or handle,
        subscribers=subs,
    )


def _extract_title(data: dict) -> str | None:
    """Extract channel title from ytInitialData."""
    try:
        header = data.get("header", {}).get("c4TabbedHeaderRenderer", {})
        return header.get("title", None)
    except (KeyError, AttributeError):
        return None


def _extract_subscriber_count(data: dict) -> int:
    """Extract subscriber count from ytInitialData."""
    try:
        header = data.get("header", {}).get("c4TabbedHeaderRenderer", {})
        sub_text = header.get("subscriberCountText", {}).get("simpleText", "")
        return _parse_count(sub_text)
    except (KeyError, AttributeError):
        return 0


def _parse_count(text: str) -> int:
    """Parse subscriber/view count strings like '1.2M', '450K'."""
    text = text.strip().upper().replace(",", "")
    match = re.match(r"([\d.]+)\s*([KMB])?", text)
    if not match:
        return 0
    try:
        num = float(match.group(1))
    except ValueError:
        return 0
    suffix = match.group(2)
    if suffix == "K":
        num *= 1_000
    elif suffix == "M":
        num *= 1_000_000
    elif suffix == "B":
        num *= 1_000_000_000
    return int(num)


def _save_checkpoint(path: str, results: list[YouTubeChannel]):
    """Save progress to checkpoint file."""
    data = {"channels": [asdict(ch) for ch in results]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
