"""Turn raw source items into the candidate list the agents choose from.

Everything here is deterministic. The order of operations matters:

1. Drop items older than the window. Undated items are kept.
2. Drop items already sent in an earlier digest.
3. Keep each source's best `max_items`: highest score where the source has
   one, newest otherwise. Capping after windowing means a busy source cannot
   crowd out its own fresh items with old ones.
4. Merge items that share a canonical URL across sources, recording where
   else each appeared. Cross-source coverage is a useful signal for the editor.
5. Number the survivors ``c1``, ``c2``, … newest first.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from newsring.config import SourceSpec
from newsring.history import History
from newsring.models import Item, SourceReport
from newsring.sources import report

#: How far before the last digest the next window starts. Feeds often publish
#: with timestamps a little behind when the item actually appears.
WINDOW_OVERLAP = timedelta(hours=2)


@dataclass(slots=True)
class Candidates:
    """The output of collection.

    Attributes:
        by_id: Candidate id to item, in id order.
        reports: One report per source.
        window_start: Oldest publication time accepted.
    """

    by_id: dict[str, Item]
    reports: list[SourceReport]
    window_start: datetime


def window_start(
    now: datetime,
    history: History,
    *,
    lookback_hours: int,
    max_lookback_hours: int,
    override_hours: int | None = None,
) -> datetime:
    """Choose the oldest publication time a run accepts.

    Args:
        now: Current time, timezone-aware.
        history: Archive history.
        lookback_hours: Window when there is no earlier digest.
        max_lookback_hours: Longest window after a gap.
        override_hours: Explicit window that ignores history.

    Returns:
        The start of the window.
    """
    if override_hours is not None:
        return now - timedelta(hours=override_hours)
    if history.last_generated is None:
        return now - timedelta(hours=lookback_hours)
    since_last = history.last_generated - WINDOW_OVERLAP
    return max(since_last, now - timedelta(hours=max_lookback_hours))


def _newest_first_key(item: Item) -> float:
    return item.published.timestamp() if item.published else float("-inf")


def _rank_within_source(items: list[Item]) -> list[Item]:
    if any(i.score is not None for i in items):
        return sorted(items, key=lambda i: i.score or 0.0, reverse=True)
    return sorted(items, key=_newest_first_key, reverse=True)


def _merge(kept: Item, extra: Item) -> None:
    """Fold a duplicate into the item already kept."""
    if extra.source not in kept.also_in and extra.source != kept.source:
        kept.also_in.append(extra.source)
    kept.discussion_url = kept.discussion_url or extra.discussion_url
    if extra.score is not None and (kept.score is None or extra.score > kept.score):
        kept.score = extra.score
        kept.comments = extra.comments
    if len(extra.summary) > len(kept.summary):
        kept.summary = extra.summary
    if len(extra.content) > len(kept.content):
        kept.content = extra.content


def build_candidates(
    fetched: list[tuple[SourceSpec, list[Item], str]],
    history: History,
    start: datetime,
    *,
    id_prefix: str = "c",
) -> Candidates:
    """Window, filter, cap, dedupe and number the fetched items.

    Args:
        fetched: Output of `newsring.sources.fetch_all`.
        history: Archive history, for the already-sent filter.
        start: Oldest publication time accepted.
        id_prefix: Letter the ids start with, so two pools built from the same
            fetch (the digest's and the card's) cannot be confused.

    Returns:
        The numbered candidates and a report per source.
    """
    merged: dict[str, Item] = {}
    reports: list[SourceReport] = []
    for spec, items, error in fetched:
        fresh = [
            i
            for i in items
            if (i.published is None or i.published >= start) and i.key not in history.seen_keys
        ]
        capped = _rank_within_source(fresh)[: spec.max_items]
        reports.append(report(spec, len(items), len(capped), error))
        for item in capped:
            if item.key in merged:
                _merge(merged[item.key], item)
            else:
                merged[item.key] = item.model_copy(deep=True)

    newest_first = sorted(merged.values(), key=_newest_first_key, reverse=True)
    by_id = {f"{id_prefix}{n}": item for n, item in enumerate(newest_first, start=1)}
    return Candidates(by_id=by_id, reports=reports, window_start=start)


def describe(candidate_id: str, item: Item, *, summary_chars: int = 280) -> str:
    """Render one candidate as a compact block for an agent prompt.

    Args:
        candidate_id: The ``cN`` id.
        item: The item.
        summary_chars: Snippet length. Short on purpose: the editor ranks on
            title, source and signal, and the writer gets the full text later.

    Returns:
        Two or three lines of plain text.
    """
    meta = [item.source]
    if item.also_in:
        meta.append("also in " + ", ".join(item.also_in))
    if item.score is not None:
        meta.append(f"score {item.score:g}")
    if item.comments:
        meta.append(f"{item.comments} comments")
    if item.published:
        meta.append(item.published.strftime("%Y-%m-%d"))
    if item.tags:
        meta.append("tags: " + ", ".join(item.tags))
    lines = [f"[{candidate_id}] {item.title}", f"    ({'; '.join(meta)})"]
    snippet = item.summary.replace("\n", " ").strip()
    if snippet:
        lines.append(
            "    " + (snippet[:summary_chars] + ("…" if len(snippet) > summary_chars else ""))
        )
    return "\n".join(lines)
