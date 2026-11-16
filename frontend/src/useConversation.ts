import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  type CEFR,
  type CorrectionItem,
  type Health,
  type Learner,
  type Scenario,
  type Session,
  type TurnAccepted,
  api,
  decodePcm,
  streamReply,
  streamSse,
} from "./api";
import { blobToWav16k, mergeChunks, player } from "./audio";

export type Phase = "idle" | "recording" | "transcribing" | "thinking" | "speaking";

export interface ChatEntry {
  key: string;
  role: "learner" | "emma";
  text: string;
  corrections: CorrectionItem[];
  pending: boolean;
  audioKey?: string;
}

function pickMimeType(): string {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/mp4",
  ];
  for (const mime of candidates) {
    if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(mime)) return mime;
  }
  return "";
}

function micErrorMessage(err: unknown): string {
  const name = (err as { name?: string })?.name ?? "";
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "Microphone access was blocked. Allow it in your browser's site settings (the padlock next to the address) and try again.";
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return "No microphone was found. Connect one and press the mic button again.";
  }
  if (name === "NotReadableError") {
    return "The microphone is busy in another application. Close it and try again.";
  }
  return err instanceof Error ? err.message : "Could not start recording.";
}

export function useConversation() {
  const [health, setHealth] = useState<Health | null>(null);
  const [learners, setLearners] = useState<Learner[]>([]);
  const [learner, setLearner] = useState<Learner | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioSlug, setScenarioSlug] = useState<string | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [booted, setBooted] = useState(false);
  const [soundReady, setSoundReady] = useState(false);
  const [errorRetryable, setErrorRetryable] = useState(true);

  const phaseRef = useRef<Phase>("idle");
  const sessionRef = useRef<Session | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const emmaKeyRef = useRef<string | null>(null);
  const audioRef = useRef<Map<number, { chunks: Int16Array[]; rate: number }>>(new Map());
  const lastAudioRef = useRef<number>(-1);
  const audioCacheRef = useRef<Map<string, { chunks: Int16Array[]; rate: number }>>(new Map());
  const currentAudioKeyRef = useRef<string | null>(null);

  const reportError = useCallback((message: string) => {
    setError(message);
    setErrorRetryable(true);
  }, []);

  const setPhaseSafe = useCallback((next: Phase) => {
    phaseRef.current = next;
    setPhase(next);
  }, []);

  useEffect(() => {
    sessionRef.current = session;
  }, [session]);

  const refreshHealth = useCallback(async () => {
    try {
      setHealth(await api.health());
    } catch (err) {
      setHealth(null);
      reportError(err instanceof Error ? err.message : "backend unreachable");
    }
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const [healthData, learnerRows, scenarioRows] = await Promise.all([
          api.health(),
          api.listLearners(),
          api.listScenarios(),
        ]);
        setHealth(healthData);
        setLearners(learnerRows);
        setScenarios(scenarioRows);
        if (learnerRows.length > 0) setLearner(learnerRows[0]);
      } catch (err) {
        reportError(err instanceof ApiError ? err.message : "Could not reach the tutor backend.");
      } finally {
        setBooted(true);
      }
    })();
  }, []);

  const createLearner = useCallback(
    async (input: { name: string; cefr: CEFR; native_lang: string; goals: string }) => {
      const created = await api.createLearner(input);
      setLearners((prev) => [...prev, created]);
      setLearner(created);
      return created;
    },
    [],
  );

  const updateLearner = useCallback(
    async (input: { name?: string; cefr?: CEFR; native_lang?: string; goals?: string }) => {
      if (!learner) return null;
      const updated = await api.updateLearner(learner.id, input);
      setLearner(updated);
      setLearners((prev) => prev.map((row) => (row.id === updated.id ? updated : row)));
      return updated;
    },
    [learner],
  );

  const chooseLearner = useCallback((next: Learner) => {
    setLearner(next);
  }, []);

  const endSession = useCallback(async () => {
    if (session) {
      try {
        await api.endSession(session.id);
      } catch {
        /* ending is best-effort */
      }
    }
    setSession(null);
    setEntries([]);
    setPhaseSafe("idle");
  }, [session, setPhaseSafe]);

  const appendEmma = useCallback((key: string, text: string, corrections: CorrectionItem[] = []) => {
    setEntries((prev) => {
      const index = prev.findIndex((entry) => entry.key === key);
      if (index === -1) {
        return [...prev, { key, role: "emma", text, corrections, pending: true }];
      }
      const next = [...prev];
      const entry = next[index];
      next[index] = {
        ...entry,
        text: entry.text ? `${entry.text}\n${text}` : text,
        corrections: corrections.length > 0 ? corrections : entry.corrections,
        pending: false,
      };
      return next;
    });
  }, []);

  const ensureAudio = useCallback(async () => {
    try {
      await player.resume();
      setSoundReady(player.state === "running");
    } catch {
      setSoundReady(false);
    }
  }, []);

  const resetAudio = useCallback(() => {
    audioRef.current = new Map();
    lastAudioRef.current = -1;
  }, []);

  const flushAudio = useCallback((index: number) => {
    const entry = audioRef.current.get(index);
    audioRef.current.delete(index);
    if (!entry || entry.chunks.length === 0) return;
    player.enqueueSentence(mergeChunks(entry.chunks), entry.rate);
  }, []);

  const handleAudio = useCallback(
    (index: number, pcmB64: string, rate: number) => {
      const samples = decodePcm(pcmB64);

      const key = currentAudioKeyRef.current;
      if (key) {
        const cached = audioCacheRef.current.get(key) ?? { chunks: [] as Int16Array[], rate };
        cached.rate = rate;
        cached.chunks.push(samples);
        audioCacheRef.current.set(key, cached);
      }

      const existing = audioRef.current.get(index);
      const entry = existing ?? { chunks: [] as Int16Array[], rate };
      entry.rate = rate;
      entry.chunks.push(samples);
      audioRef.current.set(index, entry);

      const previous = lastAudioRef.current;
      if (previous !== -1 && previous !== index) flushAudio(previous);
      lastAudioRef.current = index;
    },
    [flushAudio],
  );

  const replayAudio = useCallback(
    async (key: string) => {
      const entry = audioCacheRef.current.get(key);
      if (!entry || entry.chunks.length === 0) return;
      if (phaseRef.current !== "idle") return;

      await ensureAudio();
      player.stopAll();
      setPhaseSafe("speaking");
      try {
        await player.enqueueSentence(mergeChunks(entry.chunks), entry.rate);
      } finally {
        setPhaseSafe("idle");
      }
    },
    [ensureAudio, setPhaseSafe],
  );

  const waitForPlayback = useCallback(async (maxMs = 60000) => {
    await new Promise((r) => setTimeout(r, 60));
    const deadline = Date.now() + maxMs;
    while (player.isPlaying() && Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 100));
    }
  }, []);

  const speakOpening = useCallback(
    async (slug: string, key: string) => {
      resetAudio();
      currentAudioKeyRef.current = key;
      try {
        await ensureAudio();
        setPhaseSafe("speaking");
        await streamSse(`/api/scenarios/${encodeURIComponent(slug)}/opening`, {
          onAudio: ({ index, pcm_b64, sample_rate }) => {
            handleAudio(index, pcm_b64, sample_rate);
          },
          onError: ({ code, message }) => {
            player.stopAll();
            reportError(message);
            setErrorRetryable(code !== "not_found");
            setPhaseSafe("idle");
          },
        });
        await waitForPlayback();
      } catch {
        setPhaseSafe("idle");
      } finally {
        if (lastAudioRef.current !== -1) flushAudio(lastAudioRef.current);
        lastAudioRef.current = -1;
        setPhaseSafe("idle");
      }
    },
    [
      ensureAudio,
      flushAudio,
      handleAudio,
      reportError,
      resetAudio,
      setPhaseSafe,
      waitForPlayback,
    ],
  );

  const startSession = useCallback(
    async (mode: "free" | "scenario") => {
      if (!learner) return null;
      const created = await api.createSession({
        learner_id: learner.id,
        mode,
        scenario_slug: mode === "scenario" ? scenarioSlug : null,
      });
      setSession(created);
      setEntries([]);
      setError(null);
      setScenarioSlug(mode === "scenario" ? scenarioSlug : null);

      if (mode === "scenario" && created.scenario_slug) {
        const scenario = scenarios.find((row) => row.slug === created.scenario_slug);
        if (scenario?.opening_line) {
          const key = `opening-${created.id}`;
          setEntries([
            {
              key,
              role: "emma",
              text: scenario.opening_line,
              corrections: [],
              pending: false,
              audioKey: key,
            },
          ]);
          void speakOpening(created.scenario_slug, key);
        }
      }
      return created;
    },
    [learner, scenarioSlug, scenarios, speakOpening],
  );

  const runTurn = useCallback(
    async (accepted: TurnAccepted) => {
      await ensureAudio();
      resetAudio();

      const emmaKey = `turn-${accepted.turn_id}`;
      currentAudioKeyRef.current = emmaKey;
      emmaKeyRef.current = emmaKey;
      setEntries((prev) => [
        ...prev,
        {
          key: `learner-${accepted.turn_id}`,
          role: "learner",
          text: accepted.transcript || "(nothing heard)",
          corrections: [],
          pending: false,
        },
        {
          key: emmaKey,
          role: "emma",
          text: "",
          corrections: [],
          pending: true,
          audioKey: emmaKey,
        },
      ]);

      setPhaseSafe("thinking");
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        await streamReply(
          accepted.turn_id,
          {
            onSentence: ({ text }) => {
              setPhaseSafe("speaking");
              appendEmma(emmaKey, text);
            },
            onAudio: ({ index, pcm_b64, sample_rate }) => {
              handleAudio(index, pcm_b64, sample_rate);
            },
            onCorrections: ({ items }) => {
              setEntries((prev) => {
                const next = [...prev];
                const index = next.findIndex((entry) => entry.key === emmaKey);
                if (index !== -1) next[index] = { ...next[index], corrections: items };
                return next;
              });
            },
            onDone: () => {
              if (lastAudioRef.current !== -1) flushAudio(lastAudioRef.current);
              lastAudioRef.current = -1;
              setPhaseSafe("idle");
            },
            onError: ({ code, message }) => {
              if (lastAudioRef.current !== -1) flushAudio(lastAudioRef.current);
              lastAudioRef.current = -1;
              setError(message);
              setErrorRetryable(code !== "not_found");
              if (code === "not_found") {
                setSession(null);
                setEntries([]);
              }
              setPhaseSafe("idle");
            },
          },
          controller.signal,
        );
      } catch (err) {
        if ((err as { name?: string })?.name !== "AbortError") {
          reportError(err instanceof Error ? err.message : "The tutor failed to answer.");
        }
      } finally {
        if (lastAudioRef.current !== -1) flushAudio(lastAudioRef.current);
        lastAudioRef.current = -1;
        setPhaseSafe("idle");
      }
    },
    [appendEmma, ensureAudio, flushAudio, handleAudio, resetAudio, setPhaseSafe],
  );

  const finishRecording = useCallback(async () => {
    const active = sessionRef.current;
    if (!active) return;

    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;

    const type = recorderRef.current?.mimeType || chunksRef.current[0]?.type || "audio/webm";
    const blob = new Blob(chunksRef.current, { type });
    chunksRef.current = [];
    if (blob.size === 0) {
      reportError("That recording was empty. Hold the mic a little longer and try again.");
      setPhaseSafe("idle");
      return;
    }

    setPhaseSafe("transcribing");
    try {
      const wav = await blobToWav16k(blob);
      const accepted = await api.sendTurn(active.id, wav);
      await runTurn(accepted);
    } catch (err) {
      reportError(err instanceof Error ? err.message : "The tutor failed to answer.");
      setPhaseSafe("idle");
    }
  }, [runTurn, setPhaseSafe]);

  const sendText = useCallback(
    async (raw: string) => {
      const active = sessionRef.current;
      const text = raw.trim();
      if (!active || !text || phaseRef.current !== "idle") return false;

      setError(null);
      void ensureAudio();
      player.stopAll();
      try {
        const accepted = await api.sendTurnText(active.id, text);
        await runTurn(accepted);
        return true;
      } catch (err) {
        reportError(err instanceof Error ? err.message : "The tutor failed to answer.");
        setPhaseSafe("idle");
        return false;
      }
    },
    [ensureAudio, runTurn, setPhaseSafe],
  );

  const startRecording = useCallback(async () => {
    if (!sessionRef.current || phaseRef.current !== "idle") return;
    setError(null);

    try {
      await ensureAudio();
      player.stopAll();

      if (!navigator.mediaDevices?.getUserMedia) {
        reportError("This browser cannot record audio. Try a recent Chrome, Edge, Firefox or Safari.");
        return;
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
        },
      });
      streamRef.current = stream;

      const mimeType = pickMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        void finishRecording();
      };
      recorder.start();
      recorderRef.current = recorder;
      setPhaseSafe("recording");
    } catch (err) {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      reportError(micErrorMessage(err));
      setPhaseSafe("idle");
    }
  }, [ensureAudio, finishRecording, setPhaseSafe]);

  const stopRecording = useCallback(() => {
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
      recorderRef.current = null;
    }
    setPhaseSafe("transcribing");
  }, [setPhaseSafe]);

  const stopEverything = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.onstop = null;
      recorder.stop();
    }
    recorderRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    player.stopAll();
    setPhaseSafe("idle");
  }, [setPhaseSafe]);

  const cancelReply = useCallback(async () => {
    abortRef.current?.abort();
    abortRef.current = null;
    const key = emmaKeyRef.current;
    if (key) {
      const turnId = Number(key.replace("turn-", ""));
      if (!Number.isNaN(turnId)) {
        try {
          await api.abandonTurn(turnId);
        } catch {
          /* best effort */
        }
      }
    }
    player.stopAll();
    setPhaseSafe("idle");
  }, [setPhaseSafe]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.code !== "Space" || event.repeat) return;
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      event.preventDefault();
      void startRecording();
    };
    const onKeyUp = (event: KeyboardEvent) => {
      if (event.code !== "Space") return;
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      event.preventDefault();
      stopRecording();
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
  }, [startRecording, stopRecording]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  return {
    health,
    learners,
    learner,
    scenarios,
    scenarioSlug,
    setScenarioSlug,
    session,
    entries,
    phase,
    error,
    booted,
    setError,
    refreshHealth,
    createLearner,
    updateLearner,
    chooseLearner,
    startSession,
    endSession,
    startRecording,
    stopRecording,
    sendText,
    replayAudio,
    stopEverything,
    cancelReply,
    soundReady,
    enableSound: ensureAudio,
    errorRetryable,
    mouthAmplitude: () => player.amplitude(),
    isPlaying: () => player.isPlaying(),
  };
}