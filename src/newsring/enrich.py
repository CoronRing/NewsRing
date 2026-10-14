"""Fetch the full text of picked stories so the writer has more than a headline.

Runs after selection, so it costs one request per picked story, not one per
candidate. Items whose feed already carried a long body are skipped. A failed
fetch leaves the item as it was; the writer is told to write less when the
material is thin.
"""

from __future__ import annotations

import asyncio

import httpx
import trafilatura

from newsring.models import Item
from newsring.sources import USER_AGENT, get_bytes
from newsring.text import trim

#: An item with at least this much text already is not fetched again.
ENOUGH_TEXT = 1500

#: Hosts whose pages are JavaScript shells or need login, so a fetch returns
#: nothing useful and only costs time.
SKIP_HOSTS = ("x.com", "twitter.com", "linkedin.com", "youtube.com", "youtu.be")


def _needs_fetch(item: Item) -> bool:
    if len(item.content) >= ENOUGH_TEXT:
        return False
    host = httpx.URL(item.url).host.removeprefix("www.")
    return not any(host == h or host.endswith("." + h) for h in SKIP_HOSTS)


def extract_text(html: str, url: str) -> str:
    """Pull the main article text out of a page.

    Args:
        html: The page source.
        url: The page URL, which helps trafilatura with relative metadata.

    Returns:
        Plain text, or an empty string when nothing article-like was found.
    """
    text = trafilatura.extract(html, url=url, include_comments=False, include_tables=False)
    return text or ""


async def enrich_items(
    items: list[Item], *, max_chars: int, timeout: float, concurrency: int
) -> int:
    """Fill `Item.content` in place for items that lack it.

    Args:
        items: The picked items.
        max_chars: Cap on stored text per item.
        timeout: Per-request timeout in seconds.
        concurrency: Most requests in flight at once.

    Returns:
        How many items gained text.
    """
    targets = [i for i in items if _needs_fetch(i)]
    if not targets:
        return 0
    limit = asyncio.Semaphore(concurrency)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}

    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:

        async def one(item: Item) -> bool:
            try:
                async with limit:
                    body = await get_bytes(client, item.url)
                if body.lstrip()[:5] == b"%PDF-":
                    return False
                # trafilatura is synchronous and CPU-bound.
                page = body.decode("utf-8", errors="replace")
                text = await asyncio.to_thread(extract_text, page, item.url)
            except Exception:  # noqa: BLE001 - enrichment is best effort
                return False
            if len(text) <= len(item.content):
                return False
            item.content = trim(text, max_chars)
            return True

        results = await asyncio.gather(*(one(i) for i in targets))
    return sum(results)
