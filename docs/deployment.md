# Deployment

NewsRing needs somewhere to run once a day, somewhere to keep the archive between runs, and somewhere to send the result. Two setups cover that for free apart from model calls, and Gemini's free tier makes those free too.

| | GitHub Actions (recommended) | Always-on host with cron |
|---|---|---|
| Server | None | Any Linux box with a Chromium-based browser for the card |
| Schedule | `.github/workflows/daily.yml` | A cron line or systemd timer |
| Archive (state) | `news/` and `news_today.md`, committed back by the workflow | A directory on disk |
| Site | GitHub Pages at `https://<you>.github.io/NewsRing/` | Any static file server |
| Cost | Free for a public repository | Free on the Oracle free tier |

## GitHub Actions

`.github/workflows/daily.yml` runs at 09:00 Pacific, using the schedule's `timezone` field so daylight saving is handled by GitHub. It has three jobs:

1. **digest**: produces the digest and the top stories card, commits `news/` and `news_today.md` to `main`, and builds the site. It never sees the mail credentials. If a whole attempt fails (for example, every Gemini model overloaded for several minutes), it waits ten minutes and tries again, up to three attempts.
2. **deploy**: publishes the site to GitHub Pages.
3. **email**: sends the digest, after deploy, so the "read on the web" link in the email already works. It never sees the model keys.

It can also be run by hand from the Actions tab, with an optional window override and a switch to skip email.

### One-time setup

1. Create the repository and push to it.
2. **Settings → Pages → Source: GitHub Actions.** A user site with no custom domain (`<you>.github.io`) serves the project at `https://<you>.github.io/NewsRing/` without touching the user site's repository.
3. **Settings → Secrets and variables → Actions**, add:

   | Secret | Used by | Contents |
   |---|---|---|
   | `CHAT_GEMINI_API_KEYS` | digest | One Gemini key, or several as `key1,key2` or `[key1, key2]`. Use the variable your `[llm] api_key_env` names. |
   | `NEWSRING_EMAIL_TO` | email | Recipients, comma separated. A secret so a public repository does not publish its readers' addresses. |
   | `EMALIA_ADDRESS` | email | The sending mailbox. |
   | `EMALIA_PASSWORD` | email | That mailbox's app password. |

   and optionally the variable `EMALIA_PROVIDER` (defaults to `gmail`).
4. Run the workflow once by hand to check it.

### Notes

- **Scheduled runs are not exact.** GitHub queues `schedule` events. They commonly start 5 to 30 minutes late, and the first scheduled run of this workflow started 4.5 hours late. A late run loses no news, since every run reads a fixed 72 hours.
- **Schedules pause on inactive repositories.** GitHub disables scheduled workflows in a public repository after 60 days without activity. The daily commit should keep the repository active; if the schedule is ever disabled, re-enable it from the Actions tab.
- **The bot's commits do not trigger CI.** Pushes made with the workflow's own token never start other workflows.
- **Logs are public** on a public repository. NewsRing logs model and key *numbers* when failing over, and the number of email recipients, never keys or addresses.
- **Traces are off in CI** (`RAILTRACKS_DISABLE_EVENTS=true`), since the runner is discarded after each run.

## Always-on host

On a host with `uv` and a Chromium-based browser:

```bash
git clone <repo> newsring && cd newsring
uv sync --frozen --extra email
cp /path/to/.env .env      # CHAT_GEMINI_API_KEYS, NEWSRING_EMAIL_TO, EMALIA_* …
uv run newsring run --dry-run --no-email   # check it works without writing anything
```

Then schedule it. With cron, at 09:00 local time:

```cron
0 9 * * * cd /home/ubuntu/newsring && /home/ubuntu/.local/bin/uv run newsring run >> .log/cron.log 2>&1
```

Serve `site/` with any static file server, or commit and push to let the Pages workflow publish it. The `news/` directory is the only state: back it up or commit it, and a rebuilt host continues where the old one stopped.

## Showing today's news elsewhere

Everything under the site has a fixed URL for "today", so other pages link once and never update:

- **An image**, for a GitHub profile README or any Markdown: `https://<you>.github.io/NewsRing/today.png`, linked to `today.html`.
- **A page on another site** on the same `github.io` origin: fetch `/NewsRing/news_today.json` when the page is viewed and render it. The author's site does this for its "News Today" post, so that post never needs a rebuild.
- **A Markdown file in the repository**: `news_today.md` at the repository root.

GitHub Pages serves files with a ten-minute cache, so a new card can take that long to appear.
