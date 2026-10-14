# Railtracks feedback

Notes gathered while building NewsRing against `railtracks` 1.5.7 from PyPI, cross-checked against the source at tag `v1.5.7`. NewsRing is a small daily pipeline: a `Flow` whose entry point is a function node that calls three structured-output agents through `rt.call` and `rt.call_batch`. It is run once a day from a CLI or a CI job, so start-up time and process-wide state matter more than they would in a long-lived server.

Ordered roughly by how much each one cost. None of them blocked the build. Severity is how badly it would bite a typical user, not how hard it is to fix.

The earlier [Emalia feedback](https://github.com/CoronRing/GS-Emalia/blob/main/RT_FEEDBACK.md) covered `MaxCalls` scoping, `Flow.connect()` concurrency, closure-built tools and import time. Where this project hit the same thing, it is noted briefly rather than repeated.

---

## 1. The docs say tools and structured output can share one agent; the code refuses

**Severity: high. The docs describe a feature that raises.**

`docs/documentation/agent_design/structured_extraction.md`, section "Structured + Tool Calling", offers two options. Option 2, "Abstracted Separation", says:

> Railtracks automatically implements the steps above for you. Simply need provide the `output_schema` and `tool_nodes` parameter to the same `agent_node` definition.

`agent_node` rejects exactly that (`built_nodes/llm/node.py:178`, `_check_no_combined_tools_and_schema`) with a `NodeCreationError`, and its own docstring explains why. The snippet the docs section includes (`first_agent.py:first_agent_all`) is actually the manual two-agent version from option 1, so the prose and the code under it disagree on the same page. The agent-builder skill shipped in the package says the opposite of the docs page, correctly.

A reader who trusts the docs writes the combined form, gets an exception, and then has to work out which of three sources is right.

**Suggestion:** delete option 2 or rewrite it to say the combination is refused and why, and point at option 1. If automatic separation is planned, say so as future work.

---

## 2. Trace settings are process-wide environment variables only, and per-Flow control is deprecated

**Severity: high for anything that embeds railtracks in a larger program.**

`Flow(save_state=...)` emits `DeprecationWarning: ... Use the RAILTRACKS_DISABLE_EVENTS env var instead`. The trace directory is likewise only configurable through `RAILTRACKS_HOME`. So the supported way for a library or application to say "don't write traces for this flow" is to mutate `os.environ`, which:

- affects every other Flow in the process, including ones in unrelated libraries;
- has to happen before the session closes, at a distance from where the Flow is built;
- cannot be scoped in tests without monkeypatching the environment.

NewsRing ends up doing this in its CLI (`newsring.cli.configure_traces`), which is the right layer for it, but a library could not do it politely at all.

**Suggestion:** keep the environment variables as the global override, but keep a per-Flow argument (or a `Flow(trace=TraceConfig(...))`) as the normal path. Environment variables are a deployment concern; whether a particular flow records is a code concern.

---

## 3. Traces from a nested project land in the parent's `.railtracks/`

**Severity: medium. Silent, and mixes unrelated projects' data.**

`paths.resolve_railtracks_home()` walks up from the working directory and uses the first existing `.railtracks/` it finds. NewsRing lives inside a larger workspace that already has one, so its first run wrote its trace into the workspace's directory, next to other projects' sessions, with only an INFO log line showing the path. Nothing warned; the fallback warning only fires when *no* directory is found.

Walking up is reasonable for a monorepo, but the nearest project boundary (`pyproject.toml`, `.git`) is a better stopping point than the filesystem root.

**Suggestion:** stop the walk at the first directory containing `pyproject.toml` or `.git`, or warn when the resolved directory is above the project root.

---

## 4. No public way to read token usage or cost

**Severity: medium. Every paid, scheduled job wants this.**

railtracks records input tokens, output tokens, cost and latency for every call: they are in the saved trace and in the viz UI. But user code cannot reach them through any public API:

- `LLMResponse` has only `content` and `message_history`.
- `FlowConnection` has `message_histories()` but nothing for usage.
- `connection.session.info` and `payload()` are commented out of the docs as unstable.

NewsRing gets them from `Flow(payload_callback=...)`, which receives the trace dict, by walking `runs[].nodes[].details.internals.llm_details[]`. Two traps on the way: each node embeds its parent's details, so a recursive search for `total_cost` counts every call twice; and the shape is documented as unstable, so the parser must assume it can change.

A run of NewsRing costs about $0.006 with `gpt-6-luna` (six calls, 21k input tokens). That number is the first thing anyone deploying an agent on a schedule wants to see.

**Suggestion:** a `usage` property on `LLMResponse` (this call), and `FlowConnection.usage()` returning totals for the run, both as a small typed object.

---

## 5. Exceptions in `payload_callback` are swallowed without a log

**Severity: medium. Turns a bug into missing data.**

`_session.py`, in `Session.__exit__`:

```python
try:
    if self.executor_config.payload_callback is not None:
        self.executor_config.payload_callback(self.payload())
except Exception:
    # TODO: add logging here.
    pass
```

A callback with a `KeyError` produces no output at all. Given point 4, a payload callback is currently the only way to get usage out, so this is exactly where users will write fragile code.

**Suggestion:** log at WARNING with the traceback. The TODO already says so.

---

## 6. Agent types cannot be named without importing internals

**Severity: medium for typed codebases.**

`agent_node` has good overloads: given `output_schema=X` it returns `type[Node[_P, StructuredResponse[X]]]`. But:

- mypy cannot infer it at all: `Triage = rt.agent_node(...)` fails with `Need type annotation for "Triage"`, presumably because `_P` comes from a private default argument and has nothing to bind to.
- To write the annotation, you need `Node` and `StructuredResponse`, and neither is exported from any public module. NewsRing imports them from `railtracks.nodes.nodes` and `railtracks.built_nodes.llm.response` under `TYPE_CHECKING`.

So the overloads exist, but a strictly typed project cannot use them without reaching into private paths that may move.

**Suggestion:** export `Node`, `StringResponse`, `StructuredResponse` (and probably `LLMResponse`) from `railtracks` or `railtracks.types`, and consider a public alias such as `rt.AgentType[Output]`. Check `reveal_type(rt.agent_node(..., output_schema=X))` under mypy and pyright in CI.

---

## 7. Import time is still large

**Severity: medium for CLIs and CI.** Same finding as Emalia, re-measured on 1.5.7:

| | Time |
|---|---|
| First `import railtracks` in a fresh virtual environment (includes bytecode compilation) | 41 s |
| Warm `import railtracks` | 5.5 s |

In CI every run is a cold start. NewsRing imports railtracks lazily inside the commands that need it, so `newsring --help` and `newsring sources` stay instant.

---

## 8. Free-tier failover needs a custom model class

**Severity: high for anyone running on free tiers, which is most hobby and student users.**

NewsRing moved to Gemini's free tier with two API keys and wanted the obvious behaviour: when one key is rate limited, use the next; when a model is overloaded, fall back to another. Four things got in the way.

**a. Middleware cannot change the model or key.** `ModelInvoker.invoke` resolves the `llm` factory once, then runs the middleware chain around a closure bound to that model. A `@wrap_llm` middleware can retry the call, but every retry goes to the same client with the same key. The docs present the factory form of `llm` as "a no-arg factory resolved fresh on every model call", which suggests rotation would work; it resolves per *call*, not per *attempt*.

The working answer was a `ModelBase` subclass (`newsring.llm.FailoverLLM`) that holds one client per model and key and implements the six abstract call methods by delegation. It works well and is transparent to agents and `call_batch`, but nothing in the docs suggests subclassing `ModelBase` is a supported extension point.

**b. A 503 is not a provider error.** A 429 becomes `ProviderRateLimitError`, but Gemini's "model is currently experiencing high demand" (503) arrives as a generic `ModelError: Structured LLM call failed`, the same type as a schema or prompt bug. The only way to tell them apart is to walk `__cause__` down to the litellm exception and read `status_code`. Gemini returns 503 often enough at peak hours that this is a normal condition, not an edge case.

**c. The retry policy retries rate limits on the same key, and its error set cannot be changed.** `RetryApproach.call_with_retry` takes a `retry_on` argument, but the provider wrapper calls it without one, so from a model's `retry_approach` you always get the default set, which includes `RateLimitError`. With one key that is right; with several it burns the backoff on a key that will not recover for a minute.

**d. Model names must be in litellm's catalog.** `GeminiLLM("gemini-4-argon")` raises `ModelNotFoundError` before any request, because `_pre_init_provider_check` strips the provider prefix and looks the bare name up in the installed litellm's catalog. Google serves the model; litellm simply does not know it yet. There is no opt-out, so a model released after your litellm pin is unusable through its own provider class. NewsRing falls back to Gemini's OpenAI-compatible endpoint through `OpenAICompatibleProvider`, which takes any name.

**Suggestions:**

1. A first-class failover model: `rt.llm.Failover([model_a, model_b, ...], on=("rate_limit", "unavailable"))`, or `api_keys=[...]` on provider classes.
2. Map 5xx to a `ProviderUnavailableError` alongside the existing three provider errors.
3. Expose `retry_on` on `RetryApproach` construction.
4. Make the catalog check a warning, or add `skip_model_check=True`.

---

## 9. Small things

- **`rt.enable_logging("NONE")` crashes.** `"NONE"` is one of the documented values in the `level` type (`Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL', 'NONE']`), but it is passed straight to `logging.Logger.setLevel`, which raises `ValueError: Unknown level: 'NONE'`.

- **`call_batch` docstring example uses the wrong name.** It shows `results = await batch(NodeA, ...)`; the function is `rt.call_batch`.
- **`call_batch` has no return annotation.** Its parameters are typed generically over the node's output, but the function returns `asyncio.gather(...)` unannotated (with the comment "this is big typing disaster"), so the results are `Any`. With `return_exceptions=True`, the default, each element may also be an exception, and nothing stops code calling `.structured` on one. Annotating it as `list[_TOutput | BaseException]` (and `list[_TOutput]` under an overload for `return_exceptions=False`) would let the type checker catch both.
- **Log lines for concurrent nodes looked incomplete.** With four triage batches started at once by `call_batch`, the INFO log showed two `CREATED NewsRing Triage` lines and four `DONE` lines. The results were all correct, so this is probably a logging quirk, but it makes a run log harder to trust.
- **Docs pages are hard to read from source.** Most examples are `--8<--` snippet includes, so reading the Markdown in a checkout (or in an agent's context) shows include directives instead of code. Generated `llms.txt` helps; linking it from the README would help more.
- **`rt.enable_logging` defaults to INFO with timestamps relative to process start.** Good for debugging, noisy for a CLI. NewsRing sets WARNING unless `--verbose`.

---

## What worked well

- **Structured output was reliable.** Across four live runs (12 model calls over all three agents) with `gpt-6-luna`, every response validated against its Pydantic schema. The saved traces for three of those runs show exactly one model call per agent node, so nothing was retried behind the scenes.
- **A function node taking a dataclass just worked.** `produce_digest(request: RunRequest)` with a frozen dataclass holding a Pydantic config, used as a Flow entry point, needed nothing special. The docs only show string inputs, so this was a pleasant surprise.
- **`rt.call_batch` made the triage fan-out a one-liner**, ran the batches concurrently, and returned exceptions in place instead of failing the whole batch, which is the right default for a best-effort step.
- **`.structured` on the response** made reading typed output direct.
- **Provider classes are consistent.** OpenAI, Anthropic, Gemini and OpenAI-compatible all take the same constructor arguments, so swapping provider is a config change. Ollama and Azure differ, but in documented ways.
- **The saved trace is genuinely useful.** Per-call tokens, cost and latency were all there, which is how the usage numbers above were found.
