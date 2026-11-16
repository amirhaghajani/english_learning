import { useEffect, useRef, useState } from "react";

export type EmmaState = "idle" | "listening" | "thinking" | "speaking" | "pleased" | "correcting";

interface EmmaProps {
  state: EmmaState;
  getAmplitude: () => number;
}

const MOUTH_CLOSED = 2.2;
const MOUTH_OPEN = 8.5;

const SKIN = "#f6c9a8";
const SKIN_SHADE = "#e0a684";
const HAIR = "#4a2b1d";
const HAIR_LIGHT = "#7a4a33";
const INK = "#3a2419";

export function Emma({ state, getAmplitude }: EmmaProps) {
  const mouthRef = useRef<SVGEllipseElement | null>(null);
  const [blinking, setBlinking] = useState(false);
  const smoothed = useRef(0);
  const lastFrame = useRef(0);

  useEffect(() => {
    let frame = 0;
    const tick = (time: number) => {
      const dt = Math.min(0.1, (time - lastFrame.current) / 1000 || 0.016);
      lastFrame.current = time;

      const target = state === "speaking" ? getAmplitude() : 0;
      smoothed.current += (target - smoothed.current) * Math.min(1, dt * 18);

      if (mouthRef.current) {
        const ry = MOUTH_CLOSED + (MOUTH_OPEN - MOUTH_CLOSED) * smoothed.current;
        mouthRef.current.setAttribute("ry", ry.toFixed(2));
        mouthRef.current.setAttribute("rx", (11 + smoothed.current * 3.5).toFixed(2));
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [state, getAmplitude]);

  useEffect(() => {
    let timer: number;
    const schedule = () => {
      timer = window.setTimeout(() => {
        setBlinking(true);
        window.setTimeout(() => setBlinking(false), 140);
        schedule();
      }, 2600 + Math.random() * 3200);
    };
    schedule();
    return () => window.clearTimeout(timer);
  }, []);

  const browLift = state === "thinking" ? -7 : state === "speaking" ? -2 : 0;
  const pupilShift = state === "listening" ? -1.6 : state === "thinking" ? 2.2 : 0;

  return (
    <div className={`emma emma--${state}`}>
      <svg viewBox="0 0 200 200" role="img" aria-label={`Emma is ${state}`}>
        <defs>
          <radialGradient id="emmaSkin" cx="48%" cy="32%" r="78%">
            <stop offset="0%" stopColor="#ffe3cd" />
            <stop offset="68%" stopColor={SKIN} />
            <stop offset="100%" stopColor={SKIN_SHADE} />
          </radialGradient>
          <linearGradient id="emmaHair" x1="0" y1="0" x2="0.35" y2="1">
            <stop offset="0%" stopColor={HAIR_LIGHT} />
            <stop offset="52%" stopColor={HAIR} />
            <stop offset="100%" stopColor="#33190f" />
          </linearGradient>
          <linearGradient id="emmaTop" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#4a7c9b" />
            <stop offset="100%" stopColor="#2b4c64" />
          </linearGradient>
        </defs>

        <g className="emma__bob">
          <path
            d="M100 40 C73 40 56 60 56 90 C56 104 58 116 60 126 L140 126 C142 116 144 104 144 90 C144 60 127 40 100 40 Z"
            fill="url(#emmaHair)"
          />

          <path d="M88 118 L88 156 C88 162 112 162 112 156 L112 118 Z" fill={SKIN} />
          <ellipse cx="100" cy="142" rx="13" ry="5.5" fill="#000" opacity="0.1" />

          <path
            d="M100 156 C82 156 64 163 56 176 C50 186 48 194 48 200 L152 200 C152 194 150 186 144 176 C136 163 118 156 100 156 Z"
            fill="url(#emmaTop)"
          />
          <path d="M86 158 C90 170 110 170 114 158 C112 176 88 176 86 158 Z" fill="#24404f" />

          <path
            d="M60 106 C56 122 55 140 57 155 C58 163 70 163 72 155 C75 139 75 121 73 106 Z"
            fill="url(#emmaHair)"
          />
          <path
            d="M140 106 C144 122 145 140 143 155 C142 163 130 163 128 155 C125 139 125 121 127 106 Z"
            fill="url(#emmaHair)"
          />

          <ellipse cx="67" cy="104" rx="6" ry="9" fill={SKIN} />
          <ellipse cx="133" cy="104" rx="6" ry="9" fill={SKIN} />
          <path
            d="M66.4 101 q3.4 3.2 0 6.4"
            stroke={SKIN_SHADE}
            strokeWidth="1.4"
            fill="none"
            strokeLinecap="round"
          />
          <path
            d="M133.6 101 q-3.4 3.2 0 6.4"
            stroke={SKIN_SHADE}
            strokeWidth="1.4"
            fill="none"
            strokeLinecap="round"
          />

          <ellipse cx="100" cy="96" rx="30" ry="38" fill="url(#emmaSkin)" />

          <g className="emma__brows" transform={`translate(0 ${browLift})`}>
            <path
              d="M78 86 C83 81.5 90 81.5 95 85"
              stroke={INK}
              strokeWidth="3.2"
              strokeLinecap="round"
              fill="none"
            />
            <path
              d="M105 85 C110 81.5 117 81.5 122 86"
              stroke={INK}
              strokeWidth="3.2"
              strokeLinecap="round"
              fill="none"
            />
          </g>

          <g className="emma__eyes" style={{ transform: `translateX(${pupilShift}px)` }}>
            <ellipse cx="85" cy="94" rx="8.4" ry={blinking ? 1.1 : 9} fill="#fff" />
            <ellipse cx="115" cy="94" rx="8.4" ry={blinking ? 1.1 : 9} fill="#fff" />

            <circle cx="85" cy="94.6" r={blinking ? 0.8 : 4.7} fill="#7a5334" />
            <circle cx="115" cy="94.6" r={blinking ? 0.8 : 4.7} fill="#7a5334" />
            <circle cx="85" cy="94.6" r={blinking ? 0.4 : 2.2} fill="#22150f" />
            <circle cx="115" cy="94.6" r={blinking ? 0.4 : 2.2} fill="#22150f" />
            <circle cx="86.8" cy="92.1" r={blinking ? 0 : 1.6} fill="#fff" opacity="0.92" />
            <circle cx="116.8" cy="92.1" r={blinking ? 0 : 1.6} fill="#fff" opacity="0.92" />

            {blinking ? null : (
              <>
                <path
                  d="M76.8 90.4 Q85 84.2 93.2 90.4"
                  stroke={INK}
                  strokeWidth="2.4"
                  strokeLinecap="round"
                  fill="none"
                />
                <path
                  d="M106.8 90.4 Q115 84.2 123.2 90.4"
                  stroke={INK}
                  strokeWidth="2.4"
                  strokeLinecap="round"
                  fill="none"
                />
                <path
                  d="M77 90.6 l-2.8 -2.2 M93 90.6 l2.8 -2.2"
                  stroke={INK}
                  strokeWidth="1.7"
                  strokeLinecap="round"
                />
                <path
                  d="M107 90.6 l-2.8 -2.2 M123 90.6 l2.8 -2.2"
                  stroke={INK}
                  strokeWidth="1.7"
                  strokeLinecap="round"
                />
              </>
            )}
          </g>

          <path
            d="M100 103 C102 108 103.4 111 99.6 112.2"
            stroke={SKIN_SHADE}
            strokeWidth="2.1"
            strokeLinecap="round"
            fill="none"
          />

          <ellipse cx="78" cy="114" rx="8.5" ry="4.5" fill="#ee9d8c" opacity="0.3" />
          <ellipse cx="122" cy="114" rx="8.5" ry="4.5" fill="#ee9d8c" opacity="0.3" />

          <ellipse
            ref={mouthRef}
            cx="100"
            cy="122"
            rx="11"
            ry={MOUTH_CLOSED}
            fill="#8d3b45"
            stroke="#a9525c"
            strokeWidth="1.5"
          />

          <path
            d="M56 76 C56 54 75 40 100 40 C125 40 144 54 144 76 C135 71 125 72 113 73 C101 74 93 67 85 70 C77 72 65 78 56 76 Z"
            fill="url(#emmaHair)"
          />
          <path
            d="M76 56 C86 49 98 47 108 50"
            stroke={HAIR_LIGHT}
            strokeWidth="4.5"
            strokeLinecap="round"
            fill="none"
            opacity="0.55"
          />

          {state === "pleased" || state === "correcting" ? (
            <g className="emma__cheeks" opacity="0.5">
              <ellipse cx="75" cy="112" rx="8" ry="4.4" fill="#f2a08f" />
              <ellipse cx="125" cy="112" rx="8" ry="4.4" fill="#f2a08f" />
            </g>
          ) : null}
        </g>
      </svg>

      <div className="emma__label" aria-live="polite">
        {state === "listening"
          ? "Listening…"
          : state === "thinking"
            ? "Thinking…"
            : state === "speaking"
              ? "Speaking…"
              : state === "pleased"
                ? "Nice one!"
                : state === "correcting"
                  ? "Let me rephrase that…"
                  : "Ready"}
      </div>
    </div>
  );
}