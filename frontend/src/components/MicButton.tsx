import type { Phase } from "../useConversation";

interface MicButtonProps {
  phase: Phase;
  disabled: boolean;
  onStart: () => void;
  onStop: () => void;
}

export function MicButton({ phase, disabled, onStart, onStop }: MicButtonProps) {
  const recording = phase === "recording";
  const busy = phase === "transcribing" || phase === "thinking";

  return (
    <div className="mic">
      <button
        type="button"
        className={`mic__button${recording ? " mic__button--live" : ""}`}
        disabled={disabled || busy}
        aria-label={recording ? "Stop recording" : "Hold to talk"}
        onPointerDown={(event) => {
          event.preventDefault();
          if (disabled || busy) return;
          try {
            event.currentTarget.setPointerCapture(event.pointerId);
          } catch {
            /* capture is a nicety; older browsers still get pointerup */
          }
          onStart();
        }}
        onPointerUp={(event) => {
          event.preventDefault();
          if (recording) onStop();
        }}
        onPointerCancel={() => {
          if (recording) onStop();
        }}
      >
        <svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true">
          <path
            d="M12 15a3.5 3.5 0 0 0 3.5-3.5V6a3.5 3.5 0 0 0-7 0v5.5A3.5 3.5 0 0 0 12 15z"
            fill="currentColor"
          />
          <path
            d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3.5"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            fill="none"
          />
        </svg>
      </button>
      <span className="mic__hint">
        {recording
          ? "Release to send"
          : busy
            ? phase === "transcribing"
              ? "Transcribing…"
              : "Emma is thinking…"
            : "Hold space, tap the mic, or type"}
      </span>
    </div>
  );
}