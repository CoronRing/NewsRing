"""One NewsRing run: collect, triage, select, enrich, write.

The run is a railtracks `Flow` whose entry point is the `produce_digest`
function node. Collection and enrichment are plain async Python; the three
agent steps are `rt.call` / `rt.call_batch` so they appear in the run trace.

Model output is never trusted for structure. Every id an agent returns is
checked against the candidates, and every story the writer drops falls back to
its title and snippet, so a misbehaving model degrades the prose but never
loses or invents a link.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import railtracks as rt

from newsring.agents import Agents, build_agents
from newsring.collect import Candidates, build_candidates, describe, window_start
from newsring.config import Config
from newsring.enrich import enrich_items
from newsring.history import History, covered_section, load_history
from newsring.llm import describe_llm
from newsring.models import (
    DigestHeadline,
    DigestOutput,
    DigestQuickHit,
    DigestRecord,
    DigestStory,
    HeadlineOutput,
    Item,
    Pick,
    RunStats,
    SelectionOutput,
    TriageOutput,
    Usage,
)
from newsring.sources import fetch_all
from newsring.text import trim

logger = logging.getLogger(__name__)

#: Score given to every candidate of a triage batch whose call failed, so a
#: failure keeps the batch in play rather than silently dropping it.
NEUTRAL_SCORE = 5


class NoCandidatesError(Exception):
    """No source produced a usable candidate in the window."""


@dataclass(frozen=True, slots=True)
class RunRequest:
    """Inputs to one run.

    Attributes:
        config: The configuration.
        today: Digest date in the configured timezone.
        now: Current time, timezone-aware.
        lookback_hours: Explicit window that ignores history.
    """

    config: Config
    today: date
    now: datetime
    lookback_hours: int | None = None


@dataclass(slots=True)
class Selection:
    """The editor's choice after validation against the candidates.

    Attributes:
        picks: ``(pick, item, related items)`` in the editor's order.
        quick_hits: ``(id, item)`` pairs.
        slow_day_note: The editor's explanation when it picked fewer than asked.
    """

    picks: list[tuple[Pick, Item, list[Item]]]
    quick_hits: list[tuple[str, Item]]
    slow_day_note: str


# -- Steps ----------------------------------------------------------------------


async def triage(agents: Agents, pool: dict[str, Item], config: Config) -> dict[str, Item]:
    """Shrink a large pool to the most relevant `run.triage_keep` candidates.

    Args:
        agents: The agents.
        pool: Candidates by id.
        config: The configuration.

    Returns:
        The kept candidates by id, in their original order. The pool unchanged
        when it is already under `run.triage_threshold`.
    """
    run = config.run
    if len(pool) <= run.triage_threshold:
        return pool
    ids = list(pool)
    batches = [
        ids[i : i + run.triage_batch_size] for i in range(0, len(ids), run.triage_batch_size)
    ]
    prompts = [
        "Score these candidates:\n\n" + "\n\n".join(describe(cid, pool[cid]) for cid in batch)
        for batch in batches
    ]
    results = await rt.call_batch(agents.triage, prompts)

    scores: dict[str, int] = {}
    for batch, result in zip(batches, results, strict=True):
        if isinstance(result, BaseException):
            scores.update(dict.fromkeys(batch, NEUTRAL_SCORE))
            continue
        output: TriageOutput = result.structured
        returned = {s.id: s.score for s in output.scores if s.id in pool}
        # A candidate the model skipped keeps a neutral score rather than zero.
        scores.update({cid: returned.get(cid, NEUTRAL_SCORE) for cid in batch})

    order = {cid: n for n, cid in enumerate(ids)}
    keep = sorted(ids, key=lambda cid: (-scores[cid], order[cid]))[: run.triage_keep]
    return {cid: pool[cid] for cid in sorted(keep, key=order.__getitem__)}


def validate_selection(output: SelectionOutput, pool: dict[str, Item], config: Config) -> Selection:
    """Check the editor's ids and enforce the configured counts.

    Unknown ids are dropped, an id is used at most once across picks, related
    ids and quick hits, and both lists are cut to their configured maximum.

    Args:
        output: What the editor returned.
        pool: The candidates it chose from.
        config: The configuration.

    Returns:
        The validated selection.
    """
    count = config.profile.count
    used: set[str] = set()
    picks: list[tuple[Pick, Item, list[Item]]] = []
    for pick in output.picks:
        if len(picks) >= count.max:
            break
        if pick.id not in pool or pick.id in used:
            continue
        used.add(pick.id)
        related: list[Item] = []
        for rid in pick.related_ids:
            if rid in pool and rid not in used:
                used.add(rid)
                related.append(pool[rid])
        picks.append((pick, pool[pick.id], related))

    hits: list[tuple[str, Item]] = []
    for hid in output.quick_hits:
        if len(hits) >= count.quick_hits:
            break
        if hid in pool and hid not in used:
            used.add(hid)
            hits.append((hid, pool[hid]))
    return Selection(picks=picks, quick_hits=hits, slow_day_note=output.slow_day_note.strip())


def writer_brief(selection: Selection, config: Config) -> str:
    """Build the writer's input: the picked stories with their material."""
    limit = config.run.enrich_max_chars
    parts = ["# Stories", ""]
    for pick, item, related in selection.picks:
        parts.append(f"## [{pick.id}] {item.title}")
        parts.append(
            f"Source: {item.source}"
            + (f" (also in {', '.join(item.also_in)})" if item.also_in else "")
        )
        if item.published:
            parts.append(f"Published: {item.published:%Y-%m-%d}")
        parts.append(f"Editor's reason: {pick.reason}")
        if related:
            parts.append(
                "Related coverage: " + "; ".join(f"{r.title} ({r.source})" for r in related)
            )
        parts += ["", "Material:", trim(item.content or item.summary or "(title only)", limit), ""]
    if selection.quick_hits:
        parts += ["# Quick hits", ""]
        for hid, item in selection.quick_hits:
            snippet = trim(item.summary.replace("\n", " "), 300)
            parts.append(
                f"- [{hid}] {item.title} ({item.source}){': ' + snippet if snippet else ''}"
            )
    return "\n".join(parts)


def assemble(
    written: DigestOutput | None,
    selection: Selection,
    candidates: Candidates,
    stats: RunStats,
    today: date,
    generated_at: datetime,
) -> DigestRecord:
    """Join the writer's prose with the validated selection.

    Stories come out in the editor's order whatever order the writer used.
    A story the writer skipped falls back to its own title and snippet.

    Args:
        written: The writer's output, or None if there was nothing to write.
        selection: The validated selection.
        candidates: The collection result, for the source reports.
        stats: Run statistics.
        today: Digest date.
        generated_at: When the run finished, timezone-aware.

    Returns:
        The record to archive, render and deliver.
    """
    by_id = {s.id: s for s in written.stories} if written else {}
    lines = {q.id: q.line for q in written.quick_hits} if written else {}
    stories = []
    for pick, item, related in selection.picks:
        story = by_id.get(pick.id)
        stories.append(
            DigestStory(
                headline=story.headline if story else item.title,
                summary=story.summary if story else trim(item.summary, 500),
                why_it_matters=story.why_it_matters if story else "",
                reason=pick.reason,
                item=item,
                related=related,
            )
        )
    hits = [
        DigestQuickHit(line=lines.get(hid, item.title), item=item)
        for hid, item in selection.quick_hits
    ]
    title = written.title if written else f"NewsRing for {today.isoformat()}"
    intro = written.intro if written else "Nothing in today's sources matched your interests."
    return DigestRecord(
        date=today.isoformat(),
        generated_at=generated_at,
        title=title,
        intro=intro,
        stories=stories,
        quick_hits=hits,
        sign_off=written.sign_off if written else "",
        slow_day_note=selection.slow_day_note,
        sources=candidates.reports,
        stats=stats,
    )


# -- Flow -----------------------------------------------------------------------


@dataclass(slots=True)
class Pools:
    """Both candidate pools, built from one fetch.

    Attributes:
        digest: The personal digest's candidates: inside the run's window and
            never sent before.
        headlines: The card's candidates: the longer headline window, with no
            history filter, since the card is about what matters now.
    """

    digest: Candidates
    headlines: Candidates


async def collect(request: RunRequest, history: History) -> Pools:
    """Fetch every enabled source once and build both candidate pools."""
    config = request.config
    start = window_start(
        request.now,
        lookback_hours=config.run.lookback_hours,
        override_hours=request.lookback_hours,
    )
    fetched = await fetch_all(
        config.enabled_sources,
        timeout=config.run.fetch_timeout,
        concurrency=config.run.fetch_concurrency,
    )
    headline_start = request.now - timedelta(hours=config.headlines.window_hours)
    return Pools(
        digest=build_candidates(fetched, history, start),
        # The card ignores what the digest sent, but never repeats its own stories.
        headlines=build_candidates(
            fetched, History(seen_keys=history.card_keys), headline_start, id_prefix="h"
        ),
    )


async def pick_headlines(
    agents: Agents, pool: dict[str, Item], config: Config, today: date, history: History
) -> list[DigestHeadline]:
    """Choose the card's top stories from the headline pool.

    Unknown or repeated ids are dropped, and the list is cut to
    `headlines.count`. A failure here never fails the run: the digest is the
    product and the card is a bonus, so an error yields an empty list.

    Args:
        agents: The agents.
        pool: Headline candidates by id.
        config: The configuration.
        today: Digest date, for the prompt.
        history: Archive history; recent cards are listed as already covered.

    Returns:
        The card's stories, most exciting first.
    """
    if not config.headlines.enabled or not pool:
        return []
    listing = "\n\n".join(describe(hid, item) for hid, item in pool.items())
    header = (
        f"Today is {today:%A %d %B %Y}. {len(pool)} candidates from the last "
        f"{config.headlines.window_hours} hours:\n\n"
    )
    try:
        recent = covered_section(history.carded, what="recent cards")
        response = await rt.call(agents.headliner, header + listing + recent)
    except Exception as exc:  # noqa: BLE001 - the card is optional
        logger.warning("Headline card skipped: %s", exc)
        return []
    output: HeadlineOutput = response.structured
    picked: list[DigestHeadline] = []
    seen: set[str] = set()
    for story in output.stories:
        if story.id in pool and story.id not in seen:
            seen.add(story.id)
            picked.append(
                DigestHeadline(
                    kicker=story.kicker.strip(),
                    headline=story.headline.strip(),
                    blurb=story.blurb.strip(),
                    item=pool[story.id],
                )
            )
        if len(picked) >= config.headlines.count:
            break
    return picked


@rt.function_node
async def produce_digest(request: RunRequest) -> DigestRecord:
    """Run the whole pipeline once and return the digest record.

    Args:
        request: The run inputs.

    Returns:
        The finished digest record. Nothing is written or sent here.
    """
    started = time.monotonic()
    config = request.config
    agents = build_agents(config)
    history = load_history(
        config.resolve(config.delivery.archive_dir),
        days=config.run.history_days,
        recent_days=config.run.recent_days,
        today=request.today,
    )
    pools = await collect(request, history)
    candidates = pools.digest
    if not candidates.by_id and not pools.headlines.by_id:
        failed = [r.name for r in candidates.reports if not r.ok]
        raise NoCandidatesError(
            f"no candidates in the window starting {candidates.window_start:%Y-%m-%d %H:%M} UTC"
            + (f"; failed sources: {', '.join(failed)}" if failed else "")
        )

    headlines = await pick_headlines(agents, pools.headlines.by_id, config, request.today, history)

    pool = await triage(agents, candidates.by_id, config)
    selection = Selection(picks=[], quick_hits=[], slow_day_note="")
    if pool:
        listing = "\n\n".join(describe(cid, item) for cid, item in pool.items())
        header = f"Today is {request.today:%A %d %B %Y}. {len(pool)} candidates:\n\n"
        recent = covered_section(history.covered, what="your recent digests")
        chosen = await rt.call(agents.editor, header + listing + recent)
        selection = validate_selection(chosen.structured, pool, config)

    enriched = 0
    if config.run.enrich and selection.picks:
        enriched = await enrich_items(
            [item for _, item, _ in selection.picks],
            max_chars=config.run.enrich_max_chars,
            timeout=config.run.fetch_timeout,
            concurrency=config.run.fetch_concurrency,
        )

    written: DigestOutput | None = None
    if selection.picks or selection.quick_hits:
        response = await rt.call(agents.writer, writer_brief(selection, config))
        written = response.structured

    stats = RunStats(
        window_start=candidates.window_start,
        candidates=len(candidates.by_id),
        triaged=len(pool),
        enriched=enriched,
        headline_candidates=len(pools.headlines.by_id),
        model=describe_llm(config.llm),
        served_by=list(getattr(agents.llm, "served", [])),
        seconds=round(time.monotonic() - started, 1),
    )
    record = assemble(written, selection, candidates, stats, request.today, datetime.now(UTC))
    record.headlines = headlines
    return record


def usage_from_payload(payload: dict[str, Any]) -> Usage | None:
    """Sum token usage and cost from a railtracks run payload.

    railtracks exposes per-call usage only inside the run payload (the same
    JSON it saves as a trace), at ``runs[].nodes[].details.internals.llm_details[]``.
    Each node also embeds its parent's details, so only that exact path is
    read; a recursive search would count every call twice. railtracks calls
    this shape unstable, so anything unexpected yields None, never an error.

    Args:
        payload: The dict railtracks passes to a Flow's `payload_callback`.

    Returns:
        The totals, or None if the payload has no recognisable usage.
    """
    try:
        calls = [
            call
            for run in payload["runs"]
            for node in run["nodes"]
            for call in ((node.get("details") or {}).get("internals") or {}).get("llm_details")
            or []
        ]
    except (KeyError, TypeError, AttributeError):
        return None
    if not calls:
        return None
    costs = [c.get("total_cost") for c in calls]
    return Usage(
        calls=len(calls),
        input_tokens=sum(c.get("input_tokens") or 0 for c in calls),
        output_tokens=sum(c.get("output_tokens") or 0 for c in calls),
        cost_usd=None if any(c is None for c in costs) else round(sum(costs), 6),
    )


@dataclass(slots=True)
class UsageCollector:
    """A `payload_callback` that keeps the run's usage totals.

    railtracks swallows any exception raised by a payload callback, so this
    never raises: a failure leaves `usage` as None.
    """

    usage: Usage | None = None

    def __call__(self, payload: dict[str, Any]) -> None:
        self.usage = usage_from_payload(payload)


def build_flow(
    on_payload: Callable[[dict[str, Any]], None] | None = None,
) -> rt.Flow[[RunRequest], DigestRecord]:
    """Wrap `produce_digest` in a Flow.

    Trace recording is not configured here: railtracks deprecated the per-Flow
    `save_state` switch in favour of process-wide environment variables, which
    the CLI sets from `run.save_traces` (see `newsring.cli.configure_traces`).

    Args:
        on_payload: Receives the run payload when the run ends, before
            `invoke` returns. Called whether or not traces are saved.

    Returns:
        The Flow.
    """
    return rt.Flow(name="NewsRing", entry_point=produce_digest, payload_callback=on_payload)
