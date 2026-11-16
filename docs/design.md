# NewsRing design

**Version 0.5.0** · November 2026

NewsRing is a personal news agent. Once a day it reads a list of free sources, picks the stories that match one reader's stated interests, and writes them up in the tone that reader asked for. The only product is the digest itself: a Markdown and HTML page, archived, optionally emailed, and optionally published as a static site.

It has two goals, and they carry equal weight:

1. **Exercise [railtracks](https://github.com/RailtownAI/railtracks) on a real, small, daily workload** and write down every gap and piece of friction found along the way, in [`RT_FEEDBACK.md`](../RT_FEEDBACK.md).
2. **Produce a useful daily digest** for its author, hosted for free apart from the model calls.

## Inputs

| Input | Where it lives | Notes |
|---|---|---|
| What the reader cares about | `[profile] interests`, `avoid` | Free text. This is the main ranking signal, so specifics beat categories. |
| How many stories | `[profile.count] min`, `max`, `quick_hits` | A range, not a number. The editor may go under `min` on a slow day and must say why. |
| Tone | `[profile.tone] detail`, `style`, `language` | `detail` is `brief`, `standard` or `deep`; `style` is free text such as "dry and lightly humorous". |
| Sources | `[[sources]]` | RSS, Atom, and three JSON APIs. See [sources.md](sources.md). |

Everything is in one TOML file, described field by field in [configuration.md](configuration.md).

## The central decision: collect first, then let the model choose

There are two broad ways to build this.

- **Agentic browsing.** Give an agent the reader's interests and tools such as `list_sources`, `fetch_source` and `read_article`, and let it decide what to read.
- **Collect, then select.** Fetch every source deterministically, normalize and deduplicate, then hand the model the whole candidate list at once and ask it to choose.

NewsRing uses **collect, then select**, with one agentic idea kept where it pays: the full text of a story is fetched only after it has been picked.

| | Agentic browsing | Collect, then select |
|---|---|---|
| Coverage | Whatever the agent chose to open. Silent gaps are likely and invisible. | Every source, every day. A failure is reported per source. |
| Comparison | Sees sources one at a time, so it cannot rank across them well. | Sees all candidates side by side, so it can rank and merge duplicate coverage. |
| Cost | Tokens spent on navigation and on pages it then discards. Grows with the number of sources. | Fetching is free. One editor call over compact candidate lines, one writer call. |
| Determinism | Two runs read different things. Hard to debug or evaluate. | The candidate list is reproducible and stored, so a bad pick can be traced to its input. |
| Links | The model handles URLs, so it can mangle or invent them. | The model only ever sees ids like `c17`. Links are joined back in code. |
| Where agency helps | Following up on a story, reading the article. | Enrichment does this, deterministically, for picked stories only. |

The cases where agentic browsing would win are open-ended ones, such as "find me anything about X, wherever it is". A digest over a fixed list of feeds is not that problem. An agentic mode is still worth building later, as a comparison that also exercises railtracks' tool-calling loop; see [Future work](#future-work).

## Pipeline

```mermaid
flowchart LR
    S[Sources] --> C[Collect]
    H[(Archive)] --> C
    C -->|"> threshold"| T[Triage agent]
    C -->|"≤ threshold"| E[Editor agent]
    T --> E
    E --> V[Validate ids]
    V --> N[Enrich]
    N --> W[Writer agent]
    W --> A[Assemble]
    A --> H
    A --> R[Render]
    R --> D1[Archive .md/.json]
    R --> D2[Static site]
    R --> D3[Email]
```

| Step | Kind | What it does |
|---|---|---|
| **Collect** | Code | Fetches every enabled source concurrently, parses it into `Item`s, drops items outside the time window or already sent, keeps each source's best `max_items`, merges items that share a canonical URL, and numbers the rest `c1`, `c2`, … newest first. |
| **Triage** | Agent, batched | Only when there are more than `triage_threshold` candidates. Scores batches of `triage_batch_size` 0 to 10 in parallel through `rt.call_batch` and keeps the best `triage_keep`. A failed batch keeps a neutral score rather than vanishing. |
| **Editor** | Agent | Sees every remaining candidate as two or three compact lines (title, source, signals, snippet) and returns the main picks in order, related ids to merge into each pick, quick hits, and an optional slow-day note. |
| **Validate** | Code | Drops unknown ids, uses each id once, enforces `count.max` and `quick_hits`. |
| **Enrich** | Code | Fetches the article for each pick whose feed carried little text, extracting the main text with trafilatura. Best effort. |
| **Writer** | Agent | Writes the title, intro, one write-up per pick, one line per quick hit, in the reader's voice, from the source material only. |
| **Assemble** | Code | Joins the prose with the items by id, in the editor's order. A story the writer skipped falls back to its title and snippet, so a link is never lost. |
| **Render and deliver** | Code | Markdown and HTML from the same record. Archive always; site and email when configured. |

### Why three agents and not one

The editor and the writer are separate because the writer needs the full article text and the editor must not: fetching full text for 200 candidates would be slow, costly, and mostly wasted. Splitting them also lets each prompt do one job, and lets the editor's choice be validated in code before any prose is written.

Triage exists only to keep the editor's prompt bounded. With the default sources the pool was 76 candidates for a 24-hour window and 111 for 72 hours, because the per-source caps bound it, and one editor call handles that comfortably. Triage switches on when someone adds a firehose such as raw arXiv. Forced on for testing (threshold 40, batches of 30), the four batches ran concurrently but each took about 40 seconds, so at this pool size triage costs time rather than saving it.

All the agents are structured-output `rt.agent_node`s with no tools. railtracks does not allow `tool_nodes` and `output_schema` on the same agent, and none of these steps needs a tool: everything they need is put in the prompt.

### Trust boundary

Model output is treated as untrusted structure. The model never sees a URL and never returns one; it returns candidate ids, which are checked against the pool. Prose from the model is HTML-escaped in titles and rendered through markdown-it with raw HTML disabled in bodies. Feed content is untrusted input to the model too: a feed item could carry a prompt injection, and the worst it can do is distort the prose or the ranking, because the model has no tools and cannot produce links.

## State and history

The archive directory (`news/`) is the only state. Each run writes `news/<date>.json` (the full `DigestRecord`) and `news/<date>.md`.

Every run reads the last `lookback_hours` (72) of news, not "everything since the last digest". A story from two days ago that has not been sent is still news to the reader, and a late or failed run loses nothing. Overlapping windows mean the same stories come round again, so repeats are prevented in two layers:

- **Exact repeats, in code.** The canonical URL of everything sent in the last `history_days` (stories, related coverage, quick hits) is dropped before any agent sees the candidates. The card keeps its own list, so it never repeats a card story either.
- **The same story from a different source, by the agents.** A URL check cannot catch a second article about yesterday's launch. The headlines of the last `recent_days` digests (and, for the Headliner, cards) are appended to the agent's input under "Already covered", and both prompts say not to repeat those stories unless there is a substantial new development, in which case the write-up must say what is new.

Measured on 2026-10-14 with a dry run dated the next day: with 29 recent headlines listed, the card and digest contained no story from the previous days, where before this change the card would have repeated the same launch for three days.

A record for the run's own date is ignored, so re-running a day regenerates it instead of treating its own stories as already sent.

This design means a deployment needs no database. A scheduled job persists state by committing one directory, and the archive is also a readable history of every digest.

### Canonical URLs

Two items are the same story when their canonical URLs match: scheme and `www.` dropped, host lower-cased, tracking parameters (`utm_*`, `ref`, `fbclid`, …) and fragments removed, trailing slash stripped. The same paper on arXiv and on Hugging Face Papers collapses to `arxiv:<id>`. Different articles about the same event are merged by the editor through `related_ids`, since that needs judgement.

## Railtracks usage

| Railtracks feature | Where |
|---|---|
| `rt.Flow` | `pipeline.build_flow`: the run's entry point, with `save_state` from config. |
| `@rt.function_node` | `pipeline.produce_digest`: the Flow's entry point, taking a `RunRequest` dataclass. |
| `rt.agent_node(output_schema=...)` | `agents.build_agents`: Triage, Editor, Writer. |
| `rt.call` | Editor and Writer steps. |
| `rt.call_batch` | Triage, one call per batch, run concurrently. |
| `response.structured` | Reading every agent's typed output. |
| `rt.llm.*` providers | `llm.build_llm`: provider and model come from config. |
| `rt.enable_logging` | CLI `--verbose`. |

Findings from building against these are in [`RT_FEEDBACK.md`](../RT_FEEDBACK.md).

## The top stories card

Alongside the personal digest, each run picks the few most exciting AI stories of the last `headlines.window_hours` (72 by default) for a general audience, and renders them as a 1200×630 image. The card is the shareable half of NewsRing: it is not personalized, it lives at one URL that never changes (`today.png`), and its right-hand panel tells whoever sees it how to get their own feed.

- **One fetch, two pools.** Collection runs once with the longer of the two windows. The digest's pool is cut to the run's window and drops stories already sent; the card's pool keeps the full 72 hours and ignores history, so a big story stays on the card while it is still the story. Pool ids use different letters (`c17`, `h17`) so they cannot be confused.
- **A fourth agent.** The Headliner picks the stories and writes a kicker, headline and one-sentence blurb for each. Its prompt ranks for a general technical audience, not the reader's profile.
- **Optional by design.** A failed Headliner call or a missing browser leaves the card out, logged, and the digest is delivered as usual.
- **Rendering.** The card is HTML and CSS in the author's brand (Archivo, Inter, JetBrains Mono, `#fffa00` on `#0a0a0b`), screenshotted at 2× by any Chromium-based browser in headless mode. GitHub runners have Chrome; Windows has Edge. No browser-automation library is needed.

The same stories appear as an "Across AI today" section at the top of the digest page and the email, so the email does not depend on an image that will show a different day when the email is reopened later.

## Model failover

On free tiers each API key has a small per-minute and per-day quota, and popular models return 503 "high demand" at peak hours. With several keys in `api_key_env` or any `fallback_models`, `newsring.llm.FailoverLLM` wraps one client per model and key:

- a **429** moves to the next candidate, usually the same model on the next key;
- a **5xx or timeout** skips the rest of that model's keys, since the model itself is overloaded;
- anything else is raised at once;
- when everything has failed, it waits and tries again, up to `rotation_rounds` passes, doubling the wait from `rotation_cooldown` each time;
- it stays on whichever candidate last worked, so the rest of the run does not hit the same limit.

It is a `ModelBase` subclass rather than middleware because railtracks resolves an agent's model once per call, before middleware runs, so middleware cannot change the key. 503s are recognised by walking the exception's cause chain for an HTTP status, because railtracks wraps them in a generic `ModelError`. Gemini model names that litellm's catalog does not know yet go through Gemini's OpenAI-compatible endpoint. All of this is written up in `RT_FEEDBACK.md`.

Each record's `stats.served_by` lists which model and key answered each call.

## Delivery and hosting

Every destination renders from the same `DigestRecord`.

- **Archive** (always): `news/<date>.json` and `news/<date>.md`, plus `news_today.md` at the repository root with the card on top.
- **Static site** (`delivery.site_dir`): one dated page per digest, rebuilt from the whole archive each run so template changes apply retroactively, plus fixed URLs for the newest digest: `today.html`, `today.png`, `news_today.json`, `news_today.md` and `broadcast_today.json`. Pages follow the reader's light or dark setting.
- **Email** (`delivery.email.enabled`): sent through [Emalia](https://github.com/CoronRing/GS-Emalia)'s `MailClient`, one message per recipient so a list never exposes its addresses. Email clients ignore CSS variables and most of `<style>`, so the email is a separate template with inline styles in a single light theme.
- **The public mailing list** (`delivery.broadcast.enabled`): a separate service, described below. A run does not send it; it tells the service that a digest is published.

### The public mailing list

Anyone can subscribe at [coronring.github.io/newsring](https://coronring.github.io/newsring) and get the same digest the author gets. Everyone on the list receives the identical message, so the pipeline above is untouched: one run, the same three model calls, one `DigestRecord`. What is added is one published file and one request.

**NewsRing publishes the message; it does not hold the list.** `build_site` writes `broadcast_today.json` beside the pages it already writes: the subject, an HTML body and a plain-text body, rendered once by the same `to_email_html` and `to_markdown` that produce the author's own copy. In place of a reader's unsubscribe link it carries `{{UNSUBSCRIBE_URL}}`, a placeholder chosen because neither HTML escaping nor Markdown rendering alters it.

**A separate service holds the list and does the sending.** It lives in the website repository (`coronring.github.io/news`), runs beside the two other services on that host, and keeps its subscribers in SQLite on a named volume. After the site is deployed, the workflow's `list` job calls `newsring broadcast`, which POSTs the digest's date and a bearer token to that service; the service fetches `broadcast_today.json`, substitutes each reader's own unsubscribe link, and sends one message per reader.

The split is the point:

| | Why not in this repository |
|---|---|
| The addresses | This repository is public and its CI logs are public. A subscriber's address is personal data and must never be in either. |
| The signup, confirmation and unsubscribe flow | They need an HTTP endpoint that answers at any hour. A scheduled workflow runs once a day. |
| The sending credentials for the list | Already on the host for the service that needs them; duplicating them into repository secrets widens the blast radius for nothing. |

What crosses the boundary is a date and a token, and what comes back is three counts. A run therefore costs nothing per subscriber, and a public CI log has nothing to leak.

**Re-running is harmless.** Each subscriber's row records the date of the last digest they were sent, and the service only sends to readers whose row does not already carry today's date. A dispatched re-run, or a retry after a half-finished send, reaches nobody twice. The workflow also sends the date it published, and the service refuses the whole send if the file it fetches is dated differently, which is what a lagging Pages deploy looks like.

**Confirmed opt-in, because anyone can type anyone's address.** The service stores nothing at signup: the address rides inside a signed link, and a row is only written when that link is clicked. So an abusive signup leaves no record anywhere, and this is also what makes unsubscribing a deletion rather than a flag. Every message carries a one-click unsubscribe, as a footer link and as the `List-Unsubscribe` headers mail clients act on themselves.

**The list is capped at 50.** Not a product decision but a sending one: the mailbox behind it is an ordinary consumer account with a daily cap in the hundreds and a reputation that a daily bulk send to strangers will spend. Raising the cap is a decision to move to a real sending service first, which needs a domain to verify. The service's own [README](https://github.com/CoronRing/coronring.github.io/blob/main/news/README.md) carries the rest.

### Showing today's news on another site

The author's website shows the newest digest as a blog post ("News Today") without being rebuilt daily. NewsRing's Pages site shares the `coronring.github.io` origin, so the post's component fetches `/NewsRing/news_today.json` when the page is viewed and renders it in the site's own styles. Plain-text fields are inserted as text; only the `*_html` fields, rendered by NewsRing from Markdown with raw HTML disabled, are inserted as HTML. The post's cover image is `today.png`, so the post's card on the home page changes daily too.

Fetching JSON was chosen over the alternatives:

- **Rebuilding the site daily** would couple the two repositories and redeploy a whole site for one page.
- **Fetching `news_today.md` from the repository** would need a Markdown renderer in the browser and the raw GitHub CDN's five-minute cache.
- **An iframe of `today.html`** would not inherit the site's typography or theme.

### Hosting

The recommended deployment is a scheduled GitHub Actions workflow, which is free for this workload, needs no server, commits `news/` back as state, and publishes the site to GitHub Pages. The workflow splits into a digest job (model keys only), a deploy job, and an email job (mail credentials only) that runs after deploy so the email's web link already works. Running on an always-on host with cron works the same way. Both are covered in [deployment.md](deployment.md).

## Costs

The only paid component is the model, and on Gemini's free tier it is free. A normal day makes three model calls (Headliner, Editor, Writer), or a few more when triage runs.

Measured on 2026-10-14 with `gemini-3.8-flash` and two free keys: three calls, 26,534 input and 7,699 output tokens. railtracks reported $0.049, which is litellm's list price; the free tier charged nothing. With `gpt-6-luna` on 2026-10-13, a two-call day cost $0.0033.

Wall-clock time is 1.5 to 4 minutes. Collection takes a few seconds; most of the rest is model latency, which on the free tier varies with load, and the Gemini run above spent extra time failing over from an overloaded model.

Each run's token totals and cost are stored in the archive record (`stats.usage`) and shown at the foot of the digest.

## Future work

Proposed, not built:

- **Agentic mode for comparison.** A tool-calling agent with `list_sources`, `fetch_source` and `read_article`, run on the same day's sources, to compare picks, cost and coverage against the pipeline. It would also exercise railtracks' tool loop, which the pipeline deliberately does not use.
- **Feedback loop.** Thumbs-up and thumbs-down links in the email or site that append to a small preference log the editor reads, so the profile sharpens over time.
- **Evaluation.** Score each day's picks against the profile with a judge model, using EvalRing, so prompt or model changes can be compared on stored candidate lists.
- **More source kinds.** Reddit JSON, Bluesky lists, YouTube channel feeds, and newsletters through an inbox read by Emalia.

### Opening the digest to other readers

Proposed on 2026-11-15, nothing built. Three stages, each useful on its own, and each one only worth building once the stage before it exists.

#### Stage 1: one list, one email — **built, November 2026**

A signup page, a confirmed opt-in, and the same digest to everyone on the list. See [The public mailing list](#the-public-mailing-list) above for how it works and where each piece lives. The signup is on the project page as its live demo, on the home deck's NewsRing frame as an action, and on its own page at `/newsring`.

One thing from the original sketch was not built and should not be: the fan-out does not happen in `recipients()`. Putting the list in this repository's environment would have put subscriber addresses in a public repository's secrets and in reach of a public CI log.

#### Stage 2: a preference page per reader

Every email carries a small **config** button at the foot. It opens a page belonging to that reader, reached by a signed link so no account or password is needed. The page holds their preferences, including a free-text description of what they want to read, in the same spirit as `[profile] interests` today. One subscriber, one profile.

This is the point where the single shared digest ends and a run has to produce more than one output, so the cost model changes: picks and prose become per-profile rather than per-day.

#### Stage 3: a sectioned digest with per-section controls

Instead of one ranked list, the digest is assembled from parts, and the preference page controls each part on its own. This supersedes the "per-topic sections" idea above.

| Section | What it is | What the reader controls |
|---|---|---|
| **Headlines** | The 3 or 4 biggest stories of the day, close to what the top stories card already picks. | On or off, and how many. |
| **Category news** | Stories grouped under the categories the reader chooses, such as LLMs, agents, hardware, policy, research. | Which categories, a weight per category, and how many stories in total. |
| **Suggested actions** | 2 or 3 things the reader could do today off the back of the news: try project X, test model Y, read paper Z. | On or off, and how many. |

**Category weights are relative, not quotas.** A reader who gives LLMs a 1 and agents a 2 is saying that agent news is worth twice as much to them when the editor is choosing between two comparable stories. It is not a demand that two thirds of the digest be agent stories, and on a day with no good agent story the weight must not force a weak one in. The weights, the chosen categories and the free-text description all go into the editor's prompt; the counts are enforced in code afterwards, the way `count.max` already is.

Suggested actions are the only part that needs something the pipeline does not do today. Turning a story into something doable needs both the day's picks and the reader's own description of what they are working on, so it is either an extra job for the writer or a fifth agent that runs after the picks are fixed.
