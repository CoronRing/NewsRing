# Configuration

NewsRing reads one TOML file, `newsring.toml` by default (`--config` to change it). Unknown keys are an error, so a typo fails loudly instead of being ignored. Relative paths resolve against the config file's directory, not the working directory.

Secrets never go in this file. API keys and mailbox credentials come from the environment, or from a `.env` file found by walking up from the working directory.

## `[profile]`

| Key | Default | Meaning |
|---|---|---|
| `name` | `""` | How the digest addresses you. Optional. |
| `interests` | required | Free text describing what you want. This is the main signal the editor ranks against, so be specific: "inference engines: vLLM, llama.cpp, speculative decoding" works better than "AI infrastructure". |
| `avoid` | `""` | Free text describing what to leave out. |

### `[profile.count]`

| Key | Default | Meaning |
|---|---|---|
| `min` | `5` | Fewest main stories on a normal day. On a slow day the editor may pick fewer and must say why in a note at the bottom; it is told never to pad. |
| `max` | `10` | Most main stories. Enforced in code. |
| `quick_hits` | `5` | Most one-line mentions after the main stories. `0` turns them off. |

### `[profile.tone]`

| Key | Default | Meaning |
|---|---|---|
| `detail` | `"standard"` | `brief` (one or two sentences per story), `standard` (a paragraph), or `deep` (two to four paragraphs with technical detail and caveats). |
| `style` | `"clear and direct, engineer to engineer"` | Free-text voice, for example `"dry and lightly humorous"` or `"like a patient teacher"`. |
| `language` | `"English"` | Language the digest is written in. Sources can be in any language. |

## `[llm]`

| Key | Default | Meaning |
|---|---|---|
| `provider` | `"openai"` | One of `openai`, `anthropic`, `gemini`, `openai_compatible`, `ollama`, `azure`. |
| `model` | `"gpt-6-luna"` | Model name as the provider spells it. |
| `api_base` | none | Endpoint override. Required for `openai_compatible` (for example OpenRouter at `https://openrouter.ai/api/v1`); for `ollama` it sets a custom host. |
| `api_key_env` | none | Read the key from this variable instead of the provider's default (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, …). |
| `temperature` | none | Omitted unless set, since some reasoning models reject it. |
| `reasoning_effort` | none | `none`, `minimal`, `low`, `medium` or `high`, for models that support it. |
| `triage_model` | none | A cheaper model for the triage pass. Same provider. Defaults to `model`. |
| `fallback_models` | `[]` | Models tried in order when `model` is overloaded or rate limited on every key. Same provider. |
| `rotation_cooldown` | `30` | Seconds to wait when every model and key has failed, before trying them all again. |
| `rotation_rounds` | `4` | Passes over every model and key before a call fails. The wait between passes starts at `rotation_cooldown` and doubles, so four passes wait 30, 60 and 120 seconds. |

### Several keys and fallback models

When `api_key_env` holds more than one key (comma separated, or a list like `[key1, key2]` or `["key1", "key2"]`), or `fallback_models` is set, every call goes through a failover wrapper. It tries the primary model on each key, then each fallback model on each key, and stays on whichever one last worked:

- **Rate limited (429):** move to the next key.
- **Overloaded or failing (500, 502, 503, 504, timeout):** skip the rest of that model's keys and move to the next model.
- **Any other error:** fail immediately; another key will not fix a bad request.

If everything fails, it waits and tries again, up to `rotation_rounds` passes, doubling the wait each time. Warnings name the model and key number, never the key.

For Gemini, a model name that litellm's catalog does not know yet (railtracks refuses those) is sent through Gemini's OpenAI-compatible endpoint instead, so new models work on release day.

## `[run]`

| Key | Default | Meaning |
|---|---|---|
| `lookback_hours` | `72` | Every run reads this many hours back. Overlap between days is safe because of the next two settings. |
| `history_days` | `14` | Stories sent in this many past days are never sent again, matched by URL. |
| `recent_days` | `3` | Headlines from this many past days are shown to the Editor and the Headliner as already covered, so the same story from a different source is skipped too, unless there is a substantial new development. |
| `timezone` | `"America/Los_Angeles"` | IANA zone that decides which date a digest is filed under. Match it to the schedule in the workflow. |
| `triage_threshold` | `150` | Above this many candidates, a triage pass scores them before the editor sees them. |
| `triage_batch_size` | `60` | Candidates per triage call. Batches run concurrently. |
| `triage_keep` | `80` | Candidates passed on to the editor after triage. |
| `enrich` | `true` | Fetch the full article for picked stories whose feed carried little text. |
| `enrich_max_chars` | `6000` | Cap on article text per story given to the writer. |
| `fetch_timeout` | `20` | Per-request HTTP timeout, seconds. |
| `fetch_concurrency` | `8` | Parallel HTTP requests. |
| `save_traces` | `true` | Let railtracks record each run under `.railtracks/` beside the config file. railtracks only accepts this setting process-wide, so the CLI sets `RAILTRACKS_HOME` (unless already set) and, when this is false, `RAILTRACKS_DISABLE_EVENTS`. |

The window is a fixed `lookback_hours`, not "since the last digest", so a late or failed run loses nothing. `newsring run --lookback-hours N` overrides it for one run.

## `[headlines]`

The shareable card: the day's most exciting AI stories for a general audience, not personalized. It reads a longer window than the digest and ignores history, so a big story stays on the card while it is still the story.

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | Pick the top stories at all. They also appear as "Across AI today" in the digest and email. |
| `count` | `3` | Stories on the card, 1 to 5. Three fit best. |
| `window_hours` | `72` | How far back to look. |
| `audience` | `"developers and technically minded people who follow AI"` | Who the card is for. Steers what counts as exciting. |
| `image` | `true` | Render the card as a PNG. Needs a Chromium-based browser (Chrome, Chromium or Edge); GitHub runners have one. Set `NEWSRING_BROWSER` to choose a binary. |

## `[delivery]`

| Key | Default | Meaning |
|---|---|---|
| `archive_dir` | `"news"` | Every digest is written here as `<date>.json` and `<date>.md`. This is also the history that prevents repeats, so keep it. |
| `latest_markdown` | none | When set, the newest digest is also written to this file (for example `news_today.md`), with the card image, so the repository always shows today's news at a fixed path. |
| `site_dir` | none | When set, a static site is rebuilt here after each run (see below). |
| `site_url` | `""` | Public URL the site is served from, ending in `/`. Used for links in email, the JSON feed and the Markdown. |
| `site_title` | `"NewsRing"` | Heading of the site index. |
| `project_url` | NewsRing's GitHub page | Where readers can get their own feed. Shown on the card, the site and in email. |

### What the site contains

Each digest has a dated page that never changes, `2026-10-13.html`. The newest digest is also published under fixed names, so other pages can link to "today" once:

| File | Contents |
|---|---|
| `today.html` | The newest digest's page. |
| `today.png` | The top stories card, 1200×630 rendered at 2×. |
| `news_today.json` | The newest digest as JSON, for another site to render when the page is viewed. Plain-text fields plus `*_html` twins rendered from Markdown with raw HTML disabled. |
| `news_today.md` | The newest digest as Markdown. |
| `index.html` | Today's card, a link to today's digest, and every past digest. |

On GitHub Pages a project site shares its user site's origin, so `https://<you>.github.io` can fetch `/<repo>/news_today.json` with no CORS setup.

### `[delivery.email]`

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `false` | Whether `newsring run` sends email. `newsring run --no-email` skips it for one run; `newsring email` sends the newest archived digest on demand. |
| `to_env` | `"NEWSRING_EMAIL_TO"` | Variable holding recipients, comma separated. Kept out of the file so the file can be committed and a public repository does not publish its readers' addresses. Each recipient gets a separate message. |
| `env_prefix` | `"EMALIA_"` | Prefix of the mailbox variables read by [Emalia](https://github.com/CoronRing/GS-Emalia). With `EMALIA_`, the standard `GOOGLE_APP_PASSWORD` alias also works. |
| `subject_prefix` | `"NewsRing: "` | Prepended to the digest title. |

Email needs the extra installed (`uv sync --extra email`) and Emalia's variables set. For a Gmail account with an app password:

```bash
NEWSRING_EMAIL_TO=you@example.com
EMALIA_ADDRESS=sender@gmail.com
EMALIA_PROVIDER=gmail
EMALIA_PASSWORD=<16-character app password>
```

Emalia also supports OAuth and Google service accounts; see its `docs/authentication.md`.

## `[[sources]]`

One table per source.

| Key | Default | Meaning |
|---|---|---|
| `name` | required | Display name. Must be unique. |
| `kind` | `"feed"` | `feed` (RSS or Atom, including GitHub `releases.atom` and the arXiv export API), `hn_algolia`, `hf_daily_papers`, or `hf_trending_models`. |
| `url` | required | The endpoint. |
| `max_items` | `20` | Most items kept from this source per run, after the time window. Ranked by score where the source has one (HN points, paper upvotes, trending score), newest otherwise. |
| `min_score` | none | Drop items scoring below this. Ignored for plain feeds, which have no score. |
| `tags` | `[]` | Labels shown to the editor next to each item, for example `lab` or `release`. |
| `enabled` | `true` | Set `false` to keep a source in the file without reading it. |
| `note` | `""` | Why the source is configured the way it is. Ignored at runtime. |

`newsring sources` fetches every enabled source and prints what each returned, without calling a model. Run it after editing this list. The shipped list and its quirks are in [sources.md](sources.md).
