import { useCallback, useEffect, useRef, useState } from "react";
import { SpeechQueue, ask, resetBrain, transcribe } from "../api";
import { money } from "../format";
import type { ChatTurn } from "../types";

type Mode = "idle" | "listening" | "transcribing" | "thinking" | "speaking";

const LABEL: Record<Mode, string> = {
  idle: "Gata", listening: "Ascult", transcribing: "Transcriu", thinking: "Mă gândesc", speaking: "Vorbesc",
};

export function Jarvis({ hotkey }: { hotkey: string }) {
  const [mode, setMode] = useState<Mode>("idle");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [muted, setMuted] = useState(false);
  const speech = useRef(new SpeechQueue());
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const busy = useRef(false);
  const abort = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const orb = useRef<HTMLDivElement>(null);
  const meter = useRef<{ ctx: AudioContext; raf: number } | null>(null);

  /** Drive the orb's --lvl from the microphone while listening (no React re-renders). */
  const startMeter = (stream: MediaStream) => {
    try {
      const ctx = new AudioContext();
      const src = ctx.createMediaStreamSource(stream);
      const an = ctx.createAnalyser();
      an.fftSize = 512;
      src.connect(an);
      const buf = new Uint8Array(an.fftSize);
      let smooth = 0;
      const tick = () => {
        an.getByteTimeDomainData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) { const v = (buf[i] - 128) / 128; sum += v * v; }
        const rms = Math.sqrt(sum / buf.length);
        smooth = smooth * 0.7 + Math.min(1, rms * 4) * 0.3;
        orb.current?.style.setProperty("--lvl", smooth.toFixed(3));
        meter.current = { ctx, raf: requestAnimationFrame(tick) };
      };
      meter.current = { ctx, raf: requestAnimationFrame(tick) };
    } catch { /* no meter: orb just turns red */ }
  };
  const stopMeter = () => {
    if (meter.current) { cancelAnimationFrame(meter.current.raf); void meter.current.ctx.close(); meter.current = null; }
    orb.current?.style.setProperty("--lvl", "0");
  };

  useEffect(() => { speech.current.muted = muted; }, [muted]);
  useEffect(() => { bottom.current?.scrollIntoView({ block: "end" }); }, [turns]);

  const send = useCallback(async (text: string) => {
    if (!text.trim() || busy.current) return;
    busy.current = true;
    abort.current = new AbortController();
    const at = new Date().toISOString();
    setTurns((t) => [...t, { role: "user", text, at }, { role: "jarvis", text: "", at }]);
    setMode("thinking");
    let spoken = false;
    speech.current.onState = (s) => { if (s) setMode("speaking"); else if (!busy.current) setMode("idle"); };
    try {
      for await (const ev of ask(text, false, abort.current.signal)) {
        if (ev.type === "token") {
          setTurns((t) => { const c = [...t]; const last = { ...c[c.length - 1] }; last.text += ev.text; c[c.length - 1] = last; return c; });
        } else if (ev.type === "sentence") {
          spoken = true;
          speech.current.push(ev.text);
        } else if (ev.type === "tool") {
          setTurns((t) => { const c = [...t]; const last = { ...c[c.length - 1] }; last.meta = `citește: ${ev.name}`; c[c.length - 1] = last; return c; });
        } else if (ev.type === "done") {
          const meta = [ev.duration_ms ? `${(ev.duration_ms / 1000).toFixed(1)} s` : "", money(ev.cost_usd), ev.turns ? `${ev.turns} tură` : ""].filter(Boolean).join(" · ");
          setTurns((t) => { const c = [...t]; const last = { ...c[c.length - 1] }; if (!last.text) last.text = ev.text; last.meta = meta; c[c.length - 1] = last; return c; });
        } else if (ev.type === "error") {
          setTurns((t) => [...t, { role: "jarvis", text: `Eroare: ${ev.text}`, at, meta: "error" }]);
        }
      }
    } catch (e) {
      setTurns((t) => [...t, { role: "jarvis", text: `Eroare: ${(e as Error).message}`, at, meta: "error" }]);
    } finally {
      busy.current = false;
      if (!spoken || muted) setMode("idle");
    }
  }, [muted]);

  const startRecording = useCallback(async () => {
    if (mode !== "idle" || busy.current) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      const rec = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
      chunks.current = [];
      rec.ondataavailable = (e) => { if (e.data.size) chunks.current.push(e.data); };
      rec.onstop = async () => {
        stopMeter();
        stream.getTracks().forEach((t) => t.stop());
        setMode("transcribing");
        try {
          const blob = new Blob(chunks.current, { type: "audio/webm" });
          const r = await transcribe(blob);
          if (r.text.trim()) await send(r.text.trim());
          else { setTurns((t) => [...t, { role: "jarvis", text: "N-am auzit nimic.", at: new Date().toISOString(), meta: "error" }]); setMode("idle"); }
        } catch (e) {
          setTurns((t) => [...t, { role: "jarvis", text: `Eroare la transcriere: ${(e as Error).message}`, at: new Date().toISOString(), meta: "error" }]);
          setMode("idle");
        }
      };
      recorder.current = rec;
      rec.start();
      startMeter(stream);
      speech.current.stop();
      setMode("listening");
    } catch (e) {
      setTurns((t) => [...t, { role: "jarvis", text: `Microfonul nu e disponibil: ${(e as Error).message}`, at: new Date().toISOString(), meta: "error" }]);
    }
  }, [mode, send]);

  const stopRecording = useCallback(() => {
    if (recorder.current && recorder.current.state === "recording") recorder.current.stop();
  }, []);

  const toggle = useCallback(() => {
    if (mode === "listening") stopRecording();
    else if (mode === "speaking") { speech.current.stop(); setMode("idle"); }
    else void startRecording();
  }, [mode, startRecording, stopRecording]);

  useEffect(() => window.jarvis?.onPttToggle(toggle), [toggle]);

  const reset = async () => { speech.current.stop(); await resetBrain(); setTurns([]); setMode("idle"); };

  return (
    <div className="jarvis">
      <div className="head">
        <div ref={orb} className={`orb ${mode === "transcribing" ? "thinking" : mode}`} aria-hidden="true" />
        <div className="state">
          <b>{LABEL[mode]}</b>
          <span className="hint">{mode === "listening" ? "apasă din nou când ai terminat" : mode === "speaking" ? `${hotkey} ca să mă oprești` : `${hotkey} sau butonul de jos`}</span>
        </div>
        <div className="actions">
          <button onClick={() => setMuted((m) => !m)} aria-pressed={muted}>{muted ? "Voce oprită" : "Voce pornită"}</button>
          <button onClick={reset} title="Conversație nouă (sesiune Claude nouă)">Conversație nouă</button>
        </div>
      </div>
      <div className="transcript">
        {turns.length === 0 ? <div className="empty">Întreabă-mă ce ai de făcut azi, ce a rulat sau ce e roșu.</div> : null}
        {turns.map((t, i) => (
          <div key={i} className={`turn ${t.role} ${t.meta === "error" ? "error" : ""}`}>
            <div className="who">{t.role === "user" ? "tu" : "Jarvis"}</div>
            <div className="text">{t.text || (mode === "thinking" && i === turns.length - 1 ? "…" : "")}</div>
            {t.meta && t.meta !== "error" ? <div className="meta">{t.meta}</div> : null}
          </div>
        ))}
        <div ref={bottom} />
      </div>
      <form className="compose" onSubmit={(e) => { e.preventDefault(); const v = draft; setDraft(""); void send(v); }}>
        <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="sau scrie aici" aria-label="întrebare scrisă" />
        <button type="submit" disabled={!draft.trim() || mode !== "idle"}>Trimite</button>
      </form>
      <div style={{ padding: "0 14px 14px" }}>
        <button className={`ptt ${mode === "listening" ? "on" : ""}`} onClick={toggle} disabled={mode === "transcribing" || mode === "thinking"}>
          {mode === "listening" ? "Gata, trimite" : mode === "speaking" ? "Taci" : "Vorbește"}
        </button>
      </div>
    </div>
  );
}
