import type { BrainEvent, Snapshot } from "./types";

export const API = "http://127.0.0.1:8020";
const WS = "ws://127.0.0.1:8020/ws/events";

/** Per-launch backend token, read fresh each time (the backend may have restarted). */
async function token(): Promise<string> {
  try {
    return (await window.jarvis?.token()) ?? "";
  } catch {
    return "";
  }
}

async function authed(extra: Record<string, string> = {}): Promise<Record<string, string>> {
  return { ...extra, "X-Jarvis-Token": await token() };
}

/** Reconnecting WebSocket feed of the snapshot. Returns an unsubscribe function. */
export function subscribeSnapshot(onSnapshot: (s: Snapshot) => void, onStatus: (connected: boolean) => void): () => void {
  let ws: WebSocket | null = null;
  let closed = false;
  let retry = 1000;
  const connect = async () => {
    if (closed) return;
    // token as a subprotocol, not in the URL, so it stays out of the backend's access log
    ws = new WebSocket(WS, ["jarvis", `token.${await token()}`]);
    ws.onopen = () => { retry = 1000; onStatus(true); };
    ws.onmessage = (ev) => { try { onSnapshot(JSON.parse(ev.data) as Snapshot); } catch { /* ignore bad frame */ } };
    ws.onclose = () => { onStatus(false); if (!closed) { setTimeout(() => void connect(), retry); retry = Math.min(retry * 2, 15000); } };
    ws.onerror = () => ws?.close();
  };
  void connect();
  return () => { closed = true; ws?.close(); };
}

/** Parse a chunk of an SSE stream; returns complete events and the leftover buffer. */
export function parseSse(buffer: string): { events: BrainEvent[]; rest: string } {
  const events: BrainEvent[] = [];
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  for (const block of parts) {
    const dataLine = block.split("\n").find((l) => l.startsWith("data: "));
    if (!dataLine) continue;
    try { events.push(JSON.parse(dataLine.slice(6)) as BrainEvent); } catch { /* skip */ }
  }
  return { events, rest };
}

export async function* ask(text: string, newSession = false, signal?: AbortSignal): AsyncGenerator<BrainEvent> {
  const res = await fetch(`${API}/api/ask`, {
    method: "POST", headers: await authed({ "Content-Type": "application/json" }),
    body: JSON.stringify({ text, new_session: newSession }), signal,
  });
  if (!res.ok || !res.body) { yield { type: "error", text: `backend ${res.status}` }; return; }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const { events, rest } = parseSse(buf);
    buf = rest;
    for (const ev of events) yield ev;
  }
}

export async function transcribe(blob: Blob): Promise<{ text: string; took_s: number; audio_s: number }> {
  const fd = new FormData();
  fd.append("audio", blob, "ptt.webm");
  const res = await fetch(`${API}/api/stt`, { method: "POST", headers: await authed(), body: fd });
  if (!res.ok) throw new Error(`STT ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function synthesize(text: string): Promise<Blob> {
  const res = await fetch(`${API}/api/tts`, { method: "POST", headers: await authed({ "Content-Type": "application/json" }), body: JSON.stringify({ text }) });
  if (!res.ok) throw new Error(`TTS ${res.status}`);
  return res.blob();
}

export async function resetBrain(): Promise<void> {
  await fetch(`${API}/api/brain/reset`, { method: "POST", headers: await authed() });
}

export async function refresh(name?: string): Promise<void> {
  await fetch(`${API}/api/refresh${name ? `?name=${name}` : ""}`, { method: "POST", headers: await authed() });
}

/** Plays sentences in order; synthesis of the next sentence overlaps playback of the current one. */
export class SpeechQueue {
  private queue: Promise<Blob>[] = [];
  private playing = false;
  private current: HTMLAudioElement | null = null;
  muted = false;
  onState?: (speaking: boolean) => void;

  push(text: string): void {
    if (this.muted) return;
    this.queue.push(synthesize(text).catch(() => new Blob()));
    void this.drain();
  }

  stop(): void {
    this.queue = [];
    this.current?.pause();
    this.current = null;
    this.playing = false;
    this.onState?.(false);
  }

  private async drain(): Promise<void> {
    if (this.playing) return;
    this.playing = true;
    this.onState?.(true);
    while (this.queue.length) {
      const blob = await this.queue.shift()!;
      if (!blob.size) continue;
      await new Promise<void>((resolve) => {
        const url = URL.createObjectURL(blob);
        const a = new Audio(url);
        this.current = a;
        a.onended = a.onerror = () => { URL.revokeObjectURL(url); resolve(); };
        a.play().catch(() => resolve());
      });
    }
    this.playing = false;
    this.current = null;
    this.onState?.(false);
  }
}
