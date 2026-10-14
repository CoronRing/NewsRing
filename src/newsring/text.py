"""Small text helpers: HTML to plain text, URL canonicalization, trimming."""

from __future__ import annotations

import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TAG = re.compile(r"<[^>]+>")
_BLOCK = re.compile(r"</?(p|div|br|li|ul|ol|h[1-6]|tr|blockquote|pre)[^>]*>", re.IGNORECASE)
_DROP = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_SPACES = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES = re.compile(r"\n\s*\n+")

_TRACKING_PARAMS = {"ref", "ref_src", "source", "fbclid", "gclid", "mc_cid", "mc_eid"}
_ARXIV_ID = re.compile(
    r"^(?:https?://)?(?:www\.)?(?:arxiv\.org/(?:abs|pdf|html)|huggingface\.co/papers)/"
    r"(\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?/?$",
    re.IGNORECASE,
)


def html_to_text(raw: str) -> str:
    """Convert an HTML fragment to readable plain text.

    Good enough for feed summaries and release notes. Full article pages go
    through trafilatura instead (see `newsring.enrich`).

    Args:
        raw: HTML, or plain text, which passes through unchanged apart from
            whitespace.

    Returns:
        Plain text with paragraphs separated by blank lines.
    """
    text = _DROP.sub(" ", raw)
    text = _BLOCK.sub("\n", text)
    text = _TAG.sub(" ", text)
    text = html.unescape(text)
    text = _SPACES.sub(" ", text)
    lines = [line.strip() for line in text.split("\n")]
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def trim(text: str, limit: int) -> str:
    """Cut text to at most `limit` characters, at a word boundary, with an ellipsis."""
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,.;:") + "…"


def canonical_url(url: str) -> str:
    """Reduce a URL to a stable identity for deduplication.

    The same paper on arXiv and on Hugging Face Papers collapses to
    ``arxiv:<id>``. Otherwise the scheme and ``www.`` are dropped, the host is
    lower-cased, tracking parameters and the fragment are removed, and a
    trailing slash is stripped.

    Args:
        url: Any absolute URL.

    Returns:
        A string that is equal for two URLs pointing at the same story.
    """
    url = url.strip()
    match = _ARXIV_ID.match(url)
    if match:
        return f"arxiv:{match.group(1)}"
    parts = urlsplit(url)
    host = parts.netloc.lower().removeprefix("www.")
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_PARAMS
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("", host, path, urlencode(query), "")).lstrip("/")
