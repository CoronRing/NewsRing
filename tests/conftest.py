"""Shared fixtures. Nothing here touches the network or a model."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from newsring.config import Config, Profile, SourceSpec
from newsring.models import Item

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


def make_item(
    url: str,
    *,
    source: str = "Feed A",
    title: str = "A story",
    hours_ago: float | None = 1,
    score: float | None = None,
    summary: str = "snippet",
) -> Item:
    from newsring.text import canonical_url

    return Item(
        key=canonical_url(url),
        source=source,
        title=title,
        url=url,
        published=NOW - timedelta(hours=hours_ago) if hours_ago is not None else None,
        score=score,
        summary=summary,
    )


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        profile=Profile(interests="LLM agents and evals"),
        sources=[
            SourceSpec(name="Feed A", url="https://a.example/feed", max_items=3),
            SourceSpec(name="Feed B", url="https://b.example/feed", max_items=3),
        ],
        base_dir=tmp_path,
    )
