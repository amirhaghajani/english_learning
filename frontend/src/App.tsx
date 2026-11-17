import { useEffect, useMemo, useState } from "react";

import { Emma, type EmmaState } from "./components/Emma";
import { Composer } from "./components/Composer";
import { MicButton } from "./components/MicButton";
import { ProfilePanel } from "./components/ProfilePanel";
import { Transcript } from "./components/Transcript";
import { useConversation } from "./useConversation";

type View = "chat" | "settings";

function emmaStateFor(
  phase: string,
  hasCorrections: boolean,
  speaking: boolean,
): EmmaState {
  if (phase === "recording") return "listening";
  if (phase === "thinking") return "thinking";
  if (phase === "speaking") return hasCorrections ? "correcting" : "speaking";
  return speaking ? "speaking" : "idle";
}

const PHASE_LABEL: Record<string, string> = {
  recording: "Listening…",
  transcribing: "Transcribing…",
  thinking: "Thinking…",
  speaking: "Speaking…",
};

export default function App() {
  const convo = useConversation();
  const [view, setView] = useState<View>("chat");
  const [menuOpen, setMenuOpen] = useState(false);

  const lastTurnCorrections = useMemo(() => {
    const emma = [...convo.entries].reverse().find((entry) => entry.role === "emma");
    return (emma?.corrections.length ?? 0) > 0;
  }, [convo.entries]);

  const lastExchange = useMemo(() => {
    const emma = [...convo.entries].reverse().find((entry) => entry.role === "emma" && entry.text);
    const learner = [...convo.entries].reverse().find((entry) => entry.role === "learner");
    return { emma: emma?.text ?? "", learner: learner?.text ?? "" };
  }, [convo.entries]);

  const state = emmaStateFor(convo.phase, lastTurnCorrections, convo.isPlaying());
  const disabled = !convo.session || convo.phase !== "idle";
  const busy = convo.phase !== "idle";

  const healthLabel = !convo.health
    ? "checking…"
    : convo.health.status === "ok"
      ? `ok · ${convo.health.llm_model}`
      : `degraded · ${convo.health.llm_reachable ? "db" : "llm"}`;

  const goTo = (next: View) => {
    setView(next);
    setMenuOpen(false);
  };

  useEffect(() => {
    const query = window.matchMedia("(min-width: 721px)");
    const onChange = (event: MediaQueryListEvent) => {
      if (event.matches) {
        setView("chat");
        setMenuOpen(false);
      }
    };
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  return (
    <div className={`app app--${view}`}>
      <header className="topbar">
        {view === "chat" ? (
          <button
            type="button"
            className="icon-btn menu-btn"
            aria-label="Open menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <span aria-hidden="true">☰</span>
          </button>
        ) : (
          <button
            type="button"
            className="icon-btn"
            aria-label="Back to Emma"
            onClick={() => goTo("chat")}
          >
            <span aria-hidden="true">←</span>
          </button>
        )}

        <div className="brand">
          <span className="brand__name">Emma</span>
          <span className="brand__tag">
            {view === "settings" ? "Settings" : "American English tutor"}
          </span>
        </div>

        <div className="topbar__right">
          {convo.soundReady ? null : (
            <button
              type="button"
              className="health health--degraded"
              onClick={() => void convo.enableSound()}
              title="Browsers block audio until you interact. Click to unlock Emma's voice."
            >
              <span className="health__dot" aria-hidden="true" />
              Enable sound
            </button>
          )}
          <button
            type="button"
            className={`health health--${convo.health?.status ?? "unknown"}`}
            onClick={() => void convo.refreshHealth()}
            title={Object.entries(convo.health?.details ?? {})
              .map(([key, value]) => `${key}: ${value}`)
              .join("\n")}
          >
            <span className="health__dot" aria-hidden="true" />
            {healthLabel}
          </button>
        </div>
      </header>

      {convo.error ? (
        <div className="banner" role="alert">
          <span>{convo.error}</span>
          <div className="banner__actions">
            {convo.errorRetryable ? (
              <button type="button" className="btn btn--ghost" onClick={() => void convo.refreshHealth()}>
                Retry
              </button>
            ) : null}
            <button type="button" className="btn btn--ghost" onClick={() => convo.setError(null)}>
              Dismiss
            </button>
          </div>
        </div>
      ) : null}

      {view === "chat" ? (
        <main className="layout">
          <section className="stage">
            <Emma state={state} getAmplitude={convo.mouthAmplitude} />

            <div className="latest" aria-live="polite">
              {lastExchange.learner ? (
                <p className="latest__you">
                  <span className="latest__who">You</span>
                  {lastExchange.learner}
                </p>
              ) : null}
              <p className="latest__emma">
                <span className="latest__who">Emma</span>
                {lastExchange.emma || PHASE_LABEL[convo.phase] || ""}
              </p>
            </div>

            <MicButton
              phase={convo.phase}
              disabled={disabled}
              onStart={() => void convo.startRecording()}
              onStop={convo.stopRecording}
            />

            {convo.session && (convo.phase === "speaking" || convo.phase === "thinking") ? (
              <button
                type="button"
                className="btn btn--ghost btn--small stop-float"
                onClick={() => void convo.cancelReply()}
              >
                Stop Emma
              </button>
            ) : null}
          </section>

          <section className="chat">
            <Transcript entries={convo.entries} onReplay={(key) => void convo.replayAudio(key)} />
            <Composer disabled={disabled} onSend={convo.sendText} />
          </section>

          <ProfilePanel
            learners={convo.learners}
            learner={convo.learner}
            scenarios={convo.scenarios}
            scenarioSlug={convo.scenarioSlug}
            session={convo.session}
            onChooseLearner={convo.chooseLearner}
            onCreateLearner={convo.createLearner}
            onUpdateLearner={convo.updateLearner}
            onChooseScenario={convo.setScenarioSlug}
            onStartSession={convo.startSession}
            onEndSession={convo.endSession}
            busy={busy}
          />
        </main>
      ) : (
        <main className="settings">
          <ProfilePanel
            learners={convo.learners}
            learner={convo.learner}
            scenarios={convo.scenarios}
            scenarioSlug={convo.scenarioSlug}
            session={convo.session}
            onChooseLearner={convo.chooseLearner}
            onCreateLearner={convo.createLearner}
            onUpdateLearner={convo.updateLearner}
            onChooseScenario={convo.setScenarioSlug}
            onStartSession={convo.startSession}
            onEndSession={convo.endSession}
            busy={busy}
          />
        </main>
      )}

      {menuOpen ? (
        <>
          <div className="scrim" onClick={() => setMenuOpen(false)} />
          <nav className="drawer" aria-label="Menu">
            <button type="button" onClick={() => goTo("settings")}>
              Settings
            </button>
            <button
              type="button"
              onClick={() => {
                setMenuOpen(false);
                void convo.startSession("free");
              }}
            >
              New session
            </button>
            {convo.session ? (
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  void convo.endSession();
                }}
              >
                End session
              </button>
            ) : null}
            <button type="button" onClick={() => setMenuOpen(false)}>
              Close
            </button>
          </nav>
        </>
      ) : null}
    </div>
  );
}