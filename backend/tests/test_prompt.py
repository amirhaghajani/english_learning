from app.llm.prompt import PromptContext, RecurringError, build_messages, build_system_prompt
from app.models import (
    CEFR,
    CorrectionCategory,
    CorrectionSeverity,
    Learner,
    Scenario,
    SessionMode,
    Turn,
)


def _learner() -> Learner:
    return Learner(
        id=1,
        name="Amir",
        cefr=CEFR.B1,
        native_lang="fa",
        goals="speak at work",
    )


def _turn(seq: int, transcript: str, reply: str) -> Turn:
    return Turn(
        id=seq,
        session_id=1,
        seq=seq,
        transcript=transcript,
        reply_text=reply,
        audio_ms=0,
        no_speech=False,
    )


def test_prompt_embeds_the_exact_latest_message():
    ctx = PromptContext(
        learner=_learner(),
        history=[_turn(1, "I agree, simplicity is key.", "Right, agreed.")],
        latest_message="i knw, but wht is the problm",
    )

    prompt = build_system_prompt(ctx)

    assert "i knw, but wht is the problm" in prompt
    assert "LATEST LEARNER MESSAGE" in prompt
    assert "[[CORRECTIONS]]" in prompt


def test_prompt_does_not_leak_the_latest_message_into_history():
    history = [_turn(1, "first thing", "ok")]
    ctx = PromptContext(learner=_learner(), history=history, latest_message="second thing")

    messages = build_messages(ctx, "second thing")

    assert messages[-1].role == "user"
    assert messages[-1].content == "second thing"
    assert [m.content for m in messages].count("second thing") == 1


def test_prompt_mentions_no_punctuation_corrections():
    prompt = build_system_prompt(PromptContext(learner=_learner(), latest_message="hello"))
    assert "Ignore capitalisation and punctuation" in prompt


def test_prompt_includes_recurring_errors():
    ctx = PromptContext(
        learner=_learner(),
        recurring=[RecurringError(category="grammar", said="I has", replacement="I have", count=3)],
        latest_message="I has a question",
    )
    prompt = build_system_prompt(ctx)
    assert "I has" in prompt
    assert "PATTERNS YOU HAVE SEEN" in prompt


def test_prompt_lists_scenario_brief():
    scenario = Scenario(
        id=1,
        slug="at-the-coffee-shop",
        title="Ordering at a coffee shop",
        level="A2",
        setting="A busy cafe",
        learner_role="customer",
        emma_role="barista",
        opening_line="Morning!",
        target_language="polite requests",
        success_criteria="order a drink",
    )
    ctx = PromptContext(learner=_learner(), scenario=scenario, latest_message="hello")
    prompt = build_system_prompt(ctx)
    assert "Ordering at a coffee shop" in prompt
    assert "A busy cafe" in prompt


def test_enums_are_stable_for_prompts():
    assert CEFR.B1.value == "B1"
    assert SessionMode.free.value == "free"
    assert CorrectionCategory.grammar.value == "grammar"
    assert CorrectionSeverity.major.value == "major"