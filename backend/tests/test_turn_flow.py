from conftest import ScriptedLLM  # noqa: F401
from helpers import audio_chunks, make_wav, parse_sse, sse_order_ok

from app.audio.stt import Transcription


def _setup(client, scripted_llm, fake_stt):
    learner = client.post(
        "/api/learners",
        json={"name": "Amir", "cefr": "B1", "native_lang": "fa", "goals": "work"},
    )
    assert learner.status_code == 201, learner.text
    learner_id = learner.json()["id"]

    session = client.post(
        "/api/sessions", json={"learner_id": learner_id, "mode": "free"}
    )
    assert session.status_code == 201, session.text
    session_id = session.json()["id"]

    fake_stt.transcript = "Yesterday I go to the store and I buy some milk."
    scripted_llm.chunks = [
        "Oh nice, ",
        "so you went to the store",
        " and bought some milk?",
        " What did you need?",
        "\n\n[[CORRECTIONS]]\n",
        '[{"said": "I go to the store", "replacement": "I went to the store", '
        '"category": "grammar", "why": "Past time needs past simple.", '
        '"severity": "major"}, '
        '{"said": "I buy some milk", "replacement": "I bought some milk", '
        '"category": "grammar", "why": "Same finished past.", "severity": "major"}]',
    ]
    return learner_id, session_id


def test_full_turn_end_to_end(client, scripted_llm, fake_stt):
    learner_id, session_id = _setup(client, scripted_llm, fake_stt)

    turn_resp = client.post(
        "/api/turns",
        data={"session_id": str(session_id)},
        files={"file": ("a.wav", make_wav(800), "audio/wav")},
    )
    assert turn_resp.status_code == 201, turn_resp.text
    payload = turn_resp.json()
    assert payload["transcript"] == "Yesterday I go to the store and I buy some milk."
    assert payload["no_speech"] is False

    reply = client.get(f"/api/turns/{payload['turn_id']}/reply")
    assert reply.status_code == 200
    events = parse_sse(reply.text)

    assert sse_order_ok(events)
    names = [name for name, _ in events]
    assert names.count("meta") == 1

    sentences = [data["text"] for name, data in events if name == "sentence"]
    assert sentences == [
        "Oh nice, so you went to the store and bought some milk?",
        "What did you need?",
    ]

    first = audio_chunks(events, 0)
    second = audio_chunks(events, 1)
    assert first and second
    seqs = [data["seq"] for name, data in events if name == "audio" and data["index"] == 0]
    assert seqs == list(range(len(seqs)))

    correction_events = [data for name, data in events if name == "corrections"]
    assert len(correction_events) == 1
    items = correction_events[0]["items"]
    assert [i["said"] for i in items] == ["I go to the store", "I buy some milk"]

    session = client.get(f"/api/sessions/{session_id}?learner_id={learner_id}")
    assert session.status_code == 200
    turns = session.json()["turns"]
    assert len(turns) == 1
    assert turns[0]["reply_text"].startswith("Oh nice, so you went")
    assert "[[CORRECTIONS]]" not in turns[0]["reply_text"]
    assert len(turns[0]["corrections"]) == 2
    assert turns[0]["audio_ms"] > 0


def test_clean_sentence_produces_no_corrections(client, scripted_llm, fake_stt):
    learner = client.post("/api/learners", json={"name": "Sara", "cefr": "B2"}).json()
    session = client.post(
        "/api/sessions", json={"learner_id": learner["id"], "mode": "free"}
    ).json()

    fake_stt.transcript = "I went to the store yesterday and I bought some milk."
    scripted_llm.chunks = ["Right, that sounds easy enough. Do you go there often?"]

    turn = client.post(
        "/api/turns",
        data={"session_id": str(session["id"])},
        files={"file": ("a.wav", make_wav(500), "audio/wav")},
    ).json()

    reply = client.get(f"/api/turns/{turn['turn_id']}/reply")
    events = parse_sse(reply.text)
    items = [d for n, d in events if n == "corrections"][0]["items"]
    assert items == []


def test_no_speech_turn_skips_llm(client, scripted_llm, fake_stt):
    learner = client.post("/api/learners", json={"name": "Nina"}).json()
    session = client.post(
        "/api/sessions", json={"learner_id": learner["id"], "mode": "free"}
    ).json()

    fake_stt.transcript = ""
    turn = client.post(
        "/api/turns",
        data={"session_id": str(session["id"])},
        files={"file": ("a.wav", make_wav(300), "audio/wav")},
    ).json()
    assert turn["no_speech"] is True
    assert scripted_llm.requests == []

    events = parse_sse(client.get(f"/api/turns/{turn['turn_id']}/reply").text)
    assert sse_order_ok(events)
    assert [d for n, d in events if n == "corrections"][0]["items"] == []


def test_llm_error_is_reported_as_sse_event(client, scripted_llm, fake_stt):
    from app.llm.base import LLMError

    learner = client.post("/api/learners", json={"name": "Omar"}).json()
    session = client.post(
        "/api/sessions", json={"learner_id": learner["id"], "mode": "free"}
    ).json()

    fake_stt.transcript = "I am testing the error path."
    scripted_llm.error = LLMError("llm_unreachable", "Ollama is down", status_code=503)

    turn = client.post(
        "/api/turns",
        data={"session_id": str(session["id"])},
        files={"file": ("a.wav", make_wav(400), "audio/wav")},
    ).json()

    reply = client.get(f"/api/turns/{turn['turn_id']}/reply")
    events = parse_sse(reply.text)
    errors = [d for n, d in events if n == "error"]
    assert errors and errors[0]["code"] == "llm_unreachable"


def test_abandon_marks_turn(client, scripted_llm, fake_stt):
    learner = client.post("/api/learners", json={"name": "Rex"}).json()
    session = client.post(
        "/api/sessions", json={"learner_id": learner["id"], "mode": "free"}
    ).json()

    fake_stt.transcript = "One more sentence."
    turn = client.post(
        "/api/turns",
        data={"session_id": str(session["id"])},
        files={"file": ("a.wav", make_wav(400), "audio/wav")},
    ).json()

    resp = client.post(f"/api/turns/{turn['turn_id']}/abandon")
    assert resp.status_code == 200
    assert resp.json()["abandoned"] is True

    session_view = client.get(f"/api/sessions/{session['id']}").json()
    assert session_view["turns"][0]["abandoned"] is True


def test_audio_upload_validation(client, scripted_llm):
    learner = client.post("/api/learners", json={"name": "Val"}).json()
    session = client.post(
        "/api/sessions", json={"learner_id": learner["id"], "mode": "free"}
    ).json()

    bad = client.post(
        "/api/turns",
        data={"session_id": str(session["id"])},
        files={"file": ("a.wav", b"not a wav", "audio/wav")},
    )
    assert bad.status_code == 400

    missing = client.post(
        "/api/turns",
        data={"session_id": "99999"},
        files={"file": ("a.wav", make_wav(200), "audio/wav")},
    )
    assert missing.status_code == 404


def test_audio_has_pause_after_each_sentence(client, scripted_llm, fake_stt):
    import base64
    from collections import defaultdict

    from app.audio.tts import FakeTTS
    from app.tutor.pipeline import SENTENCE_GAP_MS

    learner = client.post("/api/learners", json={"name": "Pauses"}).json()
    session = client.post(
        "/api/sessions", json={"learner_id": learner["id"], "mode": "free"}
    ).json()

    fake_stt.transcript = "Yesterday I go to the shop."
    scripted_llm.chunks = [
        "I went to the shop.",
        " What did you buy?",
        " And how much was it?",
        "\n\n[[CORRECTIONS]]\n[]",
    ]

    turn = client.post(
        "/api/turns",
        data={"session_id": str(session["id"])},
        files={"file": ("a.wav", make_wav(300), "audio/wav")},
    ).json()

    events = parse_sse(client.get(f"/api/turns/{turn['turn_id']}/reply").text)

    by_index = defaultdict(list)
    for name, data in events:
        if name == "audio":
            by_index[data["index"]].append(data)

    assert len(by_index) == 3, by_index.keys()

    rate = FakeTTS().sample_rate
    expected_gap_bytes = 2 * rate * SENTENCE_GAP_MS // 1000

    for index, chunks in by_index.items():
        seqs = [chunk["seq"] for chunk in chunks]
        assert seqs == list(range(len(seqs))), (index, seqs)

        trailing = base64.b64decode(chunks[-1]["pcm_b64"])
        assert len(trailing) == expected_gap_bytes, (index, len(trailing))
        assert set(trailing) == {0}, f"sentence {index} does not end in silence"


def test_text_turn_without_microphone(client, scripted_llm):
    learner = client.post("/api/learners", json={"name": "Typed"}).json()
    session = client.post(
        "/api/sessions", json={"learner_id": learner["id"], "mode": "free"}
    ).json()

    scripted_llm.chunks = [
        "Nice, tell me more?",
        "\n\n[[CORRECTIONS]]\n[]",
    ]
    created = client.post(
        "/api/turns/text",
        json={"session_id": session["id"], "text": "  Yesterday I go   to the shop.  "},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["transcript"] == "Yesterday I go to the shop."
    assert body["no_speech"] is False
    assert body["audio_ms"] == 0
    assert scripted_llm.requests == []

    reply = client.get(f"/api/turns/{body['turn_id']}/reply")
    events = parse_sse(reply.text)
    assert sse_order_ok(events)
    assert [d for n, d in events if n == "corrections"][0]["items"] == []


def test_text_turn_rejects_blank_and_unknown_session(client):
    learner = client.post("/api/learners", json={"name": "Typist"}).json()
    session = client.post(
        "/api/sessions", json={"learner_id": learner["id"], "mode": "free"}
    ).json()

    blank = client.post(
        "/api/turns/text", json={"session_id": session["id"], "text": "   "}
    )
    assert blank.status_code == 400

    unknown = client.post("/api/turns/text", json={"session_id": 9999, "text": "hello"})
    assert unknown.status_code == 404


def test_scenario_opening_streams_audio(client):
    scenarios = client.get("/api/scenarios").json()
    with_opening = [s for s in scenarios if s["opening_line"].strip()]
    assert with_opening, "seed data should provide opening lines"

    slug = with_opening[0]["slug"]
    response = client.get(f"/api/scenarios/{slug}/opening")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = parse_sse(response.text)
    names = [name for name, _ in events]
    assert names[0] == "sentence"
    assert names[-1] == "done"
    assert "audio" in names

    sentences = [data["text"] for name, data in events if name == "sentence"]
    assert " ".join(sentences) == with_opening[0]["opening_line"]

    audio = [data for name, data in events if name == "audio"]
    assert audio
    indices = {chunk["index"] for chunk in audio}
    assert indices == set(range(len(sentences)))


def test_scenario_opening_unknown_slug(client):
    response = client.get("/api/scenarios/does-not-exist/opening")
    assert response.status_code == 404


def test_transcription_shape():
    result = Transcription(text="hello", no_speech=False)
    assert result.language == "en"