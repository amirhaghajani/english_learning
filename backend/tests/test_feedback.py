import json

from app.tutor.feedback import (
    extract_json_array,
    parse_correction_items,
    split_reply,
)

SENTINEL = "[[CORRECTIONS]]"


def _reply(items: list[dict], prose: str = "Nice one.") -> str:
    return f"{prose}\n\n{SENTINEL}\n{json.dumps(items)}"


def test_clean_prose_without_sentinel():
    prose, corrections = split_reply("That sounds lovely. Tell me more?")
    assert prose == "That sounds lovely. Tell me more?"
    assert corrections == []


def test_missing_sentinel_but_json_present():
    text = 'Sure. [{"said": "a", "replacement": "b", "category": "grammar"}]'
    prose, corrections = split_reply(text)
    assert prose == text
    assert corrections == []


def test_valid_corrections():
    text = _reply(
        [
            {
                "said": "I go yesterday",
                "replacement": "I went yesterday",
                "category": "grammar",
                "why": "past time",
                "severity": "major",
            }
        ]
    )
    prose, corrections = split_reply(text, ground_against="I go yesterday")
    assert prose == "Nice one."
    assert len(corrections) == 1
    assert corrections[0].said == "I go yesterday"
    assert corrections[0].replacement == "I went yesterday"
    assert corrections[0].severity == "major"


def test_truncated_json_drops_corrections_keeps_reply():
    text = 'Good. \n\n' + SENTINEL + '\n[{"said": "I go", "replacement": "I went"'
    prose, corrections = split_reply(text)
    assert prose == "Good."
    assert corrections == []


def test_non_json_garbage_after_sentinel():
    text = "Fine.\n\n" + SENTINEL + "\nSorry, I cannot do that."
    prose, corrections = split_reply(text)
    assert prose == "Fine."
    assert corrections == []


def test_extra_prose_after_json_still_parses():
    text = (
        "Okay.\n\n"
        + SENTINEL
        + '\n[{"said": "I has", "replacement": "I have", "category": "grammar"}]\n'
        "Hope that helps!"
    )
    prose, corrections = split_reply(text, ground_against="I has a question")
    assert prose == "Okay."
    assert len(corrections) == 1


def test_replacement_equal_to_said_is_discarded():
    items = [
        {"said": "I go", "replacement": "I go", "category": "grammar"},
        {"said": "I has", "replacement": "I have", "category": "grammar"},
    ]
    text = _reply(items)
    _, corrections = split_reply(text, ground_against="I go and I has")
    assert len(corrections) == 1
    assert corrections[0].said == "I has"


def test_missing_fields_are_discarded():
    items = [
        {"said": "", "replacement": "x"},
        {"said": "y", "replacement": ""},
        {"replacement": "z"},
        {"said": "I has", "replacement": "I have"},
    ]
    text = _reply(items)
    _, corrections = split_reply(text, ground_against="I has")
    assert len(corrections) == 1


def test_five_items_cap_to_three_keeping_major():
    items = [
        {
            "said": f"I goed home at {i}",
            "replacement": f"I went home at {i}",
            "severity": "minor",
        }
        for i in range(4)
    ]
    items.append(
        {
            "said": "I goed home at nine",
            "replacement": "I went home at nine",
            "severity": "major",
        }
    )
    text = _reply(items)
    transcript = " ".join(f"I goed home at {i}" for i in range(5)) + " I goed home at nine"

    parsed = parse_correction_items(items, limit=3)
    assert len(parsed) == 3
    assert any(item.severity == "major" for item in parsed)

    _, corrections = split_reply(text, ground_against=transcript)
    assert len(corrections) == 3
    assert any(item.severity == "major" for item in corrections)


def test_correction_about_an_earlier_turn_is_dropped():
    transcript = "that is on mvp step now"
    text = _reply(
        [
            {
                "said": (
                    "for now that seems good but maybe later on production run we have "
                    "some challage"
                ),
                "replacement": (
                    "for now that seems good, but maybe later on production run we will have "
                    "some challenges"
                ),
                "category": "grammar",
                "why": "Add 'will' for future tense",
                "severity": "major",
            },
            {
                "said": "on mvp step",
                "replacement": "in the MVP step",
                "category": "grammar",
                "why": "Use 'in' with 'step'",
                "severity": "minor",
            },
        ]
    )

    _, corrections = split_reply(text, ground_against=transcript)
    assert [item.said for item in corrections] == ["on mvp step"]


def test_correction_sharing_only_common_words_is_dropped():
    transcript = "that makes sense to me"
    text = _reply(
        [
            {
                "said": "that seems good to you",
                "replacement": "that seems good to me",
                "category": "grammar",
                "why": "Pronoun",
            }
        ]
    )

    _, corrections = split_reply(text, ground_against=transcript)
    assert corrections == []


def test_ungrounded_corrections_are_dropped():
    items = [
        {"said": "purple elephant", "replacement": "purple elephantine"},
        {"said": "I has", "replacement": "I have"},
    ]
    text = _reply(items)
    _, corrections = split_reply(text, ground_against="I has a question")
    assert len(corrections) == 1
    assert corrections[0].said == "I has"


def test_unknown_category_falls_back_to_grammar():
    items = [{"said": "I has", "replacement": "I have", "category": "spelling"}]
    parsed = parse_correction_items(items)
    assert parsed[0].category == "grammar"


def test_unknown_severity_falls_back_to_minor():
    items = [{"said": "I has", "replacement": "I have", "severity": "catastrophic"}]
    parsed = parse_correction_items(items)
    assert parsed[0].severity == "minor"


def test_duplicates_are_collapsed():
    items = [
        {"said": "I has", "replacement": "I have"},
        {"said": "I has", "replacement": "I have"},
    ]
    assert len(parse_correction_items(items)) == 1


def test_empty_correctly_spoken_sentence_yields_no_items():
    text = "Right.\n\n" + SENTINEL + "\n[]"
    prose, corrections = split_reply(text, ground_against="I went to the store yesterday")
    assert prose == "Right."
    assert corrections == []


def test_extract_json_array_respects_strings():
    payload = '[{"why": "a ] b"}, {"why": "c"}]'
    assert extract_json_array(payload) == payload
    assert extract_json_array("no array here") is None


def test_extract_json_array_ignores_brackets_in_strings():
    assert extract_json_array('prefix [{"why": "brackets [ inside"}] suffix') == (
        '[{"why": "brackets [ inside"}]'
    )


def test_markdown_fences_are_stripped():
    text = "```\nHello there.\n```\n\n" + SENTINEL + "\n[]"
    prose, _ = split_reply(text)
    assert prose == "Hello there."


def test_non_list_payload_is_ignored():
    text = "Fine.\n\n" + SENTINEL + '\n{"said": "a"}'
    _, corrections = split_reply(text)
    assert corrections == []


def test_capitalisation_only_fixes_are_discarded():
    items = [
        {"said": "hello there", "replacement": "Hello there"},
        {"said": "i has", "replacement": "I have"},
    ]
    parsed = parse_correction_items(items)
    assert [item.said for item in parsed] == ["i has"]


def test_punctuation_only_fix_is_discarded():
    items = [{"said": "that makes sense", "replacement": "That makes sense!"}]
    assert parse_correction_items(items) == []


def test_spelling_fix_is_kept():
    items = [{"said": "i knw", "replacement": "I know"}]
    parsed = parse_correction_items(items)
    assert len(parsed) == 1
    assert parsed[0].replacement == "I know"


def test_case_insensitive_sentinel():
    text = "Fine.\n\n[[ corrections ]]\n[]"
    prose, _ = split_reply(text)
    assert prose == "Fine."