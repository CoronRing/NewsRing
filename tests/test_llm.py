"""Key parsing and failover, with fake clients. No network."""

from __future__ import annotations

from typing import Any

import pytest
import railtracks as rt

from newsring.llm import Candidate, FailoverLLM, classify_failure, parse_key_list


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("AQ.a", ["AQ.a"]),
        ("AQ.a,AQ.b", ["AQ.a", "AQ.b"]),
        ("[AQ.a, AQ.b]", ["AQ.a", "AQ.b"]),
        ('["AQ.a", "AQ.b", "AQ.a"]', ["AQ.a", "AQ.b"]),
        ("AQ.a\nAQ.b ; AQ.c", ["AQ.a", "AQ.b", "AQ.c"]),
        ("  ", []),
    ],
)
def test_parse_key_list(raw: str, expected: list[str]) -> None:
    assert parse_key_list(raw) == expected


class _StatusError(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")
        self.status_code = status


def _wrapped(inner: BaseException) -> Exception:
    """Mimic railtracks wrapping a provider error in a generic model error."""
    try:
        raise inner
    except BaseException as exc:
        try:
            raise RuntimeError("Structured LLM call failed") from exc
        except RuntimeError as outer:
            return outer


def test_classify_failure_reads_status_through_the_cause_chain() -> None:
    assert classify_failure(rt.llm.ProviderRateLimitError("429")) == "rate_limit"
    assert classify_failure(_wrapped(_StatusError(429))) == "rate_limit"
    assert classify_failure(_wrapped(_StatusError(503))) == "transient"
    assert classify_failure(_wrapped(_StatusError(400))) is None
    assert classify_failure(ValueError("schema mismatch")) is None


class FakeClient:
    """Stands in for a railtracks model: fails with queued errors, then answers."""

    def __init__(self, name: str, errors: list[BaseException] | None = None) -> None:
        self.name = name
        self.errors = list(errors or [])
        self.calls = 0

    def structured(self, messages: Any, schema: Any) -> str:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return f"answer from {self.name}"


def _llm(*clients: tuple[str, FakeClient], **kwargs: Any) -> tuple[FailoverLLM, list[float]]:
    sleeps: list[float] = []
    candidates = [Candidate(model=m, label=c.name, client=c) for m, c in clients]  # type: ignore[arg-type]
    return FailoverLLM(candidates, sleep=sleeps.append, **kwargs), sleeps


def test_rate_limit_moves_to_the_next_key_and_stays_there() -> None:
    key1 = FakeClient("k1", [rt.llm.ProviderRateLimitError("429")])
    key2 = FakeClient("k2")
    llm, sleeps = _llm(("flash", key1), ("flash", key2))

    assert llm.structured(None, None) == "answer from k2"  # type: ignore[arg-type]
    assert llm.structured(None, None) == "answer from k2"  # type: ignore[arg-type]
    assert (key1.calls, key2.calls) == (1, 2)  # the limited key is not retried
    assert llm.served == ["k2", "k2"] and sleeps == []


def test_overloaded_model_skips_its_other_keys() -> None:
    flash_k1 = FakeClient("flash k1", [_wrapped(_StatusError(503))])
    flash_k2 = FakeClient("flash k2")
    lite_k1 = FakeClient("lite k1")
    llm, _ = _llm(("flash", flash_k1), ("flash", flash_k2), ("lite", lite_k1))

    assert llm.structured(None, None) == "answer from lite k1"  # type: ignore[arg-type]
    assert flash_k2.calls == 0


def test_waits_and_retries_when_everything_fails_once() -> None:
    k1 = FakeClient("k1", [rt.llm.ProviderRateLimitError("429")])
    k2 = FakeClient("k2", [rt.llm.ProviderRateLimitError("429")])
    llm, sleeps = _llm(("flash", k1), ("flash", k2), cooldown=7, rounds=2)

    assert llm.structured(None, None) == "answer from k1"  # type: ignore[arg-type]
    assert sleeps == [7]


def test_gives_up_after_the_last_round() -> None:
    k1 = FakeClient("k1", [rt.llm.ProviderRateLimitError("429")] * 3)
    llm, sleeps = _llm(("flash", k1), cooldown=1, rounds=3)
    with pytest.raises(rt.llm.ProviderRateLimitError):
        llm.structured(None, None)  # type: ignore[arg-type]
    assert k1.calls == 3 and sleeps == [1, 2]  # the wait doubles


def test_other_errors_are_raised_immediately() -> None:
    k1 = FakeClient("k1", [ValueError("bad schema")])
    k2 = FakeClient("k2")
    llm, _ = _llm(("flash", k1), ("flash", k2))
    with pytest.raises(ValueError, match="bad schema"):
        llm.structured(None, None)  # type: ignore[arg-type]
    assert k2.calls == 0
