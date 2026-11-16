# Emma — a local voice English tutor with a 2D character

Emma is a single-user, fully local web app. You hold a push-to-talk conversation with an
animated character; she understands your speech, answers out loud with a mouth driven by her
own audio, and corrects you without stopping the conversation.

Everything runs on your machine: **FastAPI** + **LlamaIndex** + **Ollama** + **Postgres**,
speech via **faster-whisper** and **Piper**, UI in **React + Vite**. No cloud audio, no API
keys required unless you opt into OpenRouter.

---

## What v1 does

- Push-to-talk conversation, turn based (no VAD, no barge-in)
- Streaming replies: tokens are spoken sentence by sentence as they close
- Inline **recast** plus a per-turn **correction card** (said → fixed, category, why, severity)
- Error categories: **grammar**, **word choice**, **naturalness** (pronunciation is deferred)
- Named learner profiles with CEFR level, first language and goals — Emma adapts to them
- Retrieval over a starter curriculum **and** the learner's own recurring mistakes
- Free conversation **or** a scenario role-play
- Fully swappable LLM layer: local Ollama (default) or OpenRouter

Deferred on purpose: pronunciation scoring, spaced repetition, vocabulary trainer, progress
dashboard, barge-in / echo cancellation, mobile layout, password auth, extra characters.

---

## Requirements

| Tool | Version | Notes |
|---|---|---|
| Python | 3.11+ | 3.12 recommended |
| Node | 20+ | 22 works |
| uv | any recent | dependency + venv manager |
| Ollama | 0.3+ | with `qwen3:14b` and `bge-m3` pulled |
| Postgres | 14+ with pgvector | optional — SQLite is a supported fallback |
| Piper voice | `en_US-lessac-medium` | downloaded once |

---

## Quick start

### 1. Backend

```powershell
cd backend
uv sync --extra dev --extra tts
copy ..\.env.example .env          # PowerShell
# cp ../.env.example .env         # bash
```

### 2. Models and voice

```powershell
ollama pull qwen3:14b
ollama pull bge-m3
uv run python -m piper.download_voices en_US-lessac-medium --data-dir ..\models
```

### 3. Database

Either start Postgres with pgvector:

```powershell
docker compose up -d db            # from the repo root
```

or point `DATABASE_URL` at an existing server. Then create the schema:

```powershell
uv run alembic upgrade head
```

If you skip Postgres entirely, set `DATABASE_URL` to a SQLite URL and the app creates its own
schema at startup:

```
DATABASE_URL=sqlite+aiosqlite:///./emma.sqlite3
```

### 4. Frontend

```powershell
cd frontend
npm install
npm run build
```

### 5. Run

```powershell
cd backend
uv run uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. FastAPI serves the built SPA and the API on the same origin.

For frontend work with hot reload, run both:

```powershell
uv run uvicorn app.main:app --reload          # terminal 1
cd frontend; npm run dev                       # terminal 2, http://127.0.0.1:5173
```

Vite proxies `/api` to `127.0.0.1:8000`, so no CORS dance is needed.

---

## First turn

1. In the right panel, create a learner profile (name, level, first language, goals).
2. Pick a scenario, or start a free chat.
3. Hold **space** (or the mic button), speak, release.
4. Emma answers out loud. A correction card appears under her reply if anything needed fixing.

**No microphone?** Type in the box under the conversation and press Enter. It takes exactly the
same path as speech minus the transcription step — the turn is stored with `audio_ms: 0` and
Emma still replies out loud. Useful on a desktop without a mic, or when you want to think
before committing a sentence.

Manual acceptance check: say *"Yesterday I go to the store and I buy some milk."* Emma's reply
should contain **"went"** and **"bought"** as a silent recast, and the card should list
`go → went` and `buy → bought` as `grammar` / `major`. Say something already correct and the
card should be empty — Emma never invents an error to fill it.

---

## Configuration

All settings live in `.env` (see `.env.example` for the full list).

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://…/emma` | SQLAlchemy async URL. `sqlite+aiosqlite:///…` works. |
| `LLM_PROVIDER` | `ollama` | `ollama` or `openrouter` |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | `qwen3:14b` | Chat model |
| `OPENROUTER_*` | — | Only used when `LLM_PROVIDER=openrouter` |
| `STT_BACKEND` | `whisper` | `whisper` or `fake` (tests / scripted demos) |
| `WHISPER_MODEL` | `small.en` | Size name, or a **local directory** for offline models |
| `WHISPER_DEVICE` / `WHISPER_COMPUTE_TYPE` | `cpu` / `int8` | Kept on CPU so the GPU stays free for the LLM |
| `WHISPER_LOAD_TIMEOUT` | `120` | Seconds to wait for the first model load before failing with a hint |
| `TTS_BACKEND` | `piper` | `piper` or `fake` |
| `PIPER_MODEL` | `en_US-lessac-medium` | Any Piper voice you have downloaded |
| `PIPER_MODELS_DIR` | `models` | Where `.onnx` voices live |
| `EMBEDDING_MODEL` | `bge-m3` | 1024-dim, must match the `vector(1024)` column |
| `RAG_ENABLED` | `true` | `false` forces keyword retrieval only |
| `RAG_TOP_K` | `3` | Curriculum chunks per turn |
| `MAX_CORRECTIONS` | `3` | Hard cap on the correction card |
| `MAX_SPEAK_CHARS` | `220` | Soft cap on reply length |
| `HISTORY_TURNS` | `12` | Dialogue turns sent as context |

---

## Architecture

```
Browser (React + Vite)
  MediaRecorder (opus/webm) ──▶ decodeAudioData ──▶ 16 kHz mono WAV
                                                          │
                                             POST /api/turns
                                                          ▼
FastAPI
  audio/stt.py        faster-whisper (small.en, CPU int8)
  tutor/pipeline.py   context → stream → sentence split → speak
  llm/base.py         TutorLLM protocol
    llm/ollama.py       native /api/chat, think=false          (default)
    llm/openrouter.py   OpenAI-compatible streaming
  audio/tts.py        Piper per sentence → PCM 22.05 kHz
  rag/index.py        LlamaIndex PGVectorStore + bge-m3, keyword fallback
  db.py               async SQLAlchemy + Alembic
  routers/            health, learners, scenarios, sessions, turns, admin
                                                          │
                                             GET /api/turns/{id}/reply  (SSE)
                                                          ▼
  sentence deltas → sentence splitter → Piper → base64 PCM → playback queue
                                                          ▼
  Emma.tsx: mouth openness from PCM amplitude (~60 fps)
```

Two design notes worth knowing:

- **LlamaIndex is used for retrieval, not chat.** Its streaming abstraction is too coarse for
  token-level voice pacing, so the adapters stream raw tokens and a sentence splitter paces the
  speech.
- **One LLM protocol, two adapters.** `LLM_PROVIDER` switches between them; nothing else changes.

---

## HTTP surface

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/healthz` | liveness plus DB / LLM / STT / TTS / RAG flags |
| `GET/POST/PATCH` | `/api/learners` | named profiles |
| `GET` | `/api/scenarios` | scenario list, filterable with `?level=B1` |
| `GET/POST` | `/api/sessions` | list by `?learner_id=`, or start one |
| `GET` | `/api/sessions/{id}` | session with turns and corrections |
| `POST` | `/api/sessions/{id}/end` | close a session |
| `POST` | `/api/turns` | multipart WAV → `{turn_id, transcript, no_speech}` |
| `POST` | `/api/turns/text` | typed message (no mic needed) → same shape, `audio_ms: 0` |
| `GET` | `/api/turns/{id}/reply` | SSE reply stream |
| `POST` | `/api/turns/{id}/abandon` | stop generating, mark the turn abandoned |
| `POST` | `/api/admin/ingest` | re-ingest `content/` into pgvector |

### SSE events

```
event: meta        data: {"turn_id": 12, "reply_id": "turn-12"}
event: sentence    data: {"index": 0, "text": "Oh nice — so you went there on Sunday?"}
event: audio       data: {"index": 0, "seq": 0, "pcm_b64": "…", "sample_rate": 22050}
event: corrections data: {"items": [{"said": "…", "replacement": "…", "category": "grammar", "why": "…", "severity": "major"}]}
event: done        data: {"index": 0, "audio_ms": 1840}
event: error       data: {"code": "llm_unreachable", "message": "…"}
```

`audio` chunks are 16-bit little-endian mono PCM. Chunk sequence numbers are contiguous
within a sentence index, so the browser can schedule them back to back without gaps.

The model emits plain prose, then a sentinel line, then a JSON array of corrections:

```
<prose>

[[CORRECTIONS]]
[{"said":"Yesterday I go to the store","replacement":"Yesterday I went to the store",
  "category":"grammar","why":"Past time marker 'yesterday' needs past simple.","severity":"major"}]
```

The parser is deliberately lenient: a missing sentinel means no corrections, malformed JSON
keeps the reply and drops the card, `replacement == said` items are dropped, the list is capped
at three keeping the most severe, and any correction whose `said` is not traceable to the
learner's transcript is discarded. Emma is instructed to return `[]` for a correct sentence.

---

## Content

`content/` is the authored starter corpus: 12 grammar notes, 6 usage notes and 6 scenario
briefs. Each file is Markdown with a small header (`slug`, `title`, `kind`, `level`, plus
scenario fields). Drop in a new file and re-run ingest:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/admin/ingest
```

Retrieval is filtered to `level <= learner.cefr`, so a B1 learner never sees C1 notes. If
pgvector is unavailable, retrieval silently falls back to keyword search over the same table
and logs a warning — the app still boots.

---

## Tests and lint

```powershell
cd backend
uv run pytest -q
uv run ruff check .
```

The suite runs entirely on fakes — no Whisper, no Piper, no LLM:

- correction parser fixtures (clean prose, missing sentinel, truncated JSON, garbage,
  `replacement == said`, over-cap lists, ungrounded items)
- sentence splitter (abbreviations, `e.g.`, decimals, newlines, trailing fragments)
- learner isolation across sessions
- SSE framing and per-sentence chunk ordering
- full turn end to end through `TestClient` with scripted STT/LLM/TTS, rows verified in Postgres

Frontend:

```powershell
cd frontend
npm run typecheck
npm run build
```

---

## Failure modes

| Failure | Behaviour |
|---|---|
| Mic permission denied | Explicit UI error naming the padlock/site-settings fix; no hang. Typing still works. |
| Whisper returns nothing | `no_speech` → Emma asks you to repeat; no LLM call |
| Ollama down / model missing | `llm_unreachable` SSE event with the exact `ollama serve` / `ollama pull` steps; `healthz` flags it |
| Piper voice missing | Startup fails fast with the exact download command |
| pgvector missing | Keyword retrieval fallback, startup warning, app still works |
| Malformed correction JSON | Reply streams normally, card is dropped, warning logged |
| SSE client disconnects | Generation cancelled, `POST /abandon` marks the turn |
| AudioContext blocked | Header shows **Enable sound**; audio is queued while suspended and flushes on resume, never dropped |
| VRAM pressure (12 GB) | Whisper and Piper stay on CPU; the GPU is left to `qwen3:14b` |

---

## Troubleshooting

**`Could not load Whisper model 'small.en'`.** faster-whisper downloads on first use. If the
machine has no route to Hugging Face, download the CTranslate2 model elsewhere and point
`WHISPER_MODEL` at the local folder, e.g. `WHISPER_MODEL=D:\models\faster-whisper-small.en`.

**`Piper voice 'en_US-lessac-medium' is missing`.** Run
`uv run python -m piper.download_voices en_US-lessac-medium --data-dir models`.
Other voices: `en_US-lessac-high`, `en_US-amy-medium`, `en_GB-alba-medium`.

**`Ollama is unreachable`.** Start it with `ollama serve` (Windows: the Ollama tray app) and
check `ollama list` contains the configured model.

**No sound at all.** Browsers start an `AudioContext` in `suspended` state until the page sees a
user gesture. If the header shows **Enable sound**, click it once. The player also queues audio
while suspended and flushes it on resume, so a blocked context delays speech instead of dropping
it — but a page reload always needs one click before the first turn.

**Mic does nothing.** If the click produces an error banner, the message tells you which permission to fix.

**No corrections ever appear.** Check the raw reply: if the model skipped the `[[CORRECTIONS]]`
sentinel there is nothing to parse. That is handled, not an error.

---

## Deferred

Pronunciation scoring, spaced-repetition review, vocabulary trainer, progress dashboard,
barge-in and echo cancellation, mobile layout, multiple tutor characters, password auth,
hosted Postgres. Word-timestamp visemes are sketched but not wired up: the mouth is driven by
audio amplitude, which is the safe v1.