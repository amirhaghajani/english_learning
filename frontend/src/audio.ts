const TARGET_RATE = 16000;

let decodeContext: AudioContext | null = null;

function getDecodeContext(): AudioContext {
  if (!decodeContext) {
    const Ctor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    decodeContext = new Ctor();
  }
  return decodeContext;
}

function audioCtor(): typeof AudioContext {
  return (
    window.AudioContext ??
    (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
  );
}

export function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  const writeText = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i));
  };

  writeText(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeText(8, "WAVE");
  writeText(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeText(36, "data");
  view.setUint32(40, samples.length * 2, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
    offset += 2;
  }

  return new Blob([view], { type: "audio/wav" });
}

async function resampleToMono16k(buffer: AudioBuffer): Promise<Float32Array> {
  const frames = Math.max(1, Math.ceil(buffer.duration * TARGET_RATE));
  const offline = new OfflineAudioContext(1, frames, TARGET_RATE);
  const source = offline.createBufferSource();
  source.buffer = buffer;
  source.connect(offline.destination);
  source.start();
  const rendered = await offline.startRendering();
  return rendered.getChannelData(0).slice();
}

export async function blobToWav16k(blob: Blob): Promise<Blob> {
  const arrayBuffer = await blob.arrayBuffer();
  const decoded = await getDecodeContext().decodeAudioData(arrayBuffer.slice(0));
  const mono = await resampleToMono16k(decoded);
  return encodeWav(mono, TARGET_RATE);
}

interface PcmSentence {
  samples: Float32Array;
  sampleRate: number;
  resolve?: () => void;
}

const SENTENCE_GAP_S = 0.12;
const MAX_QUEUED_SENTENCES = 64;

export function mergeChunks(chunks: Int16Array[]): Int16Array {
  let total = 0;
  for (const chunk of chunks) total += chunk.length;

  const merged = new Int16Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }
  return merged;
}

export class PcmPlayer {
  private ctx: AudioContext | null = null;
  private gain: GainNode | null = null;
  private analyser: AnalyserNode | null = null;
  private bins = new Uint8Array(128);
  private volume = 0.9;
  private unlockArmed = false;

  private queue: PcmSentence[] = [];
  private current: AudioBufferSourceNode | null = null;
  private currentSentence: PcmSentence | null = null;
  private active = 0;
  private pumping = false;
  private stopped = false;
  private generation = 0;

  get state(): string {
    return this.ctx ? this.ctx.state : 'uninitialised';
  }

  get context(): AudioContext | null {
    return this.ctx;
  }

  private ensureGraph(): AudioContext {
    if (this.ctx && this.gain && this.analyser) return this.ctx;

    const ctx = new (audioCtor())({ latencyHint: 'interactive' });
    const gain = ctx.createGain();
    gain.gain.value = this.volume;

    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.5;

    gain.connect(analyser);
    analyser.connect(ctx.destination);

    this.ctx = ctx;
    this.gain = gain;
    this.analyser = analyser;
    this.bins = new Uint8Array(analyser.fftSize);

    ctx.onstatechange = () => {
      if (this.ctx && this.ctx.state === 'running') this.pump();
    };

    return ctx;
  }

  async resume(): Promise<void> {
    const ctx = this.ensureGraph();

    if (ctx.state !== 'running') {
      try {
        await ctx.resume();
      } catch {
        /* autoplay may still block; armUnlock retries on the next gesture */
      }
    }

    if (ctx.state !== 'running') {
      this.armUnlock();
      return;
    }

    this.pump();
  }

  private armUnlock(): void {
    if (this.unlockArmed || typeof window === 'undefined') return;
    this.unlockArmed = true;

    const unlock = () => {
      this.unlockArmed = false;
      window.removeEventListener('pointerdown', unlock);
      window.removeEventListener('keydown', unlock);
      const ctx = this.ctx;
      if (ctx && ctx.state !== 'running') {
        void ctx
          .resume()
          .then(() => this.pump())
          .catch(() => undefined);
      }
    };

    window.addEventListener('pointerdown', unlock);
    window.addEventListener('keydown', unlock);
  }

  setVolume(value: number): void {
    this.volume = Math.max(0, Math.min(1, value));
    if (this.gain) this.gain.gain.value = this.volume;
  }

  enqueueSentence(int16: Int16Array, sampleRate: number): Promise<void> {
    if (int16.length === 0 || sampleRate <= 0) return Promise.resolve();

    const samples = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i += 1) samples[i] = int16[i] / 32768;

    let settle: () => void = () => undefined;
    const finished = new Promise<void>((resolve) => {
      settle = resolve;
    });

    this.queue.push({ samples, sampleRate, resolve: settle });
    if (this.queue.length > MAX_QUEUED_SENTENCES) {
      const dropped = this.queue.splice(0, this.queue.length - MAX_QUEUED_SENTENCES);
      for (const item of dropped) item.resolve?.();
    }
    this.pump();
    return finished;
  }

  private pump(): void {
    if (this.pumping) return;
    const ctx = this.ctx;
    if (!ctx || ctx.state !== 'running') {
      void this.resume();
      return;
    }

    const generation = this.generation;
    this.pumping = true;
    this.stopped = false;

    void (async () => {
      try {
        while (this.queue.length > 0 && !this.stopped && generation === this.generation) {
          const sentence = this.queue.shift();
          if (!sentence) break;

          await this.play(sentence);
          if (this.queue.length > 0 && !this.stopped) {
            await new Promise((r) => setTimeout(r, SENTENCE_GAP_S * 1000));
          }
        }
      } finally {
        if (generation === this.generation) {
          this.pumping = false;
          if (this.queue.length > 0 && !this.stopped) this.pump();
        }
      }
    })();
  }

  private play(sentence: PcmSentence): Promise<void> {
    const ctx = this.ctx;
    const gain = this.gain;
    if (!ctx || !gain || ctx.state !== 'running') return Promise.resolve();

    return new Promise<void>((resolve) => {
      const buffer = ctx.createBuffer(1, sentence.samples.length, sentence.sampleRate);
      buffer.copyToChannel(new Float32Array(sentence.samples), 0);

      const source = ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(gain);

      this.current = source;
      this.currentSentence = sentence;
      this.active += 1;

      source.onended = () => {
        this.active = Math.max(0, this.active - 1);
        this.current = null;
        this.currentSentence = null;
        source.disconnect();
        resolve();
        sentence.resolve?.();
      };

      source.start();
    });
  }

  amplitude(): number {
    if (!this.analyser || this.active === 0) return 0;
    this.analyser.getByteTimeDomainData(this.bins);
    let sum = 0;
    for (let i = 0; i < this.bins.length; i += 1) {
      const value = (this.bins[i] - 128) / 128;
      sum += value * value;
    }
    return Math.min(1, Math.sqrt(sum / this.bins.length) * 4);
  }

  isPlaying(): boolean {
    return this.active > 0 || this.queue.length > 0 || this.pumping;
  }

  stopAll(): void {
    this.generation += 1;
    const queued = this.queue;
    this.queue = [];
    for (const item of queued) item.resolve?.();

    const current = this.current;
    const currentSentence = this.currentSentence;
    this.current = null;
    this.currentSentence = null;
    if (current) {
      try {
        current.onended = null;
        current.stop();
        current.disconnect();
      } catch {
        /* already stopped */
      }
    }
    currentSentence?.resolve?.();

    this.stopped = true;
    this.pumping = false;
    this.active = 0;
  }
}

export const player = new PcmPlayer();
