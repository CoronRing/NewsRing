"""The digest archive, read back as history.

Each run writes ``<archive_dir>/<date>.json``. Reading those back gives the two
facts a run needs: when the last digest was made, which sets the time window,
and which stories were already sent, which must not be sent again. Keeping the
archive as the only state means a deployment needs no database, and a
scheduled job can persist it by committing one directory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from newsring.models import DigestRecord


@dataclass(slots=True)
class History:
    """What earlier digests tell the next run.

    Attributes:
        last_generated: When the newest archived digest was made, if any.
        seen_keys: Canonical URLs of every story already sent within the window.
        records: The archived digests read, newest first.
    """

    last_generated: datetime | None = None
    seen_keys: set[str] = field(default_factory=set)
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


def load_history(archive_dir: Path, *, days: int, today: date) -> History:
    """Collect what the next run needs from the archive.

    Args:
        archive_dir: Where digests are written.
        days: How many days back count as already sent.
        today: The digest date of the run being prepared. A record for this
            date is ignored, so re-running a day regenerates it rather than
            treating its own stories as already sent.

    Returns:
        The history. Empty when the archive does not exist yet.
    """
    cutoff = (today - timedelta(days=days)).isoformat()
    records = [r for r in list_records(archive_dir) if cutoff <= r.date < today.isoformat()]
    history = History(records=records)
    if records:
        history.last_generated = max(r.generated_at for r in records)
    for record in records:
        for story in record.stories:
            history.seen_keys.add(story.item.key)
            history.seen_keys.update(r.key for r in story.related)
        history.seen_keys.update(hit.item.key for hit in record.quick_hits)
    return history
