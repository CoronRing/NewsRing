"""The public mailing list: the message that is published, and the signal that sends it.

Nothing here sends mail. What is worth pinning down is that the published
message carries an unsubscribe slot in both of its bodies, that the slot is
left intact by the HTML and Markdown renderers, and that the digest the author
receives directly does not grow an unsubscribe line it has no use for.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from newsring.config import Config
from newsring.deliver import BROADCAST_JSON, DeliveryError, build_site, send_broadcast
from newsring.models import DigestQuickHit, DigestRecord, DigestStory, RunStats
from newsring.render import UNSUBSCRIBE_PLACEHOLDER, to_broadcast_json, to_email_html
from tests.conftest import make_item

UNSUBSCRIBE = "https://example.test/news/api/unsubscribe?token=abc"


@pytest.fixture
def record() -> DigestRecord:
    """A small but complete digest: a story, a quick hit, and real stats."""
    return DigestRecord(
        date="2026-11-16",
        generated_at=datetime(2026, 11, 16, 9, 0, tzinfo=UTC),
        title="A quiet Sunday in AI",
        intro="Two things happened, and one of them matters.",
        stories=[
            DigestStory(
                headline="A model shipped",
                summary="It is **faster** than the last one.",
                why_it_matters="Cheaper inference moves what is worth building.",
                item=make_item("https://a.example/model", title="A model shipped"),
            )
        ],
        quick_hits=[
            DigestQuickHit(line="A library cut a release.", item=make_item("https://b.example/rel"))
        ],
        sign_off="See you tomorrow.",
        stats=RunStats(
            window_start=datetime(2026, 11, 13, 9, 0, tzinfo=UTC),
            candidates=40,
            triaged=40,
            enriched=1,
            headline_candidates=40,
            model="gemini/gemini-3.8-flash",
            seconds=90.0,
        ),
    )


# -- The published message ------------------------------------------------------------


def test_broadcast_carries_the_unsubscribe_slot_in_both_bodies(record: DigestRecord) -> None:
    payload = to_broadcast_json(record, subject="NewsRing: A quiet Sunday in AI")

    assert payload["version"] == 1
    assert payload["date"] == record.date
    assert payload["subject"] == "NewsRing: A quiet Sunday in AI"
    assert payload["unsubscribe_placeholder"] == UNSUBSCRIBE_PLACEHOLDER
    # Both bodies, because a reader whose client shows the plain-text part must
    # be able to leave without replying to a no-reply address.
    assert UNSUBSCRIBE_PLACEHOLDER in payload["html"]
    assert UNSUBSCRIBE_PLACEHOLDER in payload["text"]


def test_the_slot_survives_escaping_and_substitutes_cleanly(record: DigestRecord) -> None:
    """The whole scheme rests on the placeholder reaching the sender unaltered."""
    payload = to_broadcast_json(record, subject="s")
    html = payload["html"].replace(UNSUBSCRIBE_PLACEHOLDER, UNSUBSCRIBE)

    assert UNSUBSCRIBE in html
    assert "{{" not in html
    assert "%7B%7B" not in html  # not URL-encoded on its way through the renderer


def test_the_message_is_json_serializable(record: DigestRecord) -> None:
    """It is published as a file, so anything unserializable fails the run."""
    assert json.loads(json.dumps(to_broadcast_json(record, subject="s")))["date"] == record.date


def test_a_direct_digest_has_no_unsubscribe_line(record: DigestRecord) -> None:
    """The author did not subscribe to their own digest and cannot leave it."""
    assert "Unsubscribe" not in to_email_html(record)
    assert "Unsubscribe" in to_email_html(record, unsubscribe_url=UNSUBSCRIBE)


def test_build_site_publishes_the_message(
    record: DigestRecord, config: Config, tmp_path: Path
) -> None:
    archive = tmp_path / "news"
    archive.mkdir()
    (archive / f"{record.date}.json").write_text(record.model_dump_json(), encoding="utf-8")
    site = tmp_path / "site"

    build_site(archive, site, config)

    published = json.loads((site / BROADCAST_JSON).read_text(encoding="utf-8"))
    assert published["date"] == record.date
    assert published["subject"].startswith(config.delivery.email.subject_prefix)


# -- The signal that sends it ---------------------------------------------------------


def test_broadcast_needs_an_endpoint_and_a_token(
    record: DigestRecord, config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(config.delivery.broadcast.url_env, raising=False)
    monkeypatch.delenv(config.delivery.broadcast.token_env, raising=False)

    with pytest.raises(DeliveryError, match=config.delivery.broadcast.url_env):
        send_broadcast(record, config)

    monkeypatch.setenv(config.delivery.broadcast.url_env, "https://example.test/news/api/broadcast")
    with pytest.raises(DeliveryError, match=config.delivery.broadcast.token_env):
        send_broadcast(record, config)


def test_broadcast_sends_the_date_and_the_token(
    record: DigestRecord, config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"sent": 3, "skipped": 1, "failed": 0})

    monkeypatch.setenv(config.delivery.broadcast.url_env, "https://example.test/news/api/broadcast")
    monkeypatch.setenv(config.delivery.broadcast.token_env, "s3cret")
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, **kw: httpx.Client(transport=httpx.MockTransport(handler)).post(url, **kw),
    )

    result = send_broadcast(record, config)

    assert seen["auth"] == "Bearer s3cret"
    assert seen["body"] == {"date": record.date}
    assert result == {"sent": 3, "skipped": 1, "failed": 0}


def test_a_refusal_is_reported_without_the_body(
    record: DigestRecord, config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A service that quotes the request back must not land in a public CI log."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "bad token s3cret"})

    monkeypatch.setenv(config.delivery.broadcast.url_env, "https://example.test/news/api/broadcast")
    monkeypatch.setenv(config.delivery.broadcast.token_env, "s3cret")
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, **kw: httpx.Client(transport=httpx.MockTransport(handler)).post(url, **kw),
    )

    with pytest.raises(DeliveryError) as excinfo:
        send_broadcast(record, config)

    assert "401" in str(excinfo.value)
    assert "s3cret" not in str(excinfo.value)
