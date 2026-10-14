"""Read each configured source into normalized `Item`s.

One parser per `SourceKind`. Every parser takes the raw response body and the
source's spec and returns items; fetching, errors and concurrency are handled
once in `fetch_all`. A source that fails is reported, never fatal.

The arXiv export API and GitHub ``releases.atom`` are plain Atom, so they use
the ``feed`` kind.
"""

from __future__ import annotations

import asyncio
import json
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import feedparser
import httpx

from newsring import __version__
from newsring.config import SourceKind, SourceSpec
from newsring.models import Item, SourceReport
from newsring.text import canonical_url, html_to_text, trim

USER_AGENT = f"NewsRing/{__version__} (+https://github.com/CoronRing/NewsRing)"
SUMMARY_CHARS = 1200
CONTENT_CHARS = 8000

Parser = Callable[[bytes, SourceSpec], list[Item]]


def _parse_time(value: Any) -> datetime | None:
    """Parse an ISO 8601 string or a feedparser `struct_time` into aware UTC."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    # feedparser normalizes every date format it understands to a UTC struct_time.
    # Built from fields rather than a timestamp: Windows rejects pre-1970 timestamps.
    try:
        return datetime(
            value.tm_year,
            value.tm_mon,
            value.tm_mday,
            value.tm_hour,
            value.tm_min,
            value.tm_sec,
            tzinfo=UTC,
        )
    except (AttributeError, TypeError, ValueError):
        return None


def _make_item(spec: SourceSpec, **fields: Any) -> Item:
    return Item(key=canonical_url(fields["url"]), source=spec.name, tags=list(spec.tags), **fields)


def parse_feed(body: bytes, spec: SourceSpec) -> list[Item]:
    """Parse RSS or Atom, including GitHub releases and the arXiv export API."""
    parsed = feedparser.parse(body)
    if not parsed.entries and (parsed.bozo or not parsed.version):
        # An HTML page at a feed URL parses cleanly with no entries; report it
        # rather than letting a dead feed look like a quiet one.
        reason = parsed.get("bozo_exception") or "no RSS or Atom document found"
        raise ValueError(f"not a feed: {reason}")
    items: list[Item] = []
    for entry in parsed.entries:
        link = entry.get("link") or entry.get("id")
        title = html_to_text(entry.get("title", "")).strip()
        if not link or not title:
            continue
        summary = html_to_text(entry.get("summary", ""))
        content_blocks = entry.get("content") or []
        content = html_to_text(" ".join(c.get("value", "") for c in content_blocks))
        published = _parse_time(entry.get("published_parsed") or entry.get("updated_parsed"))
        comments = entry.get("comments")
        items.append(
            _make_item(
                spec,
                title=title,
                url=link,
                discussion_url=comments if comments and comments != link else None,
                published=published,
                summary=trim(summary or content, SUMMARY_CHARS),
                content=trim(content, CONTENT_CHARS) if len(content) > len(summary) else "",
            )
        )
    return items


def parse_hn_algolia(body: bytes, spec: SourceSpec) -> list[Item]:
    """Parse a Hacker News Algolia search response."""
    hits = json.loads(body).get("hits", [])
    items: list[Item] = []
    for hit in hits:
        thread = f"https://news.ycombinator.com/item?id={hit['objectID']}"
        title = hit.get("title") or hit.get("story_title")
        if not title:
            continue
        items.append(
            _make_item(
                spec,
                title=title,
                url=hit.get("url") or thread,
                discussion_url=thread,
                published=_parse_time(hit.get("created_at")),
                summary=trim(html_to_text(hit.get("story_text") or ""), SUMMARY_CHARS),
                score=float(hit.get("points") or 0),
                comments=int(hit.get("num_comments") or 0),
            )
        )
    return items


def parse_hf_daily_papers(body: bytes, spec: SourceSpec) -> list[Item]:
    """Parse the Hugging Face daily papers API. Dated by when the paper hit the list."""
    items: list[Item] = []
    for entry in json.loads(body):
        paper = entry.get("paper", {})
        paper_id = paper.get("id")
        if not paper_id:
            continue
        items.append(
            _make_item(
                spec,
                title=paper.get("title") or entry.get("title", ""),
                url=f"https://huggingface.co/papers/{paper_id}",
                published=_parse_time(paper.get("submittedOnDailyAt") or entry.get("publishedAt")),
                summary=trim(paper.get("summary", ""), SUMMARY_CHARS),
                score=float(paper.get("upvotes") or 0),
                comments=int(entry.get("numComments") or 0),
            )
        )
    return items


def parse_hf_trending_models(body: bytes, spec: SourceSpec) -> list[Item]:
    """Parse the Hugging Face models API sorted by trending score.

    Left undated on purpose: `createdAt` is when the repository was made, often
    weeks before it trends, so the time window would drop exactly the models
    that matter. The archive history stops a model being picked twice.
    """
    items: list[Item] = []
    for model in json.loads(body):
        model_id = model.get("id") or model.get("modelId")
        if not model_id:
            continue
        task = model.get("pipeline_tag") or "unknown task"
        library = model.get("library_name") or "unknown library"
        created = (model.get("createdAt") or "")[:10]
        items.append(
            _make_item(
                spec,
                title=f"{model_id} ({task})",
                url=f"https://huggingface.co/{model_id}",
                summary=(
                    f"Trending model. Task: {task}. Library: {library}. Created {created}. "
                    f"{model.get('likes', 0)} likes, {model.get('downloads', 0)} downloads."
                ),
                score=float(model.get("trendingScore") or model.get("likes") or 0),
            )
        )
    return items


PARSERS: dict[SourceKind, Parser] = {
    "feed": parse_feed,
    "hn_algolia": parse_hn_algolia,
    "hf_daily_papers": parse_hf_daily_papers,
    "hf_trending_models": parse_hf_trending_models,
}


def _urllib_get(url: str, headers: dict[str, str], timeout: float) -> bytes:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - configured URLs
        body: bytes = response.read()
    return body


async def get_bytes(client: httpx.AsyncClient, url: str) -> bytes:
    """GET a URL, retrying a 403 once through the standard library.

    Some hosts (PyTorch's, on Pantheon) refuse httpx with a 403 whatever its
    headers say, yet serve the same request from `urllib`. The block appears to
    key on the TLS handshake rather than anything an HTTP header can change.

    Args:
        client: Shared HTTP client; its headers and timeout are reused.
        url: The URL.

    Returns:
        The response body.

    Raises:
        httpx.HTTPStatusError: For any other error status.
        urllib.error.URLError: If the fallback fails too.
    """
    response = await client.get(url)
    if response.status_code == 403:
        headers = {k: v for k, v in client.headers.items() if k.lower() in ("user-agent", "accept")}
        timeout = client.timeout.read or 20.0
        return await asyncio.to_thread(_urllib_get, str(response.url), headers, timeout)
    response.raise_for_status()
    return response.content


async def fetch_source(client: httpx.AsyncClient, spec: SourceSpec) -> tuple[list[Item], str]:
    """Fetch and parse one source.

    Args:
        client: Shared HTTP client.
        spec: The source.

    Returns:
        The parsed items and an empty string, or no items and a short error.
    """
    try:
        body = await get_bytes(client, spec.url)
        items = PARSERS[spec.kind](body, spec)
    except httpx.HTTPStatusError as exc:
        return [], f"HTTP {exc.response.status_code}"
    except Exception as exc:  # noqa: BLE001 - one bad source must not stop the run
        return [], f"{type(exc).__name__}: {exc}"[:200]
    if spec.min_score is not None:
        items = [i for i in items if i.score is None or i.score >= spec.min_score]
    return items, ""


async def fetch_all(
    specs: list[SourceSpec], *, timeout: float, concurrency: int
) -> list[tuple[SourceSpec, list[Item], str]]:
    """Fetch every source concurrently.

    Args:
        specs: Sources to read.
        timeout: Per-request timeout in seconds.
        concurrency: Most requests in flight at once.

    Returns:
        One ``(spec, items, error)`` triple per source, in input order.
    """
    limit = asyncio.Semaphore(concurrency)
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}

    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:

        async def one(spec: SourceSpec) -> tuple[SourceSpec, list[Item], str]:
            async with limit:
                items, error = await fetch_source(client, spec)
            return spec, items, error

        return list(await asyncio.gather(*(one(s) for s in specs)))


def report(spec: SourceSpec, fetched: int, kept: int, error: str) -> SourceReport:
    """Build the per-source line of the run report."""
    return SourceReport(name=spec.name, ok=not error, fetched=fetched, kept=kept, error=error)
