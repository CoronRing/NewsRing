"""The three agents, built from a config.

Each is a structured-output `rt.agent_node` with no tools. The pipeline in
`newsring.pipeline` decides what each one sees, so no agent spends tokens
navigating sources and none can reach a URL it was not given.

- **Triage** scores a batch of candidates 0 to 10. Only used when the pool is
  larger than `run.triage_threshold`.
- **Editor** chooses the main stories and quick hits from the whole pool at
  once, so it can compare across sources and merge duplicate coverage.
- **Writer** writes the digest in the reader's voice from the picked stories'
  full text.
- **Headliner** picks the few most exciting stories of the last few days for
  a general audience, for the shareable card. It ignores the reader's profile.

`rt.agent_node` returns a class, not an instance, which is why the bound names
are PascalCase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

import railtracks as rt

from newsring.config import Config, DetailLevel, HeadlineSettings, Profile
from newsring.llm import build_llm
from newsring.models import DigestOutput, HeadlineOutput, SelectionOutput, TriageOutput

if TYPE_CHECKING:
    # Neither name is exported from a public railtracks module, so naming an
    # agent's type means reaching into these. Type-checking only, on purpose.
    from railtracks.built_nodes.llm.response import StructuredResponse
    from railtracks.nodes.nodes import Node

    TriageAgent: TypeAlias = type[Node[..., StructuredResponse[TriageOutput]]]
    EditorAgent: TypeAlias = type[Node[..., StructuredResponse[SelectionOutput]]]
    WriterAgent: TypeAlias = type[Node[..., StructuredResponse[DigestOutput]]]
    HeadlinerAgent: TypeAlias = type[Node[..., StructuredResponse[HeadlineOutput]]]

DETAIL_GUIDE: dict[DetailLevel, str] = {
    "brief": "One or two sentences per story. Lead with the fact; skip background.",
    "standard": "One paragraph of three to five sentences per story: what happened, the key detail, and the implication.",
    "deep": "Two to four paragraphs per story: what happened, how it works technically, and the caveats or open questions.",
}


@dataclass(frozen=True, slots=True)
class Agents:
    """The agent classes for one config.

    Attributes:
        triage: Scores candidate batches.
        editor: Picks stories.
        writer: Writes the digest.
        headliner: Picks the card's top stories.
        llm: The model behind all of them, kept so the run can report which
            model and key actually answered.
    """

    triage: TriageAgent
    editor: EditorAgent
    writer: WriterAgent
    headliner: HeadlinerAgent
    llm: rt.llm.ModelBase


def _reader_block(profile: Profile) -> str:
    lines = ["## The reader", "", "Interests:", profile.interests.strip()]
    if profile.avoid.strip():
        lines += ["", "Leave out:", profile.avoid.strip()]
    return "\n".join(lines)


def triage_prompt(profile: Profile) -> str:
    """System message for the triage agent."""
    return f"""You screen news candidates for one reader's personal daily digest.

{_reader_block(profile)}

## Task

You will receive a batch of candidates, each with an id like [c17], a title, its source and signals, and a snippet.
Score every candidate from 0 to 10 for how much this reader would want to see it today:

- 9-10: squarely inside the interests and genuinely new or significant.
- 6-8: relevant and worth considering.
- 3-5: tangential, or relevant but minor.
- 0-2: off-topic, or something the reader asked to leave out.

Return one score for every candidate in the batch, using the ids exactly as given."""


def editor_prompt(profile: Profile) -> str:
    """System message for the editor agent."""
    count = profile.count
    return f"""You are the editor of a personal daily news digest written for one reader.

{_reader_block(profile)}

## Task

You will receive today's candidates. Each has an id like [c17], a title, its source, signals (engagement score, comments, which other sources also carried it, date, source tags), and a short snippet.

Choose between {count.min} and {count.max} main stories, most important first, and up to {count.quick_hits} quick hits: stories worth one line but not a full write-up.

How to choose:

1. Relevance to the reader's interests comes first. Use the interests as written, not a generic idea of what is newsworthy.
2. Then significance: a story carried by several sources, or with a high engagement score, usually matters more.
3. Prefer substance (releases, research, technical write-ups, real incidents) over commentary, opinion and marketing.
4. When several candidates cover the same story, pick the best one as the main entry and list the others in related_ids. Prefer the primary source (the lab's own post, the release notes, the paper) over coverage of it.
5. Each id may appear only once across all picks, related_ids and quick hits.
6. Never repeat a story listed under "Already covered", whatever the source or headline, unless there is a substantial new development; then say what is new in the reason.
7. If fewer than {count.min} stories are genuinely worth the reader's time, pick fewer and say why in slow_day_note. Never pad with filler.

For each pick, give a one-sentence reason addressed to why this reader would care. Use ids exactly as given."""


def writer_prompt(profile: Profile) -> str:
    """System message for the writer agent."""
    tone = profile.tone
    address = f"The reader's name is {profile.name}." if profile.name else ""
    return f"""You write a personal daily news digest for one reader. {address}

{_reader_block(profile)}

## Voice

- Language: {tone.language}.
- Style: {tone.style}.
- Length: {DETAIL_GUIDE[tone.detail]}

## Task

You will receive the stories the editor chose, in order, each with an id, its title, source, the editor's reason for picking it, and source material. Then the quick hits.

Write:

- a title for today's digest and a two or three sentence intro,
- one write-up per story, in the given order, with a short headline and a why_it_matters line tied to the reader's interests,
- one line per quick hit,
- optionally a one-line sign-off.

Rules:

- Use only the source material. Do not invent facts, numbers, names, benchmarks or quotes. If the material is thin, write less rather than guess, and it is fine to say details are sparse.
- Keep the voice, but never let it distort the facts.
- Do not include links or URLs; they are added for you. Do not use headings inside a write-up.
- Use ids exactly as given."""


def headliner_prompt(settings: HeadlineSettings) -> str:
    """System message for the headline agent."""
    return f"""You pick the {settings.count} most exciting AI stories of the last few days for a shareable daily card.

The audience is {settings.audience}. The card is read in a few seconds, so each story must be clear on its own.

## How to choose

1. Prefer things that genuinely happened and change what people can do or know: major model releases, important research results, significant open-source releases, notable incidents.
2. A story carried by several sources, or with a high engagement score, usually matters more.
3. Prefer the primary source (the lab's own announcement, the paper, the release notes) over coverage of it when both are present.
4. Skip funding news, opinion pieces, minor version bumps and marketing.
5. When two stories are equally strong, prefer the newer one.
6. Pick {settings.count} different stories, never two about the same event.
7. Never repeat a story listed under "Already covered" unless there is a substantial new development.

## How to write

- kicker: two or three words naming the kind of story.
- headline: under 70 characters, concrete, no clickbait, no emoji.
- blurb: one sentence under 150 characters, from the given material only. Do not invent numbers or claims.

Use the ids exactly as given."""


def build_agents(config: Config) -> Agents:
    """Build the three agent classes for a config.

    Args:
        config: The configuration. The profile is baked into each system
            message, so build once per config, not once per call.

    Returns:
        The agent classes.
    """
    main_llm = build_llm(config.llm)
    triage_llm = (
        build_llm(config.llm, model=config.llm.triage_model)
        if config.llm.triage_model
        else main_llm
    )
    profile = config.profile

    Triage: TriageAgent = rt.agent_node(
        "NewsRing Triage",
        output_schema=TriageOutput,
        llm=triage_llm,
        system_message=triage_prompt(profile),
    )
    Editor: EditorAgent = rt.agent_node(
        "NewsRing Editor",
        output_schema=SelectionOutput,
        llm=main_llm,
        system_message=editor_prompt(profile),
    )
    Writer: WriterAgent = rt.agent_node(
        "NewsRing Writer",
        output_schema=DigestOutput,
        llm=main_llm,
        system_message=writer_prompt(profile),
    )
    Headliner: HeadlinerAgent = rt.agent_node(
        "NewsRing Headliner",
        output_schema=HeadlineOutput,
        llm=main_llm,
        system_message=headliner_prompt(config.headlines),
    )
    return Agents(triage=Triage, editor=Editor, writer=Writer, headliner=Headliner, llm=main_llm)
