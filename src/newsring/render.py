"""Render a digest record as Markdown, a web page, an email, and a JSON feed.

Rendering is deterministic: the writer's prose goes in as text, and every link
comes from the item records. Model prose is escaped wherever it lands in HTML,
and summaries go through markdown-it with raw HTML disabled.

The web page and the email are separate on purpose. Email clients ignore CSS
variables, media queries and most of `<style>`, so the email uses inline
styles in a single light theme, while the web page follows the reader's
light or dark setting.
"""

from __future__ import annotations

from collections.abc import Sequence
from html import escape
from typing import Any
from urllib.parse import urlsplit

from markdown_it import MarkdownIt

from newsring.models import DigestHeadline, DigestRecord, DigestStory, SourceReport

#: Related coverage shown per story. A big launch can gather a dozen; three is plenty.
MAX_RELATED_LINKS = 3

_md = MarkdownIt("commonmark", {"html": False, "linkify": False}).disable("image")

_FONTS = (
    "https://fonts.googleapis.com/css2?family=Archivo:wght@600;800"
    "&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@500;700&display=swap"
)


def _host(url: str) -> str:
    """Link text for a URL: its host, so the label says where the link goes."""
    return urlsplit(url).netloc.removeprefix("www.") or url


def _health_line(reports: Sequence[SourceReport]) -> str:
    ok = sum(r.ok for r in reports)
    line = f"{ok} of {len(reports)} sources read"
    failed = [f"{r.name} ({r.error})" for r in reports if not r.ok]
    return line + (f"; failed: {', '.join(failed)}" if failed else "")


def stats_line(record: DigestRecord) -> str:
    """The run report shown at the foot of every digest, as plain text."""
    stats = record.stats
    line = (
        f"{_health_line(record.sources)}. {stats.candidates} candidates, "
        f"{stats.triaged} reviewed, {stats.model}, {stats.seconds:.0f}s"
    )
    if stats.usage is not None:
        line += f", {stats.usage.calls} model calls"
        if stats.usage.cost_usd is not None:
            line += f", ${stats.usage.cost_usd:.4f}"
    return line + "."


def _links(story: DigestStory) -> list[tuple[str, str]]:
    """``(label, url)`` pairs for a story: the source, its discussion, related coverage."""
    item = story.item
    links = [(_host(item.url), item.url)]
    if item.discussion_url:
        links.append(("discussion", item.discussion_url))
    links += [(_host(r.url), r.url) for r in story.related[:MAX_RELATED_LINKS]]
    return links


# -- Markdown ---------------------------------------------------------------------


def _md_link(text: str, url: str) -> str:
    return f"[{text.replace('[', '(').replace(']', ')')}]({url})"


def to_markdown(
    record: DigestRecord, *, image_url: str | None = None, project_url: str | None = None
) -> str:
    """Render a digest as Markdown, for the archive and the plain-text email body.

    Args:
        record: The digest.
        image_url: Today's card image, shown under the title. Only pass a URL
            that will keep showing this digest's card.
        project_url: Where readers can get their own feed, for the footer.

    Returns:
        A Markdown document.
    """
    lines = [f"# {record.title}", "", f"*{record.date} · {len(record.stories)} stories*", ""]
    if image_url:
        lines += [f"![Top AI stories for {record.date}]({image_url})", ""]
    lines += [record.intro, ""]
    if record.headlines:
        lines += ["## Across AI today", ""]
        lines += [
            f"- **{h.headline}** {h.blurb} ({_md_link(_host(h.item.url), h.item.url)})"
            for h in record.headlines
        ]
        lines.append("")
    for n, story in enumerate(record.stories, start=1):
        lines += [f"## {n}. {story.headline}", "", story.summary, ""]
        if story.why_it_matters:
            lines += [f"**Why it matters:** {story.why_it_matters}", ""]
        links = " · ".join(_md_link(label, url) for label, url in _links(story))
        lines += [f"{links} · via {story.item.source}", ""]
    if record.quick_hits:
        lines += ["## Quick hits", ""]
        lines += [
            f"- {hit.line} ({_md_link(_host(hit.item.url), hit.item.url)})"
            for hit in record.quick_hits
        ]
        lines.append("")
    if record.slow_day_note:
        lines += [f"*{record.slow_day_note}*", ""]
    if record.sign_off:
        lines += [record.sign_off, ""]
    lines += ["---", ""]
    if project_url:
        lines += [f"Written by [NewsRing]({project_url}). Get your own feed, in your own tone.", ""]
    lines += [f"<sub>{stats_line(record)}</sub>", ""]
    return "\n".join(lines)


# -- Web page -----------------------------------------------------------------------

_CSS = """
:root {
  --ground:#f2f2f2; --surface:#ffffff; --line:#d0d0d0; --text:#191919; --muted:#5c5c5c; --faint:#8a8a8a;
  --accent:#7a7500; --fill:#fffa00; --on-fill:#0a0a0b;
  --display: Archivo, Inter, system-ui, sans-serif; --sans: Inter, system-ui, -apple-system, 'Segoe UI', sans-serif;
  --mono: 'JetBrains Mono', ui-monospace, Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root { --ground:#0a0a0b; --surface:#151517; --line:#2a2a2f; --text:#f5f5f5; --muted:#a0a0a6; --faint:#6f6f76; --accent:#fffa00; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--ground); color:var(--text); font:16px/1.65 var(--sans); }
main { max-width: 760px; margin: 0 auto; padding: 28px 16px 64px; }
a { color: inherit; text-decoration-color: var(--fill); text-decoration-thickness: 2px; text-underline-offset: 3px; }
a:hover { color: var(--accent); }
.bar { display:flex; align-items:center; justify-content:space-between; gap:12px; font: 500 12px/1 var(--mono); letter-spacing:.12em; text-transform:uppercase; color:var(--muted); }
.brand { font: 800 20px/1 var(--display); letter-spacing:-.01em; text-transform:none; color:var(--text); text-decoration:none; }
.eyebrow { display:inline-block; margin-top:40px; background:var(--fill); color:var(--on-fill); font: 700 12px/1 var(--mono); letter-spacing:.12em; text-transform:uppercase; padding:6px 9px; }
h1 { font: 800 clamp(30px, 6vw, 46px)/1.08 var(--display); letter-spacing:-.02em; margin: 14px 0 0; }
h2 { font: 800 22px/1.2 var(--display); letter-spacing:-.01em; margin: 0 0 10px; }
h3 { font: 700 12px/1 var(--mono); letter-spacing:.14em; text-transform:uppercase; color:var(--muted); margin: 44px 0 14px; }
.intro { font-size: 18px; color: var(--muted); margin-top: 16px; }
.intro p { margin: 0; }
.card { display:block; margin-top: 28px; border: 1px solid var(--line); }
.card img { display:block; width:100%; height:auto; }
.top { list-style:none; padding:0; margin:0; border-top:1px solid var(--line); }
.top li { padding: 14px 0; border-bottom:1px solid var(--line); display:grid; grid-template-columns: 44px 1fr; }
.top .n { font: 700 20px/1.2 var(--mono); color: var(--accent); }
.top strong { font-family: var(--display); font-weight: 800; }
.top .src { font: 500 12px/1.4 var(--mono); color: var(--faint); }
article { background: var(--surface); border: 1px solid var(--line); padding: 22px 24px; margin: 16px 0; position: relative; }
article::before { content:""; position:absolute; left:-1px; top:-1px; bottom:-1px; width:4px; background: var(--fill); }
article p { margin: 0 0 12px; }
.why { font-size: 15px; color: var(--muted); }
.why strong { color: var(--text); }
.links { font: 500 12.5px/1.6 var(--mono); color: var(--faint); }
.hits { padding-left: 18px; }
.hits li { margin: 8px 0; }
.note { color: var(--muted); font-style: italic; }
.cta { margin-top: 48px; background: var(--fill); color: var(--on-fill); padding: 24px; display:flex; flex-wrap:wrap; gap: 14px 24px; align-items:center; justify-content:space-between; }
.cta strong { font: 800 22px/1.2 var(--display); display:block; }
.cta span { font-size: 15px; }
.cta a.button { background: var(--on-fill); color: var(--fill); text-decoration:none; font: 700 13px/1 var(--mono); padding: 12px 14px; white-space:nowrap; }
footer { color: var(--faint); font: 500 12px/1.6 var(--mono); margin-top: 28px; }
.index { list-style:none; padding:0; margin:0; border-top:1px solid var(--line); }
.index li { border-bottom:1px solid var(--line); padding: 14px 0; display:flex; gap:16px; align-items:baseline; }
.index .date { font: 500 13px/1 var(--mono); color: var(--faint); white-space:nowrap; }
.index a { font: 700 17px/1.35 var(--display); text-decoration:none; }
"""


def _a(text: str, url: str) -> str:
    return f'<a href="{escape(url, quote=True)}">{escape(text)}</a>'


def _page(title: str, body: str, *, description: str = "", image_url: str | None = None) -> str:
    meta = [
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="color-scheme" content="light dark">',
        f"<title>{escape(title)}</title>",
        f'<meta property="og:title" content="{escape(title, quote=True)}">',
    ]
    if description:
        meta.append(f'<meta name="description" content="{escape(description, quote=True)}">')
        meta.append(f'<meta property="og:description" content="{escape(description, quote=True)}">')
    if image_url:
        meta.append(f'<meta property="og:image" content="{escape(image_url, quote=True)}">')
        meta.append('<meta name="twitter:card" content="summary_large_image">')
    return (
        '<!doctype html>\n<html lang="en"><head>'
        + "".join(meta)
        + f'<link rel="stylesheet" href="{_FONTS}"><style>{_CSS}</style></head>'
        + f"<body><main>{body}</main></body></html>\n"
    )


def _cta(project_url: str) -> str:
    return (
        '<div class="cta"><div><strong>Want your own feed?</strong>'
        "<span>NewsRing picks the news you care about and writes it in the tone you like. "
        "No ads, no sponsors, open source.</span></div>"
        f'<a class="button" href="{escape(project_url, quote=True)}">Get NewsRing →</a></div>'
    )


def _top_stories_html(headlines: Sequence[DigestHeadline]) -> str:
    rows = [
        f'<li><span class="n">{n:02d}</span><div><strong>{escape(h.headline)}</strong> '
        f'{escape(h.blurb)}<div class="src">{_a(_host(h.item.url), h.item.url)}</div></div></li>'
        for n, h in enumerate(headlines, start=1)
    ]
    return f'<ol class="top">{"".join(rows)}</ol>'


def to_html(
    record: DigestRecord,
    *,
    index_href: str | None = None,
    image_url: str | None = None,
    share_image_url: str | None = None,
    project_url: str | None = None,
) -> str:
    """Render a digest as a standalone web page.

    Args:
        record: The digest.
        index_href: Link back to the archive index.
        image_url: The card image for this digest, shown under the intro.
            A relative URL keeps the page working before it is deployed.
        share_image_url: Absolute URL of the card for the social preview
            tags, which link unfurlers fetch from outside the site. Defaults
            to `image_url`.
        project_url: Where readers can get their own feed.

    Returns:
        A complete HTML document.
    """
    bar = (
        f'<div class="bar"><a class="brand" href="{escape(index_href or "#", quote=True)}">NewsRing</a>'
        f"<span>{escape(record.date)}</span></div>"
    )
    out = [
        bar,
        '<span class="eyebrow">News today</span>',
        f"<h1>{escape(record.title)}</h1>",
        f'<div class="intro">{_md.render(record.intro)}</div>',
    ]
    if image_url:
        out.append(
            f'<a class="card" href="#top"><img src="{escape(image_url, quote=True)}" alt="Top AI stories for {escape(record.date)}" width="1200" height="630"></a>'
        )
    if record.headlines:
        out += ['<h3 id="top">Across AI today</h3>', _top_stories_html(record.headlines)]
    if record.stories:
        out.append("<h3>Picked for you</h3>")
    for story in record.stories:
        out.append("<article>")
        out.append(f"<h2>{escape(story.headline)}</h2>")
        out.append(_md.render(story.summary))
        if story.why_it_matters:
            out.append(
                f'<p class="why"><strong>Why it matters:</strong> {escape(story.why_it_matters)}</p>'
            )
        links = " · ".join(_a(label, url) for label, url in _links(story))
        out.append(f'<div class="links">{links} · via {escape(story.item.source)}</div>')
        out.append("</article>")
    if record.quick_hits:
        out.append('<h3>Quick hits</h3><ul class="hits">')
        out += [
            f"<li>{escape(h.line)} ({_a(_host(h.item.url), h.item.url)})</li>"
            for h in record.quick_hits
        ]
        out.append("</ul>")
    if record.slow_day_note:
        out.append(f'<p class="note">{escape(record.slow_day_note)}</p>')
    if record.sign_off:
        out.append(f"<p>{escape(record.sign_off)}</p>")
    if project_url:
        out.append(_cta(project_url))
    out.append(f"<footer>{escape(stats_line(record))}</footer>")
    return _page(
        record.title,
        "\n".join(out),
        description=record.intro,
        image_url=share_image_url or image_url,
    )


def index_html(
    records: Sequence[DigestRecord],
    *,
    site_title: str,
    image_url: str | None = None,
    share_image_url: str | None = None,
    project_url: str | None = None,
) -> str:
    """Render the site's front page: today's card, then every digest, newest first.

    Args:
        records: Every digest.
        site_title: Page heading.
        image_url: Today's card, usually relative.
        share_image_url: Absolute URL of the card for social previews.
        project_url: Where readers can get their own feed.

    Returns:
        A complete HTML document.
    """
    newest = sorted(records, key=lambda r: r.date, reverse=True)
    out = [
        f'<div class="bar"><a class="brand" href="./">{escape(site_title)}</a><span>{len(records)} digests</span></div>',
        '<span class="eyebrow">AI news, picked and written for one reader</span>',
        f"<h1>{escape(newest[0].title) if newest else escape(site_title)}</h1>",
    ]
    if newest:
        out.append(f'<p class="intro">{escape(newest[0].intro)}</p>')
        if image_url:
            out.append(
                f'<a class="card" href="today.html"><img src="{escape(image_url, quote=True)}" alt="Top AI stories today" width="1200" height="630"></a>'
            )
        out.append('<p><a href="today.html">Read today\'s digest →</a></p>')
    if project_url:
        out.append(_cta(project_url))
    out.append("<h3>Every digest</h3>")
    out.append(
        '<ul class="index">'
        + "".join(
            f'<li><span class="date">{escape(r.date)}</span><a href="{escape(r.date)}.html">{escape(r.title)}</a></li>'
            for r in newest
        )
        + "</ul>"
    )
    return _page(
        site_title,
        "\n".join(out),
        description="A daily AI news digest written by NewsRing.",
        image_url=share_image_url or image_url,
    )


# -- Email --------------------------------------------------------------------------

_E = {
    "body": "margin:0;padding:0;background:#f2f2f2;",
    "wrap": "max-width:640px;margin:0 auto;padding:24px 16px;font-family:Inter,Segoe UI,Helvetica,Arial,sans-serif;color:#191919;font-size:16px;line-height:1.6;",
    "brand": "font-family:Archivo,Helvetica,Arial,sans-serif;font-weight:800;font-size:20px;color:#191919;text-decoration:none;",
    "date": "font-family:Consolas,Menlo,monospace;font-size:12px;letter-spacing:1px;text-transform:uppercase;color:#5c5c5c;",
    "eyebrow": "display:inline-block;background:#fffa00;color:#0a0a0b;font-family:Consolas,Menlo,monospace;font-weight:700;font-size:12px;letter-spacing:1px;text-transform:uppercase;padding:5px 8px;margin-top:24px;",
    "h1": "font-family:Archivo,Helvetica,Arial,sans-serif;font-weight:800;font-size:30px;line-height:1.15;margin:12px 0 0;color:#191919;",
    "intro": "font-size:17px;color:#5c5c5c;margin:12px 0 0;",
    "h3": "font-family:Consolas,Menlo,monospace;font-size:12px;letter-spacing:1.5px;text-transform:uppercase;color:#5c5c5c;margin:32px 0 10px;",
    "top": "padding:10px 0;border-bottom:1px solid #d0d0d0;",
    "n": "font-family:Consolas,Menlo,monospace;font-weight:700;color:#7a7500;",
    "card": "background:#ffffff;border:1px solid #d0d0d0;border-left:4px solid #fffa00;padding:18px 20px;margin:14px 0;",
    "h2": "font-family:Archivo,Helvetica,Arial,sans-serif;font-weight:800;font-size:20px;line-height:1.25;margin:0 0 8px;color:#191919;",
    "p": "margin:0 0 10px;",
    "why": "margin:0 0 10px;font-size:15px;color:#5c5c5c;",
    "links": "font-family:Consolas,Menlo,monospace;font-size:12px;color:#8a8a8a;",
    "a": "color:#191919;text-decoration:underline;text-decoration-color:#d9d400;",
    "cta": "background:#fffa00;color:#0a0a0b;padding:18px 20px;margin-top:32px;",
    "button": "display:inline-block;background:#0a0a0b;color:#fffa00;font-family:Consolas,Menlo,monospace;font-weight:700;font-size:13px;padding:10px 12px;text-decoration:none;margin-top:10px;",
    "foot": "font-family:Consolas,Menlo,monospace;font-size:11px;color:#8a8a8a;margin-top:24px;",
}


def _ea(text: str, url: str) -> str:
    return f'<a href="{escape(url, quote=True)}" style="{_E["a"]}">{escape(text)}</a>'


def _inline_md(text: str) -> str:
    """Markdown to HTML with inline styles on paragraphs, for email."""
    html = _md.render(text)
    return html.replace("<p>", f'<p style="{_E["p"]}">')


def to_email_html(
    record: DigestRecord, *, web_url: str | None = None, project_url: str | None = None
) -> str:
    """Render a digest as an HTML email with inline styles.

    Args:
        record: The digest.
        web_url: This digest's page on the site, linked as "read on the web".
        project_url: Where readers can get their own feed.

    Returns:
        A complete HTML document suitable as an email body.
    """
    out = [
        f'<div style="{_E["wrap"]}">',
        f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation"><tr>'
        f'<td><span style="{_E["brand"]}">NewsRing</span></td>'
        f'<td align="right" style="{_E["date"]}">{escape(record.date)}'
        + (
            f' · <a href="{escape(web_url, quote=True)}" style="{_E["a"]}">read on the web</a>'
            if web_url
            else ""
        )
        + "</td></tr></table>",
        f'<span style="{_E["eyebrow"]}">News today</span>',
        f'<h1 style="{_E["h1"]}">{escape(record.title)}</h1>',
        f'<div style="{_E["intro"]}">{_inline_md(record.intro)}</div>',
    ]
    if record.headlines:
        out.append(f'<div style="{_E["h3"]}">Across AI today</div>')
        for n, h in enumerate(record.headlines, start=1):
            out.append(
                f'<div style="{_E["top"]}"><span style="{_E["n"]}">{n:02d}</span>&nbsp; '
                f"<strong>{escape(h.headline)}</strong> {escape(h.blurb)} "
                f'<span style="{_E["links"]}">{_ea(_host(h.item.url), h.item.url)}</span></div>'
            )
    if record.stories:
        out.append(f'<div style="{_E["h3"]}">Picked for you</div>')
    for story in record.stories:
        links = " · ".join(_ea(label, url) for label, url in _links(story))
        why = (
            f'<p style="{_E["why"]}"><strong style="color:#191919;">Why it matters:</strong> {escape(story.why_it_matters)}</p>'
            if story.why_it_matters
            else ""
        )
        out.append(
            f'<div style="{_E["card"]}"><h2 style="{_E["h2"]}">{escape(story.headline)}</h2>'
            f"{_inline_md(story.summary)}{why}"
            f'<div style="{_E["links"]}">{links} · via {escape(story.item.source)}</div></div>'
        )
    if record.quick_hits:
        out.append(
            f'<div style="{_E["h3"]}">Quick hits</div><ul style="padding-left:18px;margin:0;">'
        )
        out += [
            f'<li style="margin:6px 0;">{escape(h.line)} ({_ea(_host(h.item.url), h.item.url)})</li>'
            for h in record.quick_hits
        ]
        out.append("</ul>")
    if record.slow_day_note:
        out.append(f'<p style="{_E["why"]}"><em>{escape(record.slow_day_note)}</em></p>')
    if record.sign_off:
        out.append(f'<p style="{_E["p"]}">{escape(record.sign_off)}</p>')
    if project_url:
        out.append(
            f'<div style="{_E["cta"]}"><strong style="font-family:Archivo,Helvetica,Arial,sans-serif;font-size:18px;">Want your own feed?</strong><br>'
            "Your interests, your tone. No ads, no sponsors, open source.<br>"
            f'<a href="{escape(project_url, quote=True)}" style="{_E["button"]}">Get NewsRing →</a></div>'
        )
    out.append(f'<div style="{_E["foot"]}">{escape(stats_line(record))}</div></div>')
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(record.title)}</title></head>"
        f'<body style="{_E["body"]}">' + "".join(out) + "</body></html>"
    )


# -- JSON feed ------------------------------------------------------------------------


def to_web_json(
    record: DigestRecord,
    *,
    page_url: str | None = None,
    image_url: str | None = None,
    project_url: str | None = None,
) -> dict[str, Any]:
    """The newest digest as JSON, for another site to render at view time.

    Prose fields come with an ``_html`` twin rendered by markdown-it with raw
    HTML disabled, so a consumer can insert them without its own Markdown
    parser. Every other string is plain text and must be inserted as text.

    Args:
        record: The digest.
        page_url: This digest's page on the NewsRing site.
        image_url: Today's card.
        project_url: Where readers can get their own feed.

    Returns:
        A JSON-serializable dict. ``version`` changes only on breaking changes.
    """

    def link(label: str, url: str) -> dict[str, str]:
        return {"label": label, "url": url}

    return {
        "version": 1,
        "date": record.date,
        "generated_at": record.generated_at.isoformat(),
        "title": record.title,
        "intro": record.intro,
        "intro_html": _md.render(record.intro),
        "page_url": page_url,
        "image_url": image_url,
        "project_url": project_url,
        "headlines": [
            {
                "kicker": h.kicker,
                "headline": h.headline,
                "blurb": h.blurb,
                "link": link(_host(h.item.url), h.item.url),
            }
            for h in record.headlines
        ],
        "stories": [
            {
                "headline": s.headline,
                "summary_html": _md.render(s.summary),
                "why_it_matters": s.why_it_matters,
                "source": s.item.source,
                "links": [link(label, url) for label, url in _links(s)],
            }
            for s in record.stories
        ],
        "quick_hits": [
            {"line": h.line, "link": link(_host(h.item.url), h.item.url)} for h in record.quick_hits
        ],
        "slow_day_note": record.slow_day_note,
        "sign_off": record.sign_off,
        "stats": stats_line(record),
    }
