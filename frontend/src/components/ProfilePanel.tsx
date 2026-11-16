import { useState } from "react";

import type { CEFR, Learner, Scenario, Session } from "../api";

interface ProfilePanelProps {
  learners: Learner[];
  learner: Learner | null;
  scenarios: Scenario[];
  scenarioSlug: string | null;
  session: Session | null;
  onChooseLearner: (learner: Learner) => void;
  onCreateLearner: (input: {
    name: string;
    cefr: CEFR;
    native_lang: string;
    goals: string;
  }) => Promise<unknown>;
  onUpdateLearner: (input: {
    name?: string;
    cefr?: CEFR;
    native_lang?: string;
    goals?: string;
  }) => Promise<unknown>;
  onChooseScenario: (slug: string | null) => void;
  onStartSession: (mode: "free" | "scenario") => Promise<unknown>;
  onEndSession: () => Promise<unknown>;
  busy: boolean;
}

const LEVELS: CEFR[] = ["A1", "A2", "B1", "B2", "C1"];

export function ProfilePanel({
  learners,
  learner,
  scenarios,
  scenarioSlug,
  session,
  onChooseLearner,
  onCreateLearner,
  onUpdateLearner,
  onChooseScenario,
  onStartSession,
  onEndSession,
  busy,
}: ProfilePanelProps) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [cefr, setCefr] = useState<CEFR>("B1");
  const [nativeLang, setNativeLang] = useState("");
  const [goals, setGoals] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const submit = async () => {
    setFormError(null);
    if (!name.trim()) {
      setFormError("Give the profile a name first.");
      return;
    }
    try {
      await onCreateLearner({
        name: name.trim(),
        cefr,
        native_lang: nativeLang.trim() || "en",
        goals: goals.trim(),
      });
      setCreating(false);
      setName("");
      setGoals("");
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Could not create the profile.");
    }
  };

  const saveLevel = async (next: CEFR) => {
    if (!learner) return;
    try {
      await onUpdateLearner({ cefr: next });
    } catch {
      /* surfaced through the global error banner */
    }
  };

  const saveGoals = async () => {
    if (!learner) return;
    try {
      await onUpdateLearner({ goals: goals.trim() });
    } catch {
      /* surfaced through the global error banner */
    }
  };

  return (
    <aside className="panel">
      <div className="panel__section">
        <h2 className="panel__title">Learner</h2>
        {learners.length === 0 && !creating ? (
          <p className="panel__muted">No profiles yet. Create one to start.</p>
        ) : null}

        <div className="chips">
          {learners.map((row) => (
            <button
              key={row.id}
              type="button"
              className={`chip chip--button${learner?.id === row.id ? " chip--active" : ""}`}
              onClick={() => onChooseLearner(row)}
            >
              {row.name}
              <span className="chip__sub">{row.cefr}</span>
            </button>
          ))}
          <button type="button" className="chip chip--button" onClick={() => setCreating((v) => !v)}>
            {creating ? "Cancel" : "+ New"}
          </button>
        </div>

        {learner ? (
          <div className="level-row">
            <span className="panel__label">Level</span>
            <div className="chips chips--tight">
              {LEVELS.map((level) => (
                <button
                  key={level}
                  type="button"
                  className={`chip chip--button${learner.cefr === level ? " chip--active" : ""}`}
                  onClick={() => void saveLevel(level)}
                >
                  {level}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {creating ? (
          <div className="form">
            <label className="form__field">
              <span>Name</span>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Amir" />
            </label>
            <label className="form__field">
              <span>First language</span>
              <input
                value={nativeLang}
                onChange={(e) => setNativeLang(e.target.value)}
                placeholder="fa, ru, zh…"
              />
            </label>
            <label className="form__field">
              <span>Goals</span>
              <input
                value={goals}
                onChange={(e) => setGoals(e.target.value)}
                placeholder="Speak confidently at work"
              />
            </label>
            <div className="level-row">
              <span className="panel__label">Starting level</span>
              <div className="chips chips--tight">
                {LEVELS.map((level) => (
                  <button
                    key={level}
                    type="button"
                    className={`chip chip--button${cefr === level ? " chip--active" : ""}`}
                    onClick={() => setCefr(level)}
                  >
                    {level}
                  </button>
                ))}
              </div>
            </div>
            {formError ? <p className="form__error">{formError}</p> : null}
            <button type="button" className="btn btn--primary" onClick={() => void submit()}>
              Create profile
            </button>
          </div>
        ) : null}

        {learner ? (
          <div className="form form--compact">
            <label className="form__field">
              <span>Goals</span>
              <input
                value={goals || learner.goals}
                onChange={(e) => setGoals(e.target.value)}
                onBlur={() => void saveGoals()}
                placeholder="What do you want to be able to do?"
              />
            </label>
          </div>
        ) : null}
      </div>

      <div className="panel__section">
        <h2 className="panel__title">Session</h2>
        {session ? (
          <div className="session-card">
            <div>
              <span className="panel__label">Mode</span>
              <strong>{session.mode === "free" ? "Free conversation" : "Role-play"}</strong>
            </div>
            {session.scenario_slug ? (
              <div>
                <span className="panel__label">Scenario</span>
                <strong>{session.scenario_slug.replace(/-/g, " ")}</strong>
              </div>
            ) : null}
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() => void onEndSession()}
            >
              End session
            </button>
          </div>
        ) : (
          <div className="session-actions">
            <button
              type="button"
              className="btn btn--primary"
              disabled={!learner || busy}
              onClick={() => void onStartSession("free")}
            >
              Start free chat
            </button>
            <button
              type="button"
              className="btn"
              disabled={!learner || busy || !scenarioSlug}
              onClick={() => void onStartSession("scenario")}
            >
              Start role-play
            </button>
            <p className="panel__muted">
              Role-play needs a scenario. Pick one below; free chat ignores the choice.
            </p>
          </div>
        )}
      </div>

      <div className="panel__section">
        <h2 className="panel__title">Scenarios</h2>
        <div className="scenario-list">
          {scenarios.map((scenario) => (
            <button
              key={scenario.slug}
              type="button"
              disabled={Boolean(session)}
              className={`scenario${
                scenarioSlug === scenario.slug ? " scenario--active" : ""
              }`}
              onClick={() => onChooseScenario(scenario.slug)}
            >
              <span className="scenario__title">{scenario.title}</span>
              <span className="scenario__meta">
                {scenario.level} · {scenario.setting}
              </span>
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}