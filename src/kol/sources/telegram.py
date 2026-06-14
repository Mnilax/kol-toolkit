"""Telegram channel scraper wrapper.

Enhanced version with:
- ResolveUsernameRequest instead of get_entity (fixes hangs)
- 90-second watchdog per channel
- Auto-reconnect after 2 consecutive timeouts
- --resume support via checkpoint files

Requires: telethon + API credentials in environment variables.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

CHECKPOINT_INTERVAL = 5  # Save checkpoint every N channels
WATCHDOG_TIMEOUT = 90  # Seconds before timeout per channel
MAX_CONSECUTIVE_TIMEOUTS = 2


@dataclass
class TelegramChannel:
    """Scraped Telegram channel data."""

    handle: str
    title: str = ""
    subscribers: int = 0
    total_views_last_n: int = 0
    post_count: int = 0
    avg_views: float = 0.0
    er_pct: float | None = None  # From TGStat, not computed
    error: str | None = None


def normalize_handle(raw: str) -> str:
    """Normalize a channel handle/URL to @username format."""
    s = raw.strip()
    s = re.sub(r"^https?://", "", s)
    s = re.sub(r"^(t\.me/|telegram\.me/)", "", s)
    s = s.rstrip("/")
    if not s.startswith("@") and not s.lstrip("-").isdigit():
        s = "@" + s
    return s


async def scrape_channels(
    handles: list[str],
    api_id: int | None = None,
    api_hash: str | None = None,
    session_name: str = "kol_session",
    posts_limit: int = 50,
    resume_file: str | None = None,
) -> list[TelegramChannel]:
    """Scrape multiple Telegram channels.

    Args:
        handles: List of @username or URLs
        api_id: Telegram API ID (falls back to env TG_API_ID)
        api_hash: Telegram API hash (falls back to env TG_API_HASH)
        session_name: Telethon session file name
        posts_limit: Number of recent posts to fetch
        resume_file: Path to checkpoint file for resuming

    Returns:
        List of TelegramChannel results
    """
    try:
        from telethon import TelegramClient
        from telethon.tl.functions.contacts import ResolveUsernameRequest
        from telethon.tl.functions.messages import GetHistoryRequest
    except ImportError:
        raise ImportError(
            "telethon is required for Telegram scraping. Install with: pip install 'kol-toolkit[telegram]'"
        )

    api_id = api_id or int(os.environ.get("TG_API_ID", "0"))
    api_hash = api_hash or os.environ.get("TG_API_HASH", "")

    if not api_id or not api_hash:
        raise ValueError("Telegram API credentials required. Set TG_API_ID and TG_API_HASH env vars.")

    # Load checkpoint
    completed: set[str] = set()
    results: list[TelegramChannel] = []
    if resume_file and Path(resume_file).exists():
        with open(resume_file) as f:
            checkpoint = json.load(f)
            results = [TelegramChannel(**ch) for ch in checkpoint.get("channels", [])]
            completed = {ch.handle.lower() for ch in results}

    consecutive_timeouts = 0

    async with TelegramClient(session_name, api_id, api_hash) as client:
        for i, raw_handle in enumerate(handles):
            handle = normalize_handle(raw_handle)
            if handle.lower() in completed:
                continue

            try:
                # Watchdog timeout
                channel_data = await asyncio.wait_for(
                    _fetch_channel(client, handle, posts_limit, ResolveUsernameRequest, GetHistoryRequest),
                    timeout=WATCHDOG_TIMEOUT,
                )
                results.append(channel_data)
                consecutive_timeouts = 0

            except asyncio.TimeoutError:
                results.append(TelegramChannel(handle=handle, error="timeout"))
                consecutive_timeouts += 1

                if consecutive_timeouts >= MAX_CONSECUTIVE_TIMEOUTS:
                    # Reconnect
                    await client.disconnect()
                    await asyncio.sleep(2)
                    await client.connect()
                    consecutive_timeouts = 0

            except Exception as e:
                results.append(TelegramChannel(handle=handle, error=str(e)))

            # Checkpoint
            if resume_file and (i + 1) % CHECKPOINT_INTERVAL == 0:
                _save_checkpoint(resume_file, results)

    # Final checkpoint
    if resume_file:
        _save_checkpoint(resume_file, results)

    return results


async def _fetch_channel(client, handle, posts_limit, ResolveUsernameRequest, GetHistoryRequest):
    """Fetch a single channel's data."""
    username = handle.lstrip("@")

    # Use ResolveUsernameRequest (more reliable than get_entity)
    resolved = await client(ResolveUsernameRequest(username))
    channel = resolved.peer

    history = await client(GetHistoryRequest(
        peer=channel, limit=posts_limit, offset_date=None,
        offset_id=0, max_id=0, min_id=0, add_offset=0, hash=0,
    ))

    messages = history.messages
    views_list = [m.views for m in messages if m.views is not None]
    total_views = sum(views_list)
    avg = total_views / len(views_list) if views_list else 0

    return TelegramChannel(
        handle=handle,
        title=getattr(resolved, "chats", [{}])[0].title if hasattr(resolved, "chats") and resolved.chats else username,
        subscribers=getattr(resolved.chats[0], "participants_count", 0) if hasattr(resolved, "chats") and resolved.chats else 0,
        total_views_last_n=total_views,
        post_count=len(messages),
        avg_views=avg,
    )


def _save_checkpoint(path: str, results: list[TelegramChannel]):
    """Save progress to checkpoint file."""
    data = {"channels": [asdict(ch) for ch in results]}
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
