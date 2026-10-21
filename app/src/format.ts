/** Romanian, terse, tabular-friendly formatting helpers. */

export function ago(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "—";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "—";
  const s = Math.round((now - t) / 1000);
  if (s < 0) return inFuture(-s);
  if (s < 60) return "acum";
  if (s < 3600) return `${Math.round(s / 60)} min`;
  if (s < 86400) return `${(s / 3600).toFixed(s < 36000 ? 1 : 0)} h`;
  return `${Math.round(s / 86400)} z`;
}

function inFuture(s: number): string {
  if (s < 60) return "acum";
  if (s < 3600) return `în ${Math.round(s / 60)} min`;
  if (s < 86400) return `în ${(s / 3600).toFixed(1)} h`;
  return `în ${Math.round(s / 86400)} z`;
}

export function hhmm(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("ro-RO", { hour: "2-digit", minute: "2-digit" });
}

export function dayLabel(iso: string, today = new Date()): string {
  const d = new Date(iso);
  const t0 = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const diff = Math.round((new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime() - t0.getTime()) / 86400000);
  if (diff === 0) return "azi";
  if (diff === 1) return "mâine";
  return d.toLocaleDateString("ro-RO", { day: "2-digit", month: "2-digit" });
}

export function gb(n: number | undefined): string {
  if (n === undefined) return "—";
  return n >= 1000 ? `${(n / 1000).toFixed(1)} TB` : `${n} GB`;
}

export function mib(n: number): string {
  return n >= 1024 ? `${(n / 1024).toFixed(1)} GB` : `${n} MB`;
}

export function daysLeft(n: number): string {
  if (n < 0) return `depășit cu ${-n} z`;
  if (n === 0) return "azi";
  if (n === 1) return "mâine";
  return `${n} zile`;
}

export function money(usd: number | null | undefined): string {
  return usd == null ? "" : `${usd.toFixed(2)} $`;
}
