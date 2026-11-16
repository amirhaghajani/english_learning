from app.tutor.sentences import split_sentences, strip_markdown_fences


def test_simple_sentences():
    assert split_sentences("Hello there. How are you? I am fine!") == [
        "Hello there.",
        "How are you?",
        "I am fine!",
    ]


def test_abbreviations_do_not_split():
    text = "Mr. Smith went home. He was tired."
    assert split_sentences(text) == ["Mr. Smith went home.", "He was tired."]


def test_e_g_and_i_e():
    assert split_sentences("Bring fruit, e.g. apples. Then leave.") == [
        "Bring fruit, e.g. apples.",
        "Then leave.",
    ]
    assert split_sentences("Use a tool, i.e. a hammer. Then stop.") == [
        "Use a tool, i.e. a hammer.",
        "Then stop.",
    ]


def test_decimals_do_not_split():
    assert split_sentences("It costs 3.50 dollars. That is cheap.") == [
        "It costs 3.50 dollars.",
        "That is cheap.",
    ]


def test_newlines_split():
    text = "First line\nSecond line\n\nThird paragraph."
    assert split_sentences(text) == ["First line", "Second line", "Third paragraph."]


def test_trailing_fragment_without_terminator_is_kept():
    assert split_sentences("Are you coming") == ["Are you coming"]


def test_mixed_prefix_abbreviation_and_final_period():
    text = "Dr. Jones said hello. She left."
    assert split_sentences(text) == ["Dr. Jones said hello.", "She left."]


def test_closers_after_terminator():
    text = 'He said "wait." Then he left.'
    assert split_sentences(text) == ['He said "wait."', "Then he left."]


def test_multiple_terminators_stay_together():
    assert split_sentences("Really?! Yes.") == ["Really?!", "Yes."]


def test_empty_and_whitespace():
    assert split_sentences("") == []
    assert split_sentences("   \n  ") == []


def test_single_character_i_is_not_an_abbreviation():
    assert split_sentences("I am here. You are there.") == ["I am here.", "You are there."]


def test_leading_initial():
    assert split_sentences("J. R. Hart spoke. Everyone listened.") == [
        "J. R. Hart spoke.",
        "Everyone listened.",
    ]


def test_strip_markdown_fences():
    assert strip_markdown_fences("```\nhello\n```") == "hello"
    assert strip_markdown_fences("plain") == "plain"


def test_collapses_runs_of_spaces():
    assert split_sentences("Hello    there.  Fine.") == ["Hello there.", "Fine."]