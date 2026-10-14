# Security

## Reporting a vulnerability

Please report security issues privately through GitHub: **Security → Report a vulnerability** on this repository. Do not open a public issue. You should hear back within a week.

## What NewsRing handles, and how

- **API keys and mail credentials** are read from the environment only, never from `newsring.toml`, and never written to the archive, the site, or logs. In the scheduled workflow they are GitHub Actions secrets.
- **Email recipients** are read from an environment variable for the same reason, and each recipient gets a separate message, so a mailing list's addresses are never exposed to each other. The CLI prints how many recipients were emailed, never who, because Actions logs of a public repository are public.
- **Feed content is untrusted.** A feed item could carry a prompt injection. NewsRing's agents have no tools, never see or produce URLs (they return candidate ids, and links are joined back in code), and their prose is HTML-escaped or rendered from Markdown with raw HTML disabled. The worst a malicious item can do is distort the wording or ranking of one digest.
- **The JSON feed** (`news_today.json`) carries plain text plus `*_html` fields rendered with raw HTML disabled. Consumers should insert plain fields as text.

## If you fork this

Your fork's workflow uses your own secrets; forks never receive this repository's. Scheduled workflows stay disabled in a fork until you enable them.
