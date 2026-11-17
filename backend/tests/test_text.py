import json

from app.audio.text import DEFAULT_LEXICON, normalize_for_speech


def test_strips_markdown_and_links():
    assert normalize_for_speech("**Wow** this is _great_.") == "Wow this is great."
    assert normalize_for_speech("See [the docs](https://example.com) here.") == "See the docs here."
    assert normalize_for_speech("## Heading\nBody text") == "Heading Body text"


def test_replaces_dashes_with_a_pause():
    assert normalize_for_speech("It was good\u2014really good.") == "It was good, really good."
    assert normalize_for_speech("one\u2013two") == "one, two"
    assert normalize_for_speech("I went home - then I slept.") == "I went home, then I slept."
    assert normalize_for_speech("Wait \u2014 what?") == "Wait, what?"
    assert normalize_for_speech("a\u2015b") == "a, b"


def test_no_dash_characters_survive():
    text = "One\u2014two\u2013three - four \u2212 five"
    out = normalize_for_speech(text)
    for dash in "\u2014\u2013\u2212\u2015":
        assert dash not in out
    assert " - " not in out


def test_drops_emoji_and_extraneous_whitespace():
    assert normalize_for_speech("Hello\U0001f600  there   friend") == "Hello there friend"


def test_removes_anything_after_the_corrections_sentinel():
    text = "Nice work.\n\n[[CORRECTIONS]]\n[{\"said\": \"a\"}]"
    assert normalize_for_speech(text) == "Nice work."


def test_default_lexicon_expands_abbreviations():
    assert "for example" in normalize_for_speech("Bring fruit, e.g. apples.")
    assert "et cetera" in normalize_for_speech("We need cups, plates, etc.")
    assert "that is" in normalize_for_speech("Use a tool, i.e. a hammer.")


def test_lexicon_is_word_bounded():
    assert normalize_for_speech("Escaped words stay put.") == "Escaped words stay put."
    assert DEFAULT_LEXICON["etc."] == "et cetera"


def test_custom_pronunciation_file_is_loaded(tmp_path, monkeypatch):
    import app.audio.text as text_module

    path = tmp_path / "pronunciation.json"
    path.write_text(json.dumps({"quux": "kuh-ooks", "MVP": "M V P"}), encoding="utf-8")

    monkeypatch.setattr(text_module.settings, "pronunciation_file", str(path), raising=False)
    text_module._load_lexicon.cache_clear()
    try:
        assert normalize_for_speech("a quux here") == "a kuh-ooks here"
        assert normalize_for_speech("the MVP plan") == "the M V P plan"
    finally:
        text_module._load_lexicon.cache_clear()


def test_empty_input():
    assert normalize_for_speech("") == ""
    assert normalize_for_speech("   \n ") == ""