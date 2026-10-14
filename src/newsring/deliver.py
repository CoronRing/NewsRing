"""Write a finished digest to its destinations.

The archive is always written, because it is also the history the next run
reads. Everything else is optional and configured in ``[delivery]``.

The static site has two kinds of URL. Each digest has a dated page
(``2026-10-13.html``) that never changes. The newest digest is also published
under fixed names, so other pages can link to "today" once and never update
the link:

========================  =================================================
``today.html``            the newest digest's page
``today.png``             the newest top stories card (1200×630 at 2×)
``news_today.json``       the newest digest as JSON (`render.to_web_json`)
``news_today.md``         the newest digest as Markdown
========================  =================================================
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from newsring.card import card_html, render_png
from newsring.config import Config
from newsring.history import list_records, record_path
from newsring.models import DigestRecord
from newsring.render import index_html, to_email_html, to_html, to_markdown, to_web_json

logger = logging.getLogger(__name__)

CARD_FILE = "today.png"
TODAY_PAGE = "today.html"
FEED_JSON = "news_today.json"
FEED_MARKDOWN = "news_today.md"


class DeliveryError(Exception):
    """A configured destination could not be reached."""


@dataclass(frozen=True, slots=True)
class PublicUrls:
    """Absolute URLs for the newest digest, or None where there is no site URL.

    Attributes:
        page: The newest digest's fixed page.
        dated_page: The newest digest's dated page.
        image: The card.
    """

    page: str | None
    dated_page: str | None
    image: str | None


def public_urls(config: Config, record: DigestRecord, *, has_card: bool) -> PublicUrls:
    """Work out where the newest digest is published."""
    base = config.delivery.public_url
    if not base:
        return PublicUrls(None, None, None)
    return PublicUrls(
        page=base + TODAY_PAGE,
        dated_page=f"{base}{record.date}.html",
        image=base + CARD_FILE if has_card else None,
    )


def write_archive(record: DigestRecord, archive_dir: Path) -> Path:
    """Write ``<date>.json`` and ``<date>.md``, replacing any earlier run for the date.

    Args:
        record: The digest.
        archive_dir: Archive directory, created if missing.

    Returns:
        Path of the JSON record.
    """
    archive_dir.mkdir(parents=True, exist_ok=True)
    path = record_path(archive_dir, record.date)
    path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    path.with_suffix(".md").write_text(to_markdown(record), encoding="utf-8")
    return path


def write_latest_markdown(
    record: DigestRecord, path: Path, config: Config, *, has_card: bool
) -> None:
    """Write the newest digest to a fixed Markdown file, such as ``news_today.md``.

    Unlike the archive copy, this one shows the card image, since a fixed file
    and a fixed image URL always describe the same day.
    """
    urls = public_urls(config, record, has_card=has_card)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        to_markdown(record, image_url=urls.image, project_url=config.delivery.project_url),
        encoding="utf-8",
    )


def render_card(record: DigestRecord, site_dir: Path, config: Config) -> bool:
    """Render the newest top stories card into the site as ``today.png``.

    Returns:
        True if the image was written. A missing browser or empty headline
        list returns False and leaves no image, rather than a stale one.
    """
    target = site_dir / CARD_FILE
    target.unlink(missing_ok=True)
    if not (config.headlines.enabled and config.headlines.image and record.headlines):
        return False
    html = card_html(
        record.headlines,
        day=date.fromisoformat(record.date),
        project_url=config.delivery.project_url,
    )
    return render_png(html, target)


def build_site(archive_dir: Path, site_dir: Path, config: Config) -> int:
    """Rebuild the static site from the whole archive.

    Rebuilding everything keeps the site a pure function of the archive (plus
    today's card, which `render_card` writes first), so a template change
    applies to every past digest too.

    Args:
        archive_dir: Archive to read.
        site_dir: Output directory, created if missing.
        config: The configuration.

    Returns:
        Number of digest pages written.
    """
    records = list_records(archive_dir)
    site_dir.mkdir(parents=True, exist_ok=True)
    has_card = (site_dir / CARD_FILE).exists()
    project = config.delivery.project_url
    newest = records[0] if records else None
    urls = (
        public_urls(config, newest, has_card=has_card) if newest else PublicUrls(None, None, None)
    )
    # Inside the site a relative URL works offline too; absolute ones go in feeds.
    local_image = CARD_FILE if has_card else None

    for record in records:
        is_newest = record is newest
        page = to_html(
            record,
            index_href="./",
            image_url=local_image if is_newest else None,
            share_image_url=urls.image if is_newest else None,
            project_url=project,
        )
        (site_dir / f"{record.date}.html").write_text(page, encoding="utf-8")
        if is_newest:
            (site_dir / TODAY_PAGE).write_text(page, encoding="utf-8")

    (site_dir / "index.html").write_text(
        index_html(
            records,
            site_title=config.delivery.site_title,
            image_url=local_image,
            share_image_url=urls.image,
            project_url=project,
        ),
        encoding="utf-8",
    )
    if newest is not None:
        feed = to_web_json(
            newest, page_url=urls.dated_page, image_url=urls.image, project_url=project
        )
        (site_dir / FEED_JSON).write_text(
            json.dumps(feed, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (site_dir / FEED_MARKDOWN).write_text(
            to_markdown(newest, image_url=local_image, project_url=project),
            encoding="utf-8",
        )
    (site_dir / ".nojekyll").touch()
    return len(records)


def recipients(config: Config) -> list[str]:
    """Read the email recipients from the environment variable the config names."""
    raw = os.environ.get(config.delivery.email.to_env, "")
    seen: list[str] = []
    for part in raw.replace(";", ",").replace("\n", ",").split(","):
        address = part.strip()
        if address and address.lower() not in (s.lower() for s in seen):
            seen.append(address)
    return seen


def send_email(record: DigestRecord, config: Config, *, has_card: bool) -> list[str]:
    """Send the digest through Emalia, one message per recipient.

    Separate messages keep a mailing list private: nobody sees anyone else's
    address, and one bad address does not stop the rest.

    Args:
        record: The digest.
        config: The configuration; mailbox credentials come from the
            environment under `delivery.email.env_prefix`.
        has_card: Whether today's card was published, for the web link.

    Returns:
        The addresses the message was accepted for.

    Raises:
        DeliveryError: If the ``email`` extra is not installed, no recipient
            is configured, the mailbox cannot be reached, or every send failed.
    """
    settings = config.delivery.email
    to = recipients(config)
    if not to:
        raise DeliveryError(f"email delivery is enabled but {settings.to_env} is empty")
    try:
        from emalia.mail import MailClient
    except ImportError as exc:
        raise DeliveryError(
            "email delivery needs the 'email' extra: uv sync --extra email"
        ) from exc

    urls = public_urls(config, record, has_card=has_card)
    project = config.delivery.project_url
    subject = f"{settings.subject_prefix}{record.title}"
    body = to_markdown(record, project_url=project)
    html = to_email_html(record, web_url=urls.dated_page, project_url=project)

    sent: list[str] = []
    failures: list[str] = []
    try:
        with MailClient.from_env(settings.env_prefix) as client:
            for address in to:
                try:
                    sent += client.send(
                        to=[address], subject=subject, body=body, html_body=html, footer=""
                    )
                except Exception as exc:  # noqa: BLE001 - keep sending to the rest
                    failures.append(f"{address}: {type(exc).__name__}")
                    logger.warning("Email to one recipient failed: %s", type(exc).__name__)
    except Exception as exc:
        raise DeliveryError(f"email delivery failed: {type(exc).__name__}: {exc}") from exc
    if not sent:
        raise DeliveryError("email delivery failed for every recipient: " + "; ".join(failures))
    return sent
