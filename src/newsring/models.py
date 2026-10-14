"""Data shapes shared across the pipeline.

Two families live here. `Item` and `DigestRecord` are NewsRing's own records.
The `*Output` models are the structured outputs the agents return, so their
field descriptions are written for the model, not for a developer.

Agents never see or return URLs. They refer to stories by the short candidate
id (``c17``) and the renderer looks the link up, so a model cannot invent or
mangle a link however it misbehaves.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Item(BaseModel):
    """One story from one source, normalized.

    Attributes:
        key: Stable identity across runs: the canonical URL.
        source: Name of the `SourceSpec` it came from.
        tags: The source's tags.
        title: Headline as published.
        url: Link to the story itself.
        discussion_url: Link to a discussion thread, when the source has one
            separate from the story (Hacker News, Lobsters).
        published: Publication time in UTC, when the source gives one.
        summary: Plain-text snippet or abstract, trimmed.
        content: Longer plain text when the feed carries the full article, or
            after enrichment fetches it.
        score: Engagement signal (points, upvotes, likes), when the source has one.
        comments: Comment count, when the source has one.
        also_in: Other sources that carried the same URL in this run.
    """

    key: str
    source: str
    tags: list[str] = Field(default_factory=list)
    title: str
    url: str
    discussion_url: str | None = None
    published: datetime | None = None
    summary: str = ""
    content: str = ""
    score: float | None = None
    comments: int | None = None
    also_in: list[str] = Field(default_factory=list)


class SourceReport(BaseModel):
    """How one source fared in a run.

    Attributes:
        name: Source name.
        ok: Whether the fetch and parse succeeded.
        fetched: Items parsed before any filtering.
        kept: Items that survived the time window, history and per-source cap.
        error: Short error description when `ok` is false.
    """

    name: str
    ok: bool
    fetched: int = 0
    kept: int = 0
    error: str = ""


# -- Agent outputs ------------------------------------------------------------


class TriageScore(BaseModel):
    """Relevance of one candidate."""

    id: str = Field(description="The candidate id exactly as given, for example 'c17'.")
    score: int = Field(
        ge=0, le=10, description="0 = irrelevant to the reader, 10 = exactly what they asked for."
    )


class TriageOutput(BaseModel):
    """Scores for a batch of candidates."""

    scores: list[TriageScore] = Field(description="One entry per candidate in the batch.")


class Pick(BaseModel):
    """One story chosen for the digest."""

    id: str = Field(description="The candidate id exactly as given, for example 'c17'.")
    related_ids: list[str] = Field(
        default_factory=list,
        description="Ids of other candidates covering the same story, merged into this pick.",
    )
    reason: str = Field(description="One sentence: why this reader would care.")


class SelectionOutput(BaseModel):
    """The editor's choice for today."""

    picks: list[Pick] = Field(description="Main stories, most important first.")
    quick_hits: list[str] = Field(
        default_factory=list,
        description="Ids of stories worth a one-line mention but not a full write-up.",
    )
    slow_day_note: str = Field(
        default="",
        description="If fewer stories than the minimum were worth picking, say why in one sentence.",
    )


class WrittenStory(BaseModel):
    """The write-up of one main story."""

    id: str = Field(description="The story id exactly as given, for example 'c17'.")
    headline: str = Field(description="A short headline in the requested voice.")
    summary: str = Field(
        description="The write-up. Markdown allowed (emphasis, inline code, short lists); no links, no headings."
    )
    why_it_matters: str = Field(
        default="", description="One sentence tying the story to the reader's interests."
    )


class QuickHitLine(BaseModel):
    """A one-line mention."""

    id: str = Field(description="The story id exactly as given.")
    line: str = Field(description="One sentence, no link.")


class DigestOutput(BaseModel):
    """The written digest."""

    title: str = Field(description="A title for today's digest, under 80 characters.")
    intro: str = Field(description="Two or three sentences setting up today's stories.")
    stories: list[WrittenStory] = Field(description="One entry per main story, in the given order.")
    quick_hits: list[QuickHitLine] = Field(default_factory=list)
    sign_off: str = Field(default="", description="An optional one-line closing.")


class Headline(BaseModel):
    """One story on the shareable card."""

    id: str = Field(description="The candidate id exactly as given, for example 'h12'.")
    kicker: str = Field(
        description="Two or three words naming the kind of story, e.g. 'Model release', 'Research', 'Open source', 'Incident'."
    )
    headline: str = Field(description="A punchy headline under 70 characters. Plain text.")
    blurb: str = Field(
        description="One sentence under 150 characters saying what happened and why it is exciting. Plain text."
    )


class HeadlineOutput(BaseModel):
    """The day's top stories for the card."""

    stories: list[Headline] = Field(description="The stories, most exciting first.")


# -- Archive ------------------------------------------------------------------


class DigestStory(BaseModel):
    """A main story as stored and rendered: the write-up joined with its links."""

    headline: str
    summary: str
    why_it_matters: str = ""
    reason: str = ""
    item: Item
    related: list[Item] = Field(default_factory=list)


class DigestHeadline(BaseModel):
    """A card story as stored and rendered."""

    kicker: str
    headline: str
    blurb: str
    item: Item


class DigestQuickHit(BaseModel):
    """A quick hit as stored and rendered."""

    line: str
    item: Item


class Usage(BaseModel):
    """Model usage summed over every call in a run.

    Attributes:
        calls: Model calls made.
        input_tokens: Prompt tokens.
        output_tokens: Completion tokens.
        cost_usd: Cost as reported by the provider integration. None when any
            call reported no cost, rather than a total that silently undercounts.
    """

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None


class RunStats(BaseModel):
    """Numbers describing one run, kept with the digest for later comparison.

    Attributes:
        window_start: Oldest publication time accepted.
        candidates: Items after windowing, history and dedup.
        triaged: Items passed to the editor after triage. Equals `candidates`
            when triage did not run.
        enriched: Picked items whose full text was fetched successfully.
        headline_candidates: Items the headline card chose from.
        model: Provider and model configured.
        served_by: Model (and key number) that answered each call, when the
            model failed over between keys or models.
        seconds: Wall-clock duration of the pipeline, excluding start-up.
        usage: Token and cost totals, when railtracks reported them.
    """

    window_start: datetime
    candidates: int
    triaged: int
    enriched: int = 0
    headline_candidates: int = 0
    model: str
    served_by: list[str] = Field(default_factory=list)
    seconds: float = 0.0
    usage: Usage | None = None


class DigestRecord(BaseModel):
    """Everything about one day's digest. One JSON file per date in the archive."""

    date: str
    generated_at: datetime
    title: str
    intro: str
    stories: list[DigestStory]
    quick_hits: list[DigestQuickHit] = Field(default_factory=list)
    sign_off: str = ""
    slow_day_note: str = ""
    headlines: list[DigestHeadline] = Field(default_factory=list)
    sources: list[SourceReport] = Field(default_factory=list)
    stats: RunStats
