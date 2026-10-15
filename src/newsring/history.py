"""The digest archive, read back as history.

Each run writes ``<archive_dir>/<date>.json``. Reading those back tells the
next run what must not be repeated, in two ways:

- **Exact repeats.** The canonical URL of everything already sent (stories,
  related coverage, quick hits) within `history_days` is dropped from the
  candidates before any agent sees them.
- **The same story from a different source.** A URL check cannot catch a
  second article about yesterday's launch. So the headlines of the last
  `recent_days` digests and cards are shown to the agents as already covered,
  and they are told to skip those stories unless something substantial changed.

Keeping the archive as the only state means a deployment needs no database,
and a scheduled job can persist it by committing one directory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ValidationError

from newsring.models import DigestRecord, Item


@dataclass(frozen=True, slots=True)
class Covered:
    """One story that already went out, as shown to the agents.

    Attributes:
        date: Digest date (``YYYY-MM-DD``).
        headline: The headline it went out under.
        source: Host of its link, so the agent can match coverage elsewhere.
    """

    date: str
    headline: str
    source: str

    def line(self) -> str:
        """One prompt line: ``- 2026-10-14: Headline (host)``."""
        return f"- {self.date}: {self.headline} ({self.source})"


@dataclass(slots=True)
class History:
    """What earlier digests tell the next run.

    Attributes:
        seen_keys: Canonical URLs of every story already sent in the digest
            within `history_days`.
        card_keys: Canonical URLs of every story already on a card within
            `history_days`.
        covered: Digest stories and quick hits from the last `recent_days`,
            newest first.
        carded: Card stories from the last `recent_days`, newest first.
        records: The archived digests read, newest first.
    """

    seen_keys: set[str] = field(default_factory=set)
    card_keys: set[str] = field(default_factory=set)
    covered: list[Covered] = field(default_factory=list)
    carded: list[Covered] = field(default_factory=list)
    records: list[DigestRecord] = field(default_factory=list)


def record_path(archive_dir: Path, day: str) -> Path:
    """Path of the JSON record for one date (``YYYY-MM-DD``)."""
    return archive_dir / f"{day}.json"


def list_records(archive_dir: Path) -> list[DigestRecord]:
    """Read every valid digest record in the archive, newest first.

    Files that fail to parse are skipped, so one hand-edited or truncated file
    cannot stop the daily run.
    """
    if not archive_dir.is_dir():
        return []
    records: list[DigestRecord] = []
    for path in sorted(archive_dir.glob("*.json"), reverse=True):
        try:
            records.append(DigestRecord.model_validate_json(path.read_text(encoding="utf-8")))
        except (ValidationError, ValueError):
            continue
    return records


def _host(item: Item) -> str:
    return urlsplit(item.url).netloc.removeprefix("www.") or item.source


def load_history(archive_dir: Path, *, days: int, recent_days: int, today: date) -> History:
    """Collect what the next run needs from the archive.

    Args:
        archive_dir: Where digests are written.
        days: How many days back count as already sent, by URL.
        recent_days: How many days of headlines the agents are shown as
            already covered.
        today: The digest date of the run being prepared. A record for this
            date is ignored, so re-running a day regenerates it rather than
            treating its own stories as already sent.

    Returns:
        The history. Empty when the archive does not exist yet.
    """
    cutoff = (today - timedelta(days=days)).isoformat()
    recent_cutoff = (today - timedelta(days=recent_days)).isoformat()
    records = [r for r in list_records(archive_dir) if cutoff <= r.date < today.isoformat()]
    history = History(records=records)
    for record in records:
        for story in record.stories:
            history.seen_keys.add(story.item.key)
            history.seen_keys.update(r.key for r in story.related)
        history.seen_keys.update(hit.item.key for hit in record.quick_hits)
        history.card_keys.update(h.item.key for h in record.headlines)
        if record.date < recent_cutoff:
            continue
        history.covered += [Covered(record.date, s.headline, _host(s.item)) for s in record.stories]
        history.covered += [
            Covered(record.date, q.item.title, _host(q.item)) for q in record.quick_hits
        ]
        history.carded += [
            Covered(record.date, h.headline, _host(h.item)) for h in record.headlines
        ]
    return history


def covered_section(covered: list[Covered], *, what: str) -> str:
    """The "already covered" block appended to an agent's input.

    Args:
        covered: Stories that already went out.
        what: Where they went out, for the heading, e.g. "your recent digests".

    Returns:
        A Markdown section, or an empty string when nothing is covered yet.
    """
    if not covered:
        return ""
    lines = "\n".join(c.line() for c in covered)
    return (
        f"\n\n## Already covered in {what}\n\n"
        "These stories already went out. Do not pick any of them again, even when a candidate comes "
        "from a different source or carries a different headline. The only exception is a "
        "substantial new development (for example, an announced model is now available, or a key "
        "claim was corrected); then you may pick it, and what you write must say what is new.\n\n"
        f"{lines}"
    )
