from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from newsring.config import SourceSpec
from newsring.sources import parse_feed, parse_hf_daily_papers, parse_hn_algolia
from newsring.text import canonical_url, html_to_text, trim

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>t</title>
<item><title>New &amp; shiny</title><link>https://ex.com/post?utm_source=rss</link>
<pubDate>Mon, 12 Oct 2026 16:00:00 +0000</pubDate>
<description>&lt;p&gt;Hello &lt;b&gt;world&lt;/b&gt;&lt;/p&gt;</description>
<comments>https://news.ycombinator.com/item?id=1</comments></item>
<item><title>Ancient</title><link>https://ex.com/old</link>
<pubDate>Fri, 15 Dec 1950 00:00:00 +0000</pubDate></item>
<item><title></title><link>https://ex.com/untitled</link></item>
</channel></rss>"""


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.Example.com/a/?utm_source=x&id=3#frag", "example.com/a?id=3"),
        ("http://example.com/a", "example.com/a"),
        ("https://arxiv.org/abs/2610.01234v2", "arxiv:2610.01234"),
        ("https://arxiv.org/pdf/2610.01234.pdf", "arxiv:2610.01234"),
        ("https://huggingface.co/papers/2610.01234", "arxiv:2610.01234"),
    ],
)
def test_canonical_url(url: str, expected: str) -> None:
    assert canonical_url(url) == expected


def test_html_to_text_strips_tags_and_scripts() -> None:
    raw = "<p>One &amp; two</p><script>evil()</script><ul><li>a</li><li>b</li></ul>"
    assert html_to_text(raw) == "One & two\n\na\n\nb"


def test_trim_cuts_at_word_boundary() -> None:
    assert trim("alpha beta gamma", 12) == "alpha beta…"
    assert trim("short", 12) == "short"


def test_parse_feed() -> None:
    items = parse_feed(RSS, SourceSpec(name="F", url="https://ex.com/rss", tags=["t"]))
    assert [i.title for i in items] == ["New & shiny", "Ancient"]
    first = items[0]
    assert first.key == "ex.com/post"
    assert first.summary == "Hello world"
    assert first.discussion_url == "https://news.ycombinator.com/item?id=1"
    assert first.published == datetime(2026, 10, 12, 16, tzinfo=UTC)
    assert first.tags == ["t"]
    # A pre-1970 date must parse on Windows too.
    assert items[1].published is not None and items[1].published.year == 1950


def test_parse_feed_rejects_non_feed() -> None:
    with pytest.raises(ValueError, match="not a feed"):
        parse_feed(b"<html><body>nope</body></html>", SourceSpec(name="F", url="https://x"))


def test_parse_hn_algolia_falls_back_to_thread_url() -> None:
    body = json.dumps(
        {
            "hits": [
                {
                    "objectID": "7",
                    "title": "Ask HN: x",
                    "url": None,
                    "points": 120,
                    "num_comments": 40,
                    "created_at": "2026-10-13T01:00:00Z",
                },
            ]
        }
    ).encode()
    (item,) = parse_hn_algolia(body, SourceSpec(name="HN", kind="hn_algolia", url="https://x"))
    assert item.url == item.discussion_url == "https://news.ycombinator.com/item?id=7"
    assert item.score == 120 and item.comments == 40


def test_parse_hf_daily_papers_keys_by_arxiv_id() -> None:
    body = json.dumps(
        [
            {
                "paper": {
                    "id": "2610.00001",
                    "title": "P",
                    "summary": "S",
                    "upvotes": 12,
                    "submittedOnDailyAt": "2026-10-13T00:00:00.000Z",
                },
                "numComments": 2,
            }
        ]
    ).encode()
    (item,) = parse_hf_daily_papers(
        body, SourceSpec(name="HF", kind="hf_daily_papers", url="https://x")
    )
    assert item.key == "arxiv:2610.00001"
    assert item.score == 12
