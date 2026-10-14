"""Command line interface: ``newsring run``, ``newsring sources``, ``newsring site``.

railtracks is imported inside the commands that need it. Importing it takes
tens of seconds on a cold start, which `--help` and `sources` should not pay.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import typer
from dotenv import find_dotenv, load_dotenv

from newsring import __version__
from newsring.config import Config, load_config

app = typer.Typer(
    name="newsring",
    help="A daily news agent: reads your sources, picks what matters to you, writes it up.",
    no_args_is_help=True,
    add_completion=False,
)

ConfigOption = typer.Option(
    Path("newsring.toml"), "--config", "-c", help="Configuration file.", exists=True, dir_okay=False
)


def _load(path: Path) -> Config:
    load_dotenv(find_dotenv(usecwd=True))
    return load_config(path)


def configure_traces(config: Config) -> None:
    """Point railtracks' run traces at this project, or turn them off.

    railtracks reads both settings from the environment only. Without
    `RAILTRACKS_HOME` it walks up from the working directory and writes into
    the first `.railtracks/` it finds, which for a project nested in another
    is the parent's. An explicit value already in the environment wins.
    """
    os.environ.setdefault("RAILTRACKS_HOME", str(config.base_dir))
    if not config.run.save_traces:
        os.environ["RAILTRACKS_DISABLE_EVENTS"] = "true"


@app.command()
def run(
    config_path: Path = ConfigOption,
    lookback_hours: int | None = typer.Option(
        None,
        "--lookback-hours",
        help="Read this many hours back, ignoring when the last digest ran.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print the digest as Markdown; write and send nothing."
    ),
    no_email: bool = typer.Option(False, "--no-email", help="Skip email even if it is enabled."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show railtracks logs."),
) -> None:
    """Produce today's digest and deliver it."""
    config = _load(config_path)
    configure_traces(config)

    import railtracks as rt

    from newsring.deliver import (
        DeliveryError,
        build_site,
        render_card,
        send_email,
        write_archive,
        write_latest_markdown,
    )
    from newsring.pipeline import NoCandidatesError, RunRequest, UsageCollector, build_flow
    from newsring.render import to_markdown

    rt.enable_logging("INFO" if verbose else "WARNING")
    # NewsRing's own warnings (a key rate limited, a source failing over) go to stderr.
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    now = datetime.now(UTC)
    request = RunRequest(
        config=config,
        today=now.astimezone(ZoneInfo(config.run.timezone)).date(),
        now=now,
        lookback_hours=lookback_hours,
    )
    try:
        usage = UsageCollector()
        record = build_flow(usage).invoke(request)
        record.stats.usage = usage.usage
    except NoCandidatesError as exc:
        typer.echo(f"Nothing to report: {exc}", err=True)
        raise typer.Exit(code=0) from exc

    if dry_run:
        typer.echo(to_markdown(record))
        return

    archive_dir = config.resolve(config.delivery.archive_dir)
    path = write_archive(record, archive_dir)
    typer.echo(f"Wrote {path}")

    has_card = False
    if config.delivery.site_dir is not None:
        site_dir = config.resolve(config.delivery.site_dir)
        has_card = render_card(record, site_dir, config)
        typer.echo("Rendered today's card" if has_card else "No card image this run")
        pages = build_site(archive_dir, site_dir, config)
        typer.echo(f"Rebuilt site: {pages} digests")
    if config.delivery.latest_markdown is not None:
        latest = config.resolve(config.delivery.latest_markdown)
        write_latest_markdown(record, latest, config, has_card=has_card)
        typer.echo(f"Wrote {latest.name}")

    if config.delivery.email.enabled and not no_email:
        if not record.stories and not record.quick_hits:
            typer.echo("No stories today; email skipped.")
            return
        try:
            sent = send_email(record, config, has_card=has_card)
        except DeliveryError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        # Counts only: CI logs of a public repository are public.
        typer.echo(f"Emailed {len(sent)} recipient(s)")


@app.command()
def sources(config_path: Path = ConfigOption) -> None:
    """Fetch every enabled source and report what each returned. No model calls."""
    config = _load(config_path)
    from newsring.sources import fetch_all

    results = asyncio.run(
        fetch_all(
            config.enabled_sources,
            timeout=config.run.fetch_timeout,
            concurrency=config.run.fetch_concurrency,
        )
    )
    width = max(len(s.name) for s, _, _ in results)
    failures = 0
    for spec, items, error in results:
        if error:
            failures += 1
            typer.echo(f"FAIL  {spec.name:<{width}}  {error}")
            continue
        dated = [i.published for i in items if i.published]
        newest = max(dated).strftime("%Y-%m-%d %H:%M") if dated else "undated"
        typer.echo(f"ok    {spec.name:<{width}}  {len(items):4d} items  newest {newest}")
    typer.echo(f"\n{len(results) - failures} of {len(results)} sources OK")
    if failures:
        raise typer.Exit(code=1)


@app.command()
def site(
    config_path: Path = ConfigOption,
    card: bool = typer.Option(True, "--card/--no-card", help="Re-render today's card image."),
) -> None:
    """Republish from the archive without running the agent: card, site and news_today.md."""
    config = _load(config_path)
    if config.delivery.site_dir is None:
        typer.echo("delivery.site_dir is not set", err=True)
        raise typer.Exit(code=1)
    from newsring.deliver import build_site, render_card, write_latest_markdown
    from newsring.history import list_records

    archive_dir = config.resolve(config.delivery.archive_dir)
    site_dir = config.resolve(config.delivery.site_dir)
    records = list_records(archive_dir)
    has_card = (site_dir / "today.png").exists()
    if records and card:
        has_card = render_card(records[0], site_dir, config)
    pages = build_site(archive_dir, site_dir, config)
    if records and config.delivery.latest_markdown is not None:
        write_latest_markdown(
            records[0], config.resolve(config.delivery.latest_markdown), config, has_card=has_card
        )
    typer.echo(f"Rebuilt site: {pages} digests" + (", with card" if has_card else ""))


@app.command()
def email(
    config_path: Path = ConfigOption,
    day: str | None = typer.Option(
        None, "--date", help="Digest date (YYYY-MM-DD). Defaults to the newest."
    ),
) -> None:
    """Email an archived digest to the configured recipients.

    The scheduled workflow sends email in its own step, after the site is
    deployed, so the email's web link works by the time anyone opens it.
    """
    config = _load(config_path)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    from newsring.deliver import DeliveryError, send_email
    from newsring.history import list_records

    records = list_records(config.resolve(config.delivery.archive_dir))
    record = next((r for r in records if day is None or r.date == day), None)
    if record is None:
        typer.echo(f"No archived digest{' for ' + day if day else ''}", err=True)
        raise typer.Exit(code=1)
    if not record.stories and not record.quick_hits:
        typer.echo(f"The {record.date} digest has no stories; email skipped.")
        return
    try:
        sent = send_email(record, config, has_card=bool(record.headlines))
    except DeliveryError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    # Counts only: CI logs of a public repository are public.
    typer.echo(f"Emailed the {record.date} digest to {len(sent)} recipient(s)")


@app.command()
def version() -> None:
    """Print the NewsRing version."""
    typer.echo(__version__)


def main() -> None:
    """Console script entry point."""
    if sys.platform == "win32":
        # Digests contain typographic characters the legacy console code page cannot encode.
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    app()
