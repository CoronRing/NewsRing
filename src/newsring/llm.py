"""Build a railtracks model from the ``[llm]`` config section.

Kept separate so swapping provider or model is a config change. Any provider
railtracks supports can be added to `PROVIDERS` without touching the agents.

When the key variable holds several keys, or fallback models are configured,
the model is a `FailoverLLM`: one client per model and key, moving on when
the current one is rate limited or overloaded. That is the common shape of
free-tier access, where each key has a small per-minute and per-day quota and
popular models are intermittently unavailable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

import railtracks as rt
from pydantic import BaseModel
from railtracks.llm import MessageHistory, ModelProvider, Response, Tool

from newsring.config import LLMSettings

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

#: Provider name in the config to the railtracks model class. Constructors differ
#: slightly (Ollama takes a domain, Azure reads its endpoint from the environment),
#: which `build_llm` accounts for.
PROVIDERS: dict[str, Callable[..., rt.llm.ModelBase]] = {
    "openai": rt.llm.OpenAILLM,
    "anthropic": rt.llm.AnthropicLLM,
    "gemini": rt.llm.GeminiLLM,
    "openai_compatible": rt.llm.OpenAICompatibleProvider,
    "ollama": rt.llm.OllamaLLM,
    "azure": rt.llm.AzureAILLM,
}

#: Gemini's OpenAI-compatible endpoint. Used for Gemini models that railtracks
#: refuses because litellm's model catalog does not list them yet.
GEMINI_OPENAI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"

#: HTTP statuses meaning "this model is struggling right now", not "this request is wrong".
TRANSIENT_STATUSES = frozenset({500, 502, 503, 504})

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def parse_key_list(raw: str) -> list[str]:
    """Split an API-key variable into keys.

    Accepts a single key, comma or whitespace separated keys, a JSON array, or
    a bracketed unquoted list (``[AQ.aaa, AQ.bbb]``). The last shape is easy to
    mangle with a plain split into keys carrying a stray bracket, which the API
    then rejects as invalid rather than as malformed.

    Args:
        raw: The variable's value.

    Returns:
        Keys in declared order, blanks and duplicates removed.
    """
    text = raw.strip()
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            text = text[1:-1]
        else:
            if isinstance(parsed, list):
                text = ",".join(str(p) for p in parsed)
    keys: list[str] = []
    for part in text.replace(";", ",").replace("\n", ",").split(","):
        for token in part.split():
            key = token.strip().strip("'\"")
            if key and key not in keys:
                keys.append(key)
    return keys


def classify_failure(exc: BaseException) -> str | None:
    """Say whether an error is worth retrying elsewhere, and why.

    railtracks maps a 429 to `ProviderRateLimitError` but wraps a 503 ("model
    overloaded") in a generic `ModelError`, so the exception type alone cannot
    tell the two apart. The HTTP status survives on the provider exception
    further down the cause chain, so this walks the chain and reads it.

    Args:
        exc: Whatever the model call raised.

    Returns:
        ``"rate_limit"`` for a quota or rate limit, ``"transient"`` for a
        server-side failure or timeout, or None for anything else.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, rt.llm.ProviderRateLimitError):
            return "rate_limit"
        if isinstance(current, rt.llm.ProviderTimeoutError):
            return "transient"
        if isinstance(current, rt.llm.RetryError) and current.exception_list:
            return classify_failure(current.exception_list[-1])
        status = getattr(current, "status_code", None)
        if status == 429:
            return "rate_limit"
        if status in TRANSIENT_STATUSES:
            return "transient"
        current = current.__cause__ or current.__context__
    return None


def _one_line(exc: BaseException) -> str:
    text = _ANSI.sub("", " ".join(str(exc).split()))
    return f"{type(exc).__name__}: {text[:160]}"


@dataclass(frozen=True, slots=True)
class Candidate:
    """One way to make a call: a model name with one API key.

    Attributes:
        model: Model name, so an overloaded model can be skipped as a whole.
        label: For logs and run stats. Never contains the key.
        client: The configured railtracks model.
    """

    model: str
    label: str
    client: rt.llm.ModelBase


class FailoverLLM(rt.llm.ModelBase):
    """A model that fails over across API keys and fallback models.

    Candidates are tried in order: every key for the primary model, then
    every key for each fallback model. The wrapper stays on whichever
    candidate last worked, so once a key is rate limited the rest of the run
    starts from the next one instead of hitting the limit again.

    - A rate limit moves to the next candidate, usually the same model on the
      next key.
    - A transient server error (503 overloaded, 500, timeout) skips the rest
      of that model's keys, since another key for an overloaded model does
      not help.
    - Any other error is raised straight away.

    When every candidate has failed, it waits and tries them all again, up to
    `rounds` passes. The wait starts at `cooldown` seconds and doubles each
    time, since rate limits are mostly per minute and "high demand" spells
    on popular models can last several minutes.

    railtracks resolves an agent's model once per call, before model
    middleware runs, so middleware can retry a call but cannot change the key
    or model it uses. Failing over inside the model is what makes this
    transparent to the agents and to `rt.call_batch`.

    Args:
        candidates: Ordered ways to make a call. At least one.
        cooldown: Seconds to wait after every candidate has failed.
        rounds: Passes over all candidates before giving up.
        sleep: Injected for tests.
    """

    def __init__(
        self,
        candidates: Sequence[Candidate],
        *,
        cooldown: float = 30.0,
        rounds: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not candidates:
            raise ValueError("FailoverLLM needs at least one candidate")
        super().__init__()
        self._candidates = list(candidates)
        self._cooldown = cooldown
        self._rounds = max(1, rounds)
        self._sleep = sleep
        self._current = 0
        self._lock = threading.Lock()
        #: Label of the candidate that answered each successful call, in order.
        self.served: list[str] = []

    @property
    def current(self) -> Candidate:
        """The candidate the next call starts with."""
        return self._candidates[self._current]

    def model_name(self) -> str:
        return self.current.client.model_name()

    def model_provider(self) -> ModelProvider:
        return self.current.client.model_provider()

    @classmethod
    def model_gateway(cls) -> ModelProvider:
        # railtracks reads the gateway only inside its own provider classes;
        # instances of this wrapper report their current client's provider.
        raise NotImplementedError("FailoverLLM reports its current client's provider")

    def _order(self) -> list[int]:
        with self._lock:
            start = self._current
        total = len(self._candidates)
        return [(start + n) % total for n in range(total)]

    def _settle(self, index: int) -> None:
        with self._lock:
            self._current = index
            self.served.append(self._candidates[index].label)

    def _note(self, index: int, kind: str, exc: BaseException) -> str | None:
        """Log a failure and return the model to skip for the rest of this pass."""
        candidate = self._candidates[index]
        verdict = "rate limited" if kind == "rate_limit" else "unavailable"
        logger.warning(
            "%s %s, trying the next option (%s)", candidate.label, verdict, _one_line(exc)
        )
        return candidate.model if kind == "transient" else None

    def _wait(self, round_number: int) -> float:
        """Seconds to wait before pass `round_number` (1-based after the first pass)."""
        return self._cooldown * 2 ** (round_number - 1)

    def _run(self, call: Callable[[rt.llm.ModelBase], _T]) -> _T:
        last: BaseException | None = None
        for round_number in range(self._rounds):
            if round_number:
                wait = self._wait(round_number)
                logger.warning("Every model and key failed; waiting %.0fs", wait)
                self._sleep(wait)
            skip: str | None = None
            for index in self._order():
                candidate = self._candidates[index]
                if candidate.model == skip:
                    continue
                try:
                    result = call(candidate.client)
                except Exception as exc:
                    kind = classify_failure(exc)
                    if kind is None:
                        raise
                    last = exc
                    skip = self._note(index, kind, exc)
                    continue
                self._settle(index)
                return result
        assert last is not None
        raise last

    async def _arun(self, call: Callable[[rt.llm.ModelBase], Awaitable[_T]]) -> _T:
        last: BaseException | None = None
        for round_number in range(self._rounds):
            if round_number:
                wait = self._wait(round_number)
                logger.warning("Every model and key failed; waiting %.0fs", wait)
                await asyncio.sleep(wait)
            skip: str | None = None
            for index in self._order():
                candidate = self._candidates[index]
                if candidate.model == skip:
                    continue
                try:
                    result = await call(candidate.client)
                except Exception as exc:
                    kind = classify_failure(exc)
                    if kind is None:
                        raise
                    last = exc
                    skip = self._note(index, kind, exc)
                    continue
                self._settle(index)
                return result
        assert last is not None
        raise last

    def _chat(self, messages: MessageHistory) -> Response:
        return self._run(lambda m: m.chat(messages))

    def _structured(self, messages: MessageHistory, schema: type[BaseModel]) -> Response:
        return self._run(lambda m: m.structured(messages, schema))

    def _chat_with_tools(self, messages: MessageHistory, tools: list[Tool]) -> Response:
        return self._run(lambda m: m.chat_with_tools(messages, tools))

    async def _achat(self, messages: MessageHistory) -> Response:
        return await self._arun(lambda m: m.achat(messages))

    async def _astructured(self, messages: MessageHistory, schema: type[BaseModel]) -> Response:
        return await self._arun(lambda m: m.astructured(messages, schema))

    async def _achat_with_tools(self, messages: MessageHistory, tools: list[Tool]) -> Response:
        return await self._arun(lambda m: m.achat_with_tools(messages, tools))


def _keys(settings: LLMSettings) -> list[str]:
    if not settings.api_key_env:
        return []
    keys = parse_key_list(os.environ.get(settings.api_key_env, ""))
    if not keys:
        raise ValueError(f"llm.api_key_env names {settings.api_key_env}, which is not set")
    return keys


def _client(
    settings: LLMSettings, model: str, key: str | None, extra: dict[str, Any]
) -> rt.llm.ModelBase:
    """One railtracks client for one model and key."""
    provider = PROVIDERS[settings.provider]
    kwargs = dict(extra)
    if settings.provider == "ollama":
        if settings.api_base:
            kwargs.update(custom_domain=settings.api_base, domain="custom")
        return provider(model, **kwargs)
    if settings.provider == "azure":
        return provider(model, **kwargs)
    if settings.api_base:
        kwargs["api_base"] = settings.api_base
    if key is not None:
        kwargs["api_key"] = key
    try:
        return provider(model, **kwargs)
    except rt.llm.ModelNotFoundError:
        if settings.provider != "gemini" or settings.api_base:
            raise
    # railtracks checks Gemini model names against litellm's catalog, which
    # lags Google's releases. The OpenAI-compatible endpoint takes any name.
    logger.info("%s is not in litellm's catalog; using Gemini's OpenAI-compatible endpoint", model)
    kwargs["api_base"] = GEMINI_OPENAI_BASE
    if key is None:
        kwargs["api_key"] = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    return rt.llm.OpenAICompatibleProvider(model, **kwargs)


def build_llm(settings: LLMSettings, *, model: str | None = None) -> rt.llm.ModelBase:
    """Construct the model client.

    Args:
        settings: The ``[llm]`` section.
        model: Use this model name instead of `settings.model`, for example the
            triage model. Fallback models still apply after it.

    Returns:
        A railtracks model, ready to pass to `rt.agent_node`. A `FailoverLLM`
        when there is more than one key or any fallback model.

    Raises:
        ValueError: If the provider is unknown, or a required key is missing.
    """
    if settings.provider not in PROVIDERS:
        known = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"unknown llm.provider {settings.provider!r}; expected one of: {known}")
    if settings.provider == "openai_compatible" and not settings.api_base:
        raise ValueError("llm.provider 'openai_compatible' needs llm.api_base")

    extra: dict[str, Any] = {}
    if settings.temperature is not None:
        extra["temperature"] = settings.temperature
    if settings.reasoning_effort is not None:
        extra["reasoning_effort"] = settings.reasoning_effort

    models = [model or settings.model]
    models += [m for m in settings.fallback_models if m not in models]
    keys: list[str | None] = list(_keys(settings)) or [None]
    if len(models) == 1 and len(keys) == 1:
        return _client(settings, models[0], keys[0], extra)

    candidates = [
        Candidate(
            model=name,
            label=name if len(keys) == 1 else f"{name} (key {n})",
            client=_client(settings, name, key, extra),
        )
        for name in models
        for n, key in enumerate(keys, start=1)
    ]
    return FailoverLLM(
        candidates, cooldown=settings.rotation_cooldown, rounds=settings.rotation_rounds
    )


def describe_llm(settings: LLMSettings) -> str:
    """``provider/model`` for logs and the archive."""
    return f"{settings.provider}/{settings.model}"
