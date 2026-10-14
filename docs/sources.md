# Sources

Every source in the shipped `newsring.toml` is free, needs no account, and was checked with `newsring sources` on 2026-10-13. Of the 37 URLs in the starting list, 30 worked as given, five needed a different URL, one is blocked, and one has no feed at all. Two Google blogs were added later, so 35 sources are enabled.

## Status of the starting list

| Source | Status | What changed |
|---|---|---|
| Hacker News (Algolia) | Works | Added `numericFilters=points>50` and `hitsPerPage=50`, applied server side. |
| Hacker News front page RSS | Works | |
| HF Daily Papers | Works | Dated by when a paper reached the daily list, scored by upvotes. |
| HF Trending Models | **Fixed** | `sort=trending` returns HTTP 400. The parameter is `sort=trendingScore`. |
| Hugging Face Blog | Works | The feed holds every post ever (876); the time window does the filtering. |
| Lobsters AI tag | Works | |
| OpenAI News | Works | Also holds the full history (1,287 items). |
| Google DeepMind | **Fixed** | `/blog/feed/basic/` redirects to `/blog/rss.xml`; the config uses the target directly. |
| Google Research | Works | |
| Google AI Blog, Google Gemini Blog | **Added** | Where Google announces models such as Gemini 4 Argon. Both old `blog.google/...` paths redirect to new ones; the config uses the targets. |
| Meta AI | **Mirror** | `ai.meta.com/blog/rss/` returns 404. Uses the community mirror below. |
| Anthropic | **Mirror** | Anthropic publishes no feed (`/news/rss` returns 404). Uses the community mirror, split into News and Research. |
| Mistral AI | **Mirror** | `mistral.ai/news/index.xml` returns 404. Community mirror. |
| Microsoft Research | Works | |
| NVIDIA Developer | Works | |
| AWS Machine Learning | Works | |
| Cloudflare AI | Works | |
| PyTorch | **Fixed** | `/feed.xml` returns 404; the feed is `/blog/feed/`. The host (Pantheon) also refuses httpx with a 403 whatever the headers, so NewsRing retries any 403 once through the standard library, which it accepts. |
| GitHub releases (6) | Works | llama.cpp moved from `ggerganov/` to `ggml-org/` (the old URL redirects). llama.cpp tags a build several times a day, so it is capped at two items. |
| arXiv cs.AI, cs.CL, cs.LG RSS | **Replaced, off** | `rss.arxiv.org` returned empty feeds when probed. The export API works and is configured as one combined query, but disabled: these categories get several hundred papers a day with no quality signal, so the newest 100 are an arbitrary slice. HF Daily Papers is the upvoted view of the same stream. |
| BAIR Blog | Works | Posts rarely (last on 2026-07-29). |
| Stanford HAI | **No feed** | `/news/rss.xml` serves an HTML page. Left out. |
| Simon Willison | Works | |
| Lilian Weng | Works | The feed contains a pre-1970 date, which crashed date parsing on Windows until the parser stopped going through timestamps. |
| Sebastian Raschka | Works | |
| Eugene Yan | Works | Posts rarely. |
| Chip Huyen | Works | Last post January 2025; kept because it costs nothing. |
| Ars Technica | Works | |
| The Verge AI | Works | |
| VentureBeat AI | **Blocked, off** | HTTP 429 to every non-browser client, including with a browser User-Agent. |
| MIT Technology Review AI | Works | |

## The community mirror

Anthropic, Meta and Mistral come from [Olshansk/rss-feeds](https://github.com/Olshansk/rss-feeds), which scrapes each blog on a GitHub Actions schedule and commits the result as RSS. It was current when checked (Anthropic Research updated the day before), but it is a third party: if it stops, those sources go quiet. The run report at the bottom of each digest lists every source that failed, and `newsring sources` shows each source's newest item, which is how a stale mirror would show up.

## Adding a source

1. Find a feed URL. Most blogs have one at `/feed`, `/rss`, `/atom.xml` or `/index.xml`; any GitHub repository has `/releases.atom`.
2. Add a `[[sources]]` table with a `name`, `url`, a `max_items` cap and some `tags`.
3. Run `newsring sources` and check it reports items and a recent date.

A source that serves HTML instead of a feed is reported as a failure ("no RSS or Atom document found") rather than as a quiet source with zero items.
