"""Candidate building, history, selection validation, assembly and rendering."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from newsring.collect import WINDOW_OVERLAP, build_candidates, window_start
from newsring.config import Config
from newsring.deliver import build_site, write_archive
from newsring.history import History, load_history
from newsring.models import (
    DigestOutput,
    Pick,
    QuickHitLine,
    RunStats,
    SelectionOutput,
    WrittenStory,
)
from newsring.pipeline import assemble, validate_selection
from newsring.render import to_html, to_markdown
from tests.conftest import NOW, make_item


def test_window_start() -> None:
    empty = History()
    assert window_start(NOW, empty, lookback_hours=24, max_lookback_hours=72) == NOW - timedelta(
        hours=24
    )
    recent = History(last_generated=NOW - timedelta(hours=10))
    assert window_start(NOW, recent, lookback_hours=24, max_lookback_hours=72) == (
        NOW - timedelta(hours=10) - WINDOW_OVERLAP
    )
    stale = History(last_generated=NOW - timedelta(days=30))
    assert window_start(NOW, stale, lookback_hours=24, max_lookback_hours=72) == NOW - timedelta(
        hours=72
    )
    assert window_start(
        NOW, recent, lookback_hours=24, max_lookback_hours=72, override_hours=5
    ) == (NOW - timedelta(hours=5))


def test_build_candidates_windows_filters_caps_and_merges(config: Config) -> None:
    a, b = config.sources
    a_items = [
        make_item("https://ex.com/shared", source="Feed A", hours_ago=2),
        make_item("https://ex.com/old", source="Feed A", hours_ago=100),
        make_item("https://ex.com/seen", source="Feed A", hours_ago=1),
        make_item("https://ex.com/undated", source="Feed A", hours_ago=None),
    ]
    b_items = [
        make_item(
            "https://www.ex.com/shared/?utm_source=b",
            source="Feed B",
            hours_ago=3,
            score=50,
            summary="a much longer snippet from B",
        ),
    ] + [make_item(f"https://b.ex/{n}", source="Feed B", hours_ago=1, score=n) for n in range(5)]
    history = History(seen_keys={"ex.com/seen"})

    result = build_candidates(
        [(a, a_items, ""), (b, b_items, "")], history, NOW - timedelta(hours=24)
    )
    keys = [i.key for i in result.by_id.values()]

    assert "ex.com/old" not in keys  # outside the window
    assert "ex.com/seen" not in keys  # already sent
    assert "ex.com/undated" in keys  # undated items are kept
    shared = next(i for i in result.by_id.values() if i.key == "ex.com/shared")
    assert shared.also_in == ["Feed B"]
    assert shared.score == 50 and shared.summary == "a much longer snippet from B"
    # Feed B is capped at 3, keeping its highest scores (the shared item scored 50).
    assert {k for k in keys if k.startswith("b.ex/")} == {"b.ex/4", "b.ex/3"}
    assert list(result.by_id)[0] == "c1"
    assert [r.kept for r in result.reports] == [2, 3]


def _pool() -> dict[str, object]:
    return {f"c{n}": make_item(f"https://ex.com/{n}", title=f"T{n}") for n in range(1, 8)}


def test_validate_selection_drops_bad_ids_and_enforces_counts(config: Config) -> None:
    config.profile.count.max = 2
    config.profile.count.quick_hits = 1
    pool = _pool()
    output = SelectionOutput(
        picks=[
            Pick(id="c1", related_ids=["c2", "c99"], reason="r1"),
            Pick(id="c2", reason="duplicate of a related id"),
            Pick(id="nope", reason="unknown"),
            Pick(id="c3", reason="r3"),
            Pick(id="c4", reason="over the max"),
        ],
        quick_hits=["c1", "c5", "c6"],
    )
    selection = validate_selection(output, pool, config)  # type: ignore[arg-type]
    assert [p.id for p, _, _ in selection.picks] == ["c1", "c3"]
    assert [r.title for r in selection.picks[0][2]] == ["T2"]
    assert [hid for hid, _ in selection.quick_hits] == ["c5"]


def _record(config: Config, written: DigestOutput | None):
    pool = _pool()
    selection = validate_selection(
        SelectionOutput(
            picks=[Pick(id="c1", reason="r1"), Pick(id="c2", reason="r2")], quick_hits=["c3"]
        ),
        pool,  # type: ignore[arg-type]
        config,
    )
    from newsring.collect import Candidates

    candidates = Candidates(by_id=pool, reports=[], window_start=NOW)  # type: ignore[arg-type]
    stats = RunStats(window_start=NOW, candidates=7, triaged=7, model="test/model")
    return assemble(written, selection, candidates, stats, date(2026, 10, 13), NOW)


def test_assemble_keeps_editor_order_and_falls_back_for_skipped_stories(config: Config) -> None:
    written = DigestOutput(
        title="Today",
        intro="Intro.",
        stories=[
            WrittenStory(id="c1", headline="H1", summary="S1"),
            WrittenStory(id="c9", headline="X", summary="X"),
        ],
        quick_hits=[QuickHitLine(id="c3", line="Q3")],
    )
    record = _record(config, written)
    assert [s.headline for s in record.stories] == ["H1", "T2"]  # c2 skipped by the writer
    assert record.stories[1].item.url == "https://ex.com/2"
    assert record.quick_hits[0].line == "Q3"


def test_render_and_archive_round_trip(config: Config, tmp_path: Path) -> None:
    record = _record(
        config,
        DigestOutput(
            title="A <b>title</b>",
            intro="Intro with `code`.",
            stories=[
                WrittenStory(id="c1", headline="H1", summary="Body **bold**.", why_it_matters="W")
            ],
        ),
    )
    markdown = to_markdown(record)
    assert "[ex.com](https://ex.com/1) · via Feed A" in markdown
    page = to_html(record, index_href="index.html")
    assert "A &lt;b&gt;title&lt;/b&gt;" in page  # escaped, never injected
    assert "<strong>bold</strong>" in page
    assert 'href="https://ex.com/1"' in page

    archive = tmp_path / "news"
    write_archive(record, archive)
    config.delivery.site_url = "https://example.github.io/NewsRing"
    site = tmp_path / "site"
    assert build_site(archive, site, config) == 1
    assert (site / "2026-10-13.html").exists() and (site / "today.html").exists()
    feed = json.loads((site / "news_today.json").read_text(encoding="utf-8"))
    assert feed["page_url"] == "https://example.github.io/NewsRing/2026-10-13.html"
    assert feed["image_url"] is None  # no card was rendered
    assert feed["stories"][0]["summary_html"] == "<p>Body <strong>bold</strong>.</p>\n"

    # The next day's run treats this digest's stories as already sent.
    history = load_history(archive, days=14, today=date(2026, 10, 14))
    assert {"ex.com/1", "ex.com/2", "ex.com/3"} <= history.seen_keys
    # Re-running the same day ignores that day's own record.
    assert load_history(archive, days=14, today=date(2026, 10, 13)).seen_keys == set()


def test_usage_from_payload_reads_only_each_nodes_own_calls() -> None:
    from newsring.pipeline import usage_from_payload

    call = {"input_tokens": 100, "output_tokens": 20, "total_cost": 0.001}
    node = {"details": {"internals": {"llm_details": [call]}}}
    # Each node embeds its parent's details too; those must not be counted.
    child = {"details": {"internals": {"llm_details": [call]}}, "parent": node}
    usage = usage_from_payload({"runs": [{"nodes": [node, child]}]})
    assert usage is not None
    assert (usage.calls, usage.input_tokens, usage.output_tokens) == (2, 200, 40)
    assert usage.cost_usd == 0.002

    unknown_cost = {
        "runs": [{"nodes": [{"details": {"internals": {"llm_details": [{"input_tokens": 5}]}}}]}]
    }
    assert usage_from_payload(unknown_cost).cost_usd is None  # type: ignore[union-attr]
    assert usage_from_payload({"unexpected": "shape"}) is None
    assert usage_from_payload({"runs": [{"nodes": [{"details": None}]}]}) is None


def test_email_html_is_inline_styled_and_escaped(config: Config) -> None:
    from newsring.render import to_email_html

    record = _record(
        config,
        DigestOutput(
            title="<script>x</script>",
            intro="Intro.",
            stories=[WrittenStory(id="c1", headline="H1", summary="S1")],
        ),
    )
    html = to_email_html(record, web_url="https://site/2026-10-13.html", project_url="https://proj")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "var(--" not in html  # email clients ignore CSS variables
    assert "<style" not in html
    assert 'href="https://site/2026-10-13.html"' in html and 'href="https://proj"' in html


def test_recipients_parse_a_list_and_drop_duplicates(
    config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    from newsring.deliver import recipients

    monkeypatch.setenv("NEWSRING_EMAIL_TO", "a@x.com, b@y.com;A@x.com\n c@z.com,,")
    assert recipients(config) == ["a@x.com", "b@y.com", "c@z.com"]
