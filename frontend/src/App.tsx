import { useMemo } from "react";

import { Emma, type EmmaState } from "./components/Emma";
import { Composer } from "./components/Composer";
import { MicButton } from "./components/MicButton";
import { ProfilePanel } from "./components/ProfilePanel";
import { Transcript } from "./components/Transcript";
import { useConversation } from "./useConversation";

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

export default function App() {
  const convo = useConversation();

  const lastTurnCorrections = useMemo(() => {
    const emma = [...convo.entries].reverse().find((entry) => entry.role === "emma");
    return (emma?.corrections.length ?? 0) > 0;
  }, [convo.entries]);

  const state = emmaStateFor(convo.phase, lastTurnCorrections, convo.isPlaying());
  const disabled = !convo.session || convo.phase !== "idle";

  const healthLabel = !convo.health
    ? "checking…"
    : convo.health.status === "ok"
      ? `ok · ${convo.health.llm_model}`
      : `degraded · ${convo.health.llm_reachable ? "db" : "llm"}`;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand__name">{convo.health ? "Emma" : "Emma"}</span>
          <span className="brand__tag">American English tutor</span>
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

      <main className="layout">
        <section className="stage">
          <Emma state={state} getAmplitude={convo.mouthAmplitude} />
          <MicButton
            phase={convo.phase}
            disabled={disabled}
            onStart={() => void convo.startRecording()}
            onStop={convo.stopRecording}
          />
          {convo.phase !== "idle" && convo.session ? (
            <button type="button" className="btn btn--ghost btn--small" onClick={() => void convo.cancelReply()}>
              Stop Emma
            </button>
          ) : null}
        </section>

        <section className="chat">
          <Transcript entries={convo.entries} onReplay={(id) => void convo.replayTurn(id)} />
          <Composer disabled={!convo.session || convo.phase !== "idle"} onSend={convo.sendText} />
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
          busy={convo.phase !== "idle"}
        />
      </main>
    </div>
  );
}