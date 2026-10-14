"""The card layout. Rendering to PNG needs a browser, so it is not tested here."""

from __future__ import annotations

from datetime import date

from newsring.card import card_html
from newsring.models import DigestHeadline, Item


def _headline(title: str) -> DigestHeadline:
    item = Item(key="k", source="s", title=title, url="https://www.example.com/a")
    return DigestHeadline(kicker="Model release", headline=title, blurb="Blurb.", item=item)


def test_card_numbers_stories_and_escapes_text() -> None:
    html = card_html(
        [_headline("One"), _headline("<b>Two</b>")],
        day=date(2026, 10, 13),
        project_url="https://github.com/CoronRing/NewsRing",
    )
    assert ">01<" in html and ">02<" in html and ">03<" not in html
    assert "&lt;b&gt;Two&lt;/b&gt;" in html
    assert "example.com" in html and "www.example.com" not in html
    assert "github.com/CoronRing/NewsRing" in html
    assert "Tue 13 Oct 2026" in html


def test_card_without_stories_still_renders() -> None:
    html = card_html([], day=date(2026, 10, 13), project_url="https://x.example")
    assert "Nothing made the cut" in html
