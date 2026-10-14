# Contributing

Thanks for helping. Issues and pull requests are both welcome.

## Good first contributions

- **A new source kind.** Each kind is one parser in `src/newsring/sources.py` that turns a response body into `Item`s, plus a test with a captured sample. Reddit JSON, Bluesky lists and YouTube channel feeds are all wanted.
- **A source for the default list**, with a note on any quirk. Run `uv run newsring sources` first.
- **Tone presets** or prompt improvements, with a before-and-after digest.
- **Card designs.** The card is plain HTML and CSS in `src/newsring/card.py`.

## Setup

```bash
uv sync --extra email
uv run pytest -m "not network and not llm"
uv run ruff check src tests && uv run ruff format --check src tests
uv run mypy
```

`uv run newsring run --dry-run --no-email` runs the whole pipeline and prints the digest without writing or sending anything. It needs a model key; see `docs/configuration.md`.

## Guidelines

- Keep agents tool-free and keep URLs out of their inputs and outputs. That is the core safety property; see `docs/design.md`.
- Every public function is typed and has a docstring.
- A pull request that changes behaviour updates the docs in `docs/` in the same change.
