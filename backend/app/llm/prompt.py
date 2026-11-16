from dataclasses import dataclass, field

from app.config import settings
from app.llm.base import ChatMessage
from app.models import Learner, Scenario, Turn

_OUTPUT_CONTRACT = """LATEST LEARNER MESSAGE - the only message you may correct, repeated verbatim:
---
{latest_message}
---

CORRECTION RULES
- Judge only the message above. It is the last thing the learner said.
- Correct grammar, wrong word choice, unnatural phrasing, misspellings, and informal
  abbreviations that have a standard written form (knw -> know, wht -> what, problm -> problem).
- Ignore capitalisation and punctuation. The learner is speaking, not writing, so never
  report a missing comma or a lower-case "i" as a mistake.
- Never correct anything from an earlier turn, even if you spot a mistake there. Earlier
  turns already had their card.
- List at most 3 items, most important first.
- If the message above is genuinely correct and natural, output [].
- Do not invent an error to fill the card. Equally, do not stay silent about a real one.

OUTPUT CONTRACT - follow exactly.
1. Reply with 2 to 4 short spoken sentences. Plain prose only. No markdown, no bullet
   points, no stage directions, no emojis, no headings.
2. Never mention grammar rules, error names, or the words "mistake", "error",
   "correction" unless the learner asks about language directly.
3. Answer what you meant first. Only weave in a recast when there is a real error worth
   modelling; if the latest message is already correct, answer it directly and do NOT repeat
   their words back to them. Do this silently: say it, do not explain it.
4. End with exactly one short follow-up question that keeps them talking.
5. Then output a blank line, then the sentinel line below, then a JSON array.
6. The JSON array has one object per correction and nothing else after it.

SENTINEL LINE (verbatim):
[[CORRECTIONS]]

JSON array shape:
[{"said": "<exact wrong fragment copied from the LATEST LEARNER MESSAGE above>",
  "replacement": "<fixed fragment>",
  "category": "grammar|word_choice|naturalness",
  "why": "<one short line, no jargon>",
  "severity": "minor|major"}]

Hard rules for the array:
- "said" must be copied verbatim from the LATEST LEARNER MESSAGE, not paraphrased and not
  taken from an earlier turn.
- "replacement" must differ from "said".
- "why" is for the learner, so keep it under 15 words and jargon-free."""

_PERSONA = """You are Emma, a warm American English conversation partner. You are 29, curious,
gently funny, and you never lecture. You are not a teacher and you never sound like one.
You are proud of the learner for talking and you are genuinely interested in their answer.
You adapt your vocabulary and speed to their level without ever sounding like they are
being managed."""

_TRANSFER_NOTE = """The learner's first language is {native_lang}. Anticipate the mistakes that
language usually causes in English (for example omitted articles, preposition calques,
gendered pronouns, or word order) and correct those first. Do not treat every slip as
equally important."""


@dataclass
class RetrievedDoc:
    title: str
    body: str
    kind: str = "grammar"
    level: str = "A1"
    score: float = 0.0


@dataclass
class RecurringError:
    category: str
    said: str
    replacement: str
    count: int = 1


@dataclass
class PromptContext:
    learner: Learner
    scenario: Scenario | None = None
    curriculum: list[RetrievedDoc] = field(default_factory=list)
    recurring: list[RecurringError] = field(default_factory=list)
    history: list[Turn] = field(default_factory=list)
    latest_message: str = ""
    history_turns: int = settings.history_turns
    max_speak_chars: int = settings.max_speak_chars
    max_corrections: int = settings.max_corrections


_CEFR_GUIDE = {
    "A1": "Use short sentences and the most common 500 words. Present simple, present continuous.",
    "A2": "Everyday language, simple past, common connectors like 'and', 'but', 'because'.",
    "B1": "Natural conversational English. Mix tenses, use common phrasal verbs.",
    "B2": "Fluent, idiomatic English with some less common vocabulary and varied structure.",
    "C1": "Nuanced, idiomatic English. Register, humour and subtle phrasing are welcome.",
}


def _format_scenario(scenario: Scenario | None) -> str:
    if scenario is None:
        return (
            "MODE: free conversation.\n"
            "There is no role-play brief. Follow the learner's lead, stay curious, and keep "
            "them talking about whatever they bring up."
        )
    targets = scenario.target_language.strip()
    return (
        f"MODE: role-play scenario '{scenario.title}'.\n"
        f"Setting: {scenario.setting}\n"
        f"Your role (Emma): {scenario.emma_role}\n"
        f"The learner's role: {scenario.learner_role}\n"
        f"Target language to encourage naturally: {targets or 'general fluency'}\n"
        f"Success looks like: {scenario.success_criteria or 'a relaxed, flowing exchange'}\n"
        f"Open in character if this is the first turn: {scenario.opening_line}"
    )


def _format_curriculum(docs: list[RetrievedDoc]) -> str:
    if not docs:
        return "No reference notes matched this turn. Rely on your own judgement."
    blocks = []
    for doc in docs:
        blocks.append(f"- [{doc.kind}/{doc.level}] {doc.title}\n  {doc.body.strip()}")
    return "REFERENCE NOTES (use silently, never quote or cite them):\n" + "\n".join(blocks)


def _format_recurring(errors: list[RecurringError]) -> str:
    if not errors:
        return "No recurring error patterns worth flagging yet."
    lines = []
    for err in errors:
        lines.append(
            f"- {err.category} x{err.count}: they said \"{err.said}\" -> \"{err.replacement}\""
        )
    header = "PATTERNS YOU HAVE SEEN FROM THIS LEARNER BEFORE (weave fixes in silently):"
    return header + "\n" + "\n".join(lines)


def build_system_prompt(ctx: PromptContext) -> str:
    learner = ctx.learner
    parts: list[str] = [
        _PERSONA,
        "",
        f"YOUR NAME: {settings.emma_name}. You speak {settings.emma_variant} English.",
        "",
        "LEARNER PROFILE:",
        f"- Name: {learner.name}",
        f"- Level: {learner.cefr.value} ({_CEFR_GUIDE.get(learner.cefr.value, '')})",
        f"- First language: {learner.native_lang}",
        f"- Goals: {learner.goals.strip() or 'general conversation confidence'}",
        "",
        _TRANSFER_NOTE.format(native_lang=learner.native_lang),
        "",
        _format_scenario(ctx.scenario),
        "",
        _format_curriculum(ctx.curriculum),
        "",
        _format_recurring(ctx.recurring),
        "",
        "STYLE LIMITS:",
        f"- Keep each spoken reply under about {ctx.max_speak_chars} characters total.",
        f"- Never more than {ctx.max_corrections} corrections in the JSON array.",
        "- No text formatting of any kind in the prose part.",
        "",
        _OUTPUT_CONTRACT.replace(
            "{latest_message}", ctx.latest_message.strip() or "(empty message)"
        ),
    ]
    return "\n".join(p for p in parts if p is not None)


def build_messages(ctx: PromptContext, learner_text: str) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    for turn in ctx.history:
        if turn.transcript.strip():
            messages.append(ChatMessage(role="user", content=turn.transcript.strip()))
        if turn.reply_text.strip():
            messages.append(ChatMessage(role="assistant", content=turn.reply_text.strip()))
    messages.append(ChatMessage(role="user", content=learner_text.strip()))
    return messages