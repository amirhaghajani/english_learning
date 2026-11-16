import { useEffect, useRef } from "react";

import type { ChatEntry } from "../useConversation";
import { CorrectionCard } from "./CorrectionCard";

interface TranscriptProps {
  entries: ChatEntry[];
}

export function Transcript({ entries }: TranscriptProps) {
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
      {entries.map((entry) => (
        <div key={entry.key} className={`bubble bubble--${entry.role}`}>
          <div className="bubble__body">
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
          </div>
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}