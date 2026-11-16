from helpers import make_wav


def _learner(client, name: str, **extra) -> dict:
    resp = client.post("/api/learners", json={"name": name, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_sessions_are_scoped_by_learner(client, scripted_llm, fake_stt):
    amir = _learner(client, "Amir", cefr="B1")
    sara = _learner(client, "Sara", cefr="A2")

    s_amir = client.post(
        "/api/sessions", json={"learner_id": amir["id"], "mode": "free"}
    ).json()
    s_sara = client.post(
        "/api/sessions", json={"learner_id": sara["id"], "mode": "free"}
    ).json()

    fake_stt.transcript = "Hello there."
    for session in (s_amir, s_sara):
        client.post(
            "/api/turns",
            data={"session_id": str(session["id"])},
            files={"file": ("a.wav", make_wav(300), "audio/wav")},
        )

    listing = client.get(f"/api/sessions?learner_id={amir['id']}")
    assert listing.status_code == 200
    ids = [row["id"] for row in listing.json()]
    assert ids == [s_amir["id"]]

    hidden = client.get(f"/api/sessions/{s_sara['id']}?learner_id={amir['id']}")
    assert hidden.status_code == 404

    own = client.get(f"/api/sessions/{s_sara['id']}?learner_id={sara['id']}")
    assert own.status_code == 200
    assert own.json()["turns"][0]["transcript"] == "Hello there."


def test_duplicate_learner_name_is_rejected(client):
    _learner(client, "Duplicated")
    second = client.post("/api/learners", json={"name": "Duplicated"})
    assert second.status_code == 409


def test_learner_update(client):
    learner = _learner(client, "Before")
    patched = client.patch(
        f"/api/learners/{learner['id']}",
        json={"cefr": "B2", "goals": "speak at work", "native_lang": "fa"},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["cefr"] == "B2"
    assert body["goals"] == "speak at work"

    clash = client.patch(
        f"/api/learners/{learner['id']}", json={"name": "After"}
    )
    assert clash.status_code == 200


def test_scenario_session_requires_scenario(client):
    learner = _learner(client, "ScenarioUser")
    bad = client.post(
        "/api/sessions", json={"learner_id": learner["id"], "mode": "scenario"}
    )
    assert bad.status_code == 400

    unknown = client.post(
        "/api/sessions",
        json={"learner_id": learner["id"], "mode": "scenario", "scenario_slug": "nope"},
    )
    assert unknown.status_code == 404


def test_scenarios_are_seeded_and_filterable(client):
    all_scenarios = client.get("/api/scenarios")
    assert all_scenarios.status_code == 200
    rows = all_scenarios.json()
    assert len(rows) >= 6

    b2 = client.get("/api/scenarios?level=B2")
    assert b2.status_code == 200
    assert all(row["level"] == "B2" for row in b2.json())
    assert any(row["slug"] == "job-interview" for row in b2.json())


def test_session_end_is_idempotent(client):
    learner = _learner(client, "EndUser")
    session = client.post(
        "/api/sessions", json={"learner_id": learner["id"], "mode": "free"}
    ).json()

    first = client.post(f"/api/sessions/{session['id']}/end")
    assert first.status_code == 200
    assert first.json()["ended_at"] is not None

    second = client.post(f"/api/sessions/{session['id']}/end")
    assert second.status_code == 200
    assert second.json()["ended_at"] == first.json()["ended_at"]


def test_session_cannot_accept_turns_after_end(client, scripted_llm, fake_stt):
    learner = _learner(client, "Closed")
    session = client.post(
        "/api/sessions", json={"learner_id": learner["id"], "mode": "free"}
    ).json()
    client.post(f"/api/sessions/{session['id']}/end")

    resp = client.post(
        "/api/turns",
        data={"session_id": str(session["id"])},
        files={"file": ("a.wav", make_wav(200), "audio/wav")},
    )
    assert resp.status_code == 409