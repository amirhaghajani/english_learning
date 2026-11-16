export type CEFR = "A1" | "A2" | "B1" | "B2" | "C1";
export type SessionMode = "scenario" | "free";
export type CorrectionCategory = "grammar" | "word_choice" | "naturalness";
export type CorrectionSeverity = "minor" | "major";

export interface Learner {
  id: number;
  name: string;
  cefr: CEFR;
  native_lang: string;
  goals: string;
  created_at: string;
}

export interface Correction {
  id: number;
  turn_id: number;
  said: string;
  replacement: string;
  category: CorrectionCategory;
  why: string;
  severity: CorrectionSeverity;
}

export interface Turn {
  id: number;
  session_id: number;
  seq: number;
  transcript: string;
  reply_text: string;
  audio_ms: number;
  no_speech: boolean;
  abandoned: boolean;
  created_at: string;
  corrections: Correction[];
}

export interface Session {
  id: number;
  learner_id: number;
  mode: SessionMode;
  scenario_slug: string | null;
  started_at: string;
  ended_at: string | null;
  llm_provider: string | null;
  llm_model: string | null;
  turns: Turn[];
}

export interface Scenario {
  id: number;
  slug: string;
  title: string;
  level: string;
  setting: string;
  learner_role: string;
  emma_role: string;
  opening_line: string;
  target_language: string;
  success_criteria: string;
}

export interface TurnAccepted {
  turn_id: number;
  transcript: string;
  no_speech: boolean;
  audio_ms: number;
}

export interface Health {
  status: string;
  database: boolean;
  database_backend: string;
  llm_provider: string;
  llm_model: string;
  llm_reachable: boolean;
  stt_backend: string;
  stt_ready: boolean;
  tts_backend: string;
  tts_ready: boolean;
  rag_backend: string;
  details: Record<string, string>;
}

export interface CorrectionItem {
  said: string;
  replacement: string;
  category: CorrectionCategory;
  why: string;
  severity: CorrectionSeverity;
}

export type SseEvent =
  | { event: "meta"; data: { turn_id: number; reply_id: string } }
  | { event: "sentence"; data: { index: number; text: string } }
  | {
      event: "audio";
      data: { index: number; seq: number; pcm_b64: string; sample_rate: number; sentence: string };
    }
  | { event: "done"; data: { index: number; audio_ms: number } }
  | { event: "corrections"; data: { items: CorrectionItem[] } }
  | { event: "error"; data: { code: string; message: string } };

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(init?.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string") message = payload.detail;
      else if (payload.detail) message = JSON.stringify(payload.detail);
    } catch {
      /* keep the status text */
    }
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  health: () => request<Health>("/api/healthz"),

  listLearners: () => request<Learner[]>("/api/learners"),

  createLearner: (body: {
    name: string;
    cefr: CEFR;
    native_lang: string;
    goals: string;
  }) =>
    request<Learner>("/api/learners", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateLearner: (id: number, body: Partial<Pick<Learner, "name" | "cefr" | "native_lang" | "goals">>) =>
    request<Learner>(`/api/learners/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  listScenarios: () => request<Scenario[]>("/api/scenarios"),

  createSession: (body: { learner_id: number; mode: SessionMode; scenario_slug?: string | null }) =>
    request<Session>("/api/sessions", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getSession: (id: number, learnerId: number) =>
    request<Session>(`/api/sessions/${id}?learner_id=${learnerId}`),

  listSessions: (learnerId: number) =>
    request<Session[]>(`/api/sessions?learner_id=${learnerId}`),

  endSession: (id: number) =>
    request<Session>(`/api/sessions/${id}/end`, { method: "POST" }),

  sendTurn: (sessionId: number, wav: Blob) => {
    const form = new FormData();
    form.append("session_id", String(sessionId));
    form.append("file", wav, "turn.wav");
    return request<TurnAccepted>("/api/turns", { method: "POST", body: form });
  },

  sendTurnText: (sessionId: number, text: string) =>
    request<TurnAccepted>("/api/turns/text", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, text }),
    }),

  abandonTurn: (turnId: number) =>
    request<{ turn_id: number; abandoned: boolean }>(`/api/turns/${turnId}/abandon`, {
      method: "POST",
    }),

  ingest: () => request<{ documents: number; upserted: number; backend: string }>("/api/admin/ingest", {
    method: "POST",
  }),
};

function parseBlock(block: string): SseEvent | null {
  let event = "";
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!event) return null;
  try {
    const parsed = JSON.parse(data) as unknown;
    return { event, data: parsed } as SseEvent;
  } catch {
    return { event, data: {} } as SseEvent;
  }
}

export interface ReplyStreamHandlers {
  onMeta?: (data: { turn_id: number; reply_id: string }) => void;
  onSentence?: (data: { index: number; text: string }) => void;
  onAudio?: (data: { index: number; seq: number; pcm_b64: string; sample_rate: number; sentence: string }) => void;
  onDone?: (data: { index: number; audio_ms: number }) => void;
  onCorrections?: (data: { items: CorrectionItem[] }) => void;
  onError?: (data: { code: string; message: string }) => void;
}

export function decodePcm(base64: string): Int16Array {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  const view = new DataView(bytes.buffer);
  const samples = new Int16Array(bytes.length / 2);
  for (let i = 0; i < samples.length; i += 1) samples[i] = view.getInt16(i * 2, true);
  return samples;
}

export async function streamSse(
  url: string,
  handlers: ReplyStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(url, {
    signal,
    headers: { Accept: "text/event-stream" },
  });

  if (!response.ok || !response.body) {
    const detail = await response.text().catch(() => "");
    throw new ApiError(response.status, detail || `reply failed (${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const parsed = parseBlock(block);
      if (parsed) dispatch(parsed, handlers);
      boundary = buffer.indexOf("\n\n");
    }
  }

  if (buffer.trim()) {
    const parsed = parseBlock(buffer);
    if (parsed) dispatch(parsed, handlers);
  }
}

function dispatch(event: SseEvent, handlers: ReplyStreamHandlers): void {
  switch (event.event) {
    case "meta":
      handlers.onMeta?.(event.data);
      break;
    case "sentence":
      handlers.onSentence?.(event.data);
      break;
    case "audio":
      handlers.onAudio?.(event.data);
      break;
    case "done":
      handlers.onDone?.(event.data);
      break;
    case "corrections":
      handlers.onCorrections?.(event.data);
      break;
    case "error":
      handlers.onError?.(event.data);
      break;
    default:
      break;
  }
}

export function streamReply(
  turnId: number,
  handlers: ReplyStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  return streamSse("/api/turns/" + turnId + "/reply", handlers, signal);
}
