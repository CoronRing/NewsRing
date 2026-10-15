"""Load and validate a NewsRing configuration file.

A configuration is one TOML file holding the reader's profile, the model to
use, how a run behaves, where the digest goes, and the list of sources. See
`docs/configuration.md` for every field.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SourceKind = Literal["feed", "hn_algolia", "hf_daily_papers", "hf_trending_models"]
DetailLevel = Literal["brief", "standard", "deep"]


class _Strict(BaseModel):
    """Base for config sections: unknown keys are an error, not silently ignored."""

    model_config = ConfigDict(extra="forbid")


class CountRange(_Strict):
    """How many stories the reader wants.

    Attributes:
        min: Fewest main stories on a normal day. The editor may go under this
            on a genuinely slow day rather than pad with filler.
        max: Most main stories. Hard ceiling.
        quick_hits: Most one-line mentions listed after the main stories.
    """

    min: int = Field(default=5, ge=0)
    max: int = Field(default=10, ge=1)
    quick_hits: int = Field(default=5, ge=0)

    @model_validator(mode="after")
    def _ordered(self) -> CountRange:
        if self.min > self.max:
            raise ValueError(f"count.min ({self.min}) is greater than count.max ({self.max})")
        return self


class Tone(_Strict):
    """How the digest should read.

    Attributes:
        detail: ``brief`` is one or two sentences per story, ``standard`` a
            short paragraph, ``deep`` several paragraphs with technical detail.
        style: Free-text voice, for example ``"dry and lightly humorous"``.
        language: Language the digest is written in.
    """

    detail: DetailLevel = "standard"
    style: str = "clear and direct, engineer to engineer"
    language: str = "English"


class Profile(_Strict):
    """What the reader cares about.

    Attributes:
        name: How the digest addresses the reader. Optional.
        interests: Free text describing what to look for. This is the main
            signal the editor ranks against, so specifics beat categories.
        avoid: Free text describing what to leave out.
        count: How many stories to pick.
        tone: How to write them up.
    """

    name: str = ""
    interests: str
    avoid: str = ""
    count: CountRange = CountRange()
    tone: Tone = Tone()


class LLMSettings(_Strict):
    """The model behind every agent.

    Attributes:
        provider: A key of `newsring.llm.PROVIDERS`.
        model: Model name as the provider spells it.
        api_base: Endpoint override, required for ``openai_compatible``.
        api_key_env: Environment variable holding the key, when the provider's
            default variable is not the one to use.
        temperature: Sampling temperature. Omitted when unset, since some
            reasoning models reject it.
        reasoning_effort: Passed through for providers that support it.
        triage_model: A cheaper model for the triage pass. Defaults to `model`.
        fallback_models: Models tried, in order, when `model` is rate limited
            on every key or overloaded. Same provider.
        rotation_cooldown: When every model and key has failed, seconds to
            wait before trying them all again. Doubles after each failed pass.
        rotation_rounds: Passes over every model and key before a call fails.
    """

    provider: str = "openai"
    model: str = "gpt-6-luna"
    api_base: str | None = None
    api_key_env: str | None = None
    temperature: float | None = None
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] | None = None
    triage_model: str | None = None
    fallback_models: list[str] = Field(default_factory=list)
    rotation_cooldown: float = Field(default=30.0, ge=0)
    rotation_rounds: int = Field(default=4, ge=1)


class RunSettings(_Strict):
    """How one run gathers and narrows candidates.

    Attributes:
        lookback_hours: Every run reads this many hours back. Stories already
            sent are filtered out by history, so overlap between days is safe.
        history_days: Stories sent in this many past days are never sent
            again (matched by URL).
        recent_days: Headlines from this many past days are shown to the
            agents as already covered, so the same story from a different
            source is not repeated either.
        timezone: IANA zone that decides which date a digest belongs to.
        triage_threshold: Above this many candidates, a triage pass scores them
            in batches before the editor sees them.
        triage_batch_size: Candidates per triage call.
        triage_keep: How many triaged candidates go on to the editor.
        enrich: Fetch the full text of picked articles before writing.
        enrich_max_chars: Per-article cap on fetched text.
        fetch_timeout: Per-request HTTP timeout in seconds.
        fetch_concurrency: Parallel HTTP requests.
        save_traces: Let railtracks record each run under `.railtracks/` next to
            the config file. Applied process-wide through railtracks'
            environment variables, since railtracks has no per-Flow switch.
    """

    lookback_hours: int = Field(default=72, ge=1)
    history_days: int = Field(default=14, ge=0)
    recent_days: int = Field(default=3, ge=0)
    timezone: str = "America/Los_Angeles"
    triage_threshold: int = Field(default=150, ge=1)
    triage_batch_size: int = Field(default=60, ge=1)
    triage_keep: int = Field(default=80, ge=1)
    enrich: bool = True
    enrich_max_chars: int = Field(default=6000, ge=500)
    fetch_timeout: float = Field(default=20.0, gt=0)
    fetch_concurrency: int = Field(default=8, ge=1)
    save_traces: bool = True


class HeadlineSettings(_Strict):
    """The daily top stories card: the few most exciting AI stories, for anyone.

    Unlike the digest, this is not personalized. It is meant to be shared, so
    it ranks for a general technical audience and reads a longer window.

    Attributes:
        enabled: Produce the card.
        count: Stories on the card.
        window_hours: How far back to look. Longer than the digest's window so
            a big story stays on the card while it is still the story.
        audience: Who the card is for, in free text. Steers what counts as exciting.
        image: Render the card as a PNG. Needs a Chromium-based browser; see
            `newsring.card`.
    """

    enabled: bool = True
    count: int = Field(default=3, ge=1, le=5)
    window_hours: int = Field(default=72, ge=1)
    audience: str = "developers and technically minded people who follow AI"
    image: bool = True


class EmailDelivery(_Strict):
    """Send the digest by email through Emalia.

    Each recipient gets their own message, so on a mailing list nobody sees
    anyone else's address.

    Attributes:
        enabled: Whether `newsring run` sends email. `--no-email` overrides it.
        to_env: Environment variable holding the recipient list, comma
            separated. Kept out of the config file so it can be committed, and
            so a public repository does not publish its readers' addresses.
        env_prefix: Prefix of the Emalia mailbox variables. ``EMALIA_`` also
            accepts the standard ``GOOGLE_*`` aliases.
        subject_prefix: Prepended to the digest title.
    """

    enabled: bool = False
    to_env: str = "NEWSRING_EMAIL_TO"
    env_prefix: str = "EMALIA_"
    subject_prefix: str = "NewsRing: "


class DeliverySettings(_Strict):
    """Where a finished digest goes.

    Attributes:
        archive_dir: Every digest is written here as JSON and Markdown, one
            pair per day. It doubles as the history that prevents repeats, so
            keep it.
        latest_markdown: When set, the newest digest is also written to this
            file, so the repository always shows today's news at a fixed path.
        site_dir: When set, a static site is rebuilt here: one page per
            digest, plus stable URLs for the newest one (see `newsring.deliver`).
        site_url: Public URL the site is served from, used for links in email
            and in the JSON feed. Ends with a slash.
        site_title: Heading of the site index.
        project_url: Where readers can get their own feed, shown on the card,
            the site and in email.
        email: Email delivery settings.
    """

    archive_dir: Path = Path("news")
    latest_markdown: Path | None = None
    site_dir: Path | None = None
    site_url: str = ""
    site_title: str = "NewsRing"
    project_url: str = "https://github.com/CoronRing/NewsRing"
    email: EmailDelivery = EmailDelivery()

    @property
    def public_url(self) -> str:
        """`site_url` with exactly one trailing slash, or empty."""
        return self.site_url.rstrip("/") + "/" if self.site_url else ""


class SourceSpec(_Strict):
    """One place news comes from.

    Attributes:
        name: Display name, unique within the config.
        kind: How to read it. ``feed`` covers RSS and Atom, including GitHub
            ``releases.atom``.
        url: The endpoint.
        max_items: Most recent items kept from this source per run.
        min_score: Drop items whose engagement score (HN points, paper
            upvotes, model likes) is below this. Ignored for plain feeds.
        tags: Free labels shown to the editor, for example ``"lab"``.
        enabled: Set false to keep a source in the file without reading it.
        note: Why the source is configured the way it is. Not used at runtime.
    """

    name: str
    kind: SourceKind = "feed"
    url: str
    max_items: int = Field(default=20, ge=1)
    min_score: float | None = None
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    note: str = ""


class Config(_Strict):
    """A complete NewsRing configuration.

    Attributes:
        profile: The reader.
        llm: The model.
        run: Run behaviour.
        headlines: The shareable top stories card.
        delivery: Output destinations.
        sources: Feeds and APIs to read.
        base_dir: Directory relative paths resolve against. Set by `load_config`
            to the config file's directory.
    """

    profile: Profile
    llm: LLMSettings = LLMSettings()
    run: RunSettings = RunSettings()
    headlines: HeadlineSettings = HeadlineSettings()
    delivery: DeliverySettings = DeliverySettings()
    sources: list[SourceSpec]
    base_dir: Path = Path(".")

    @model_validator(mode="after")
    def _unique_sources(self) -> Config:
        names = [s.name for s in self.sources]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            raise ValueError(f"source names must be unique, repeated: {', '.join(duplicates)}")
        return self

    @property
    def enabled_sources(self) -> list[SourceSpec]:
        """Sources with `enabled` set."""
        return [s for s in self.sources if s.enabled]

    def resolve(self, path: Path) -> Path:
        """Resolve a configured path against the config file's directory."""
        return path if path.is_absolute() else (self.base_dir / path).resolve()


def load_config(path: str | Path) -> Config:
    """Read and validate a TOML configuration file.

    Args:
        path: Path to the TOML file.

    Returns:
        The validated configuration, with `base_dir` set to the file's directory.

    Raises:
        FileNotFoundError: If the file does not exist.
        pydantic.ValidationError: If a field is missing, unknown or out of range.
    """
    file = Path(path).resolve()
    with file.open("rb") as handle:
        raw: dict[str, Any] = tomllib.load(handle)
    raw["base_dir"] = file.parent
    return Config.model_validate(raw)
