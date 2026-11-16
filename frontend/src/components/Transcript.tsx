import { useEffect, useRef } from "react";

import type { ChatEntry } from "../useConversation";
import { CorrectionCard } from "./CorrectionCard";

interface TranscriptProps {
  entries: ChatEntry[];
  onReplay?: (audioKey: string) => void;
}

export function Transcript({ entries, onReplay }: TranscriptProps) {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [entries]);

  if (entries.length === 0) {
    return (
      <div className="transcript transcript--empty">
        <p>Hold the space bar, press the mic, or just type below.</p>
        <p className="transcript__hint">
          Emma listens, answers out loud, and quietly rewrites anything that would sound off.
        </p>
      </div>
    );
  }

  return (
    <div className="transcript">
      {entries.map((entry) => {
        const replayable = entry.role === "emma" && !!entry.audioKey;
        return (
          <div key={entry.key} className={`bubble bubble--${entry.role}`}>
            <div
              className={`bubble__body${replayable ? " bubble__body--replayable" : ""}`}
              role={replayable ? "button" : undefined}
              tabIndex={replayable ? 0 : undefined}
              title={replayable ? "Click to hear this again" : undefined}
              onClick={
                replayable && onReplay ? () => onReplay(entry.audioKey as string) : undefined
              }
              onKeyDown={
                replayable && onReplay
                  ? (event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onReplay(entry.audioKey as string);
                      }
                    }
                  : undefined
              }
            >
              {entry.text ? (
                <p className="bubble__text">{entry.text}</p>
              ) : (
                <p className="bubble__text bubble__text--pending">
                  <span className="dots" aria-label="thinking">
                    <i />
                    <i />
                    <i />
                  </span>
                </p>
              )}
              {entry.corrections.length > 0 ? <CorrectionCard items={entry.corrections} /> : null}
              {replayable ? (
                <span className="bubble__replay" aria-hidden="true">
                  <svg viewBox="0 0 24 24" width="13" height="13">
                    <path
                      d="M4 9v6h4l5 4V5L8 9H4z"
                      fill="currentColor"
                    />
                    <path
                      d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12"
                      stroke="currentColor"
                      strokeWidth="1.7"
                      strokeLinecap="round"
                      fill="none"
                    />
                  </svg>
                  Replay
                </span>
              ) : null}
            </div>
          </div>
        );
      })}
      <div ref={endRef} />
    </div>
  );
}