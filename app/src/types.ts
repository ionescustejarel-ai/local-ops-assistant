export type Severity = "red" | "yellow" | "info";

export interface Alert { id: string; severity: Severity; text: string; source: string }

export interface TaskLog { started_utc?: string; idle: boolean; failed: boolean; summary: string; log?: string }
export interface Task {
  name: string; state: string; last_run: string | null; age_s: number | null; next_run: string | null;
  result_code: number | null; result_hex: string | null; result_ok: boolean; result_text: string;
  missed_runs: number; trigger: string | null; interval_s: number | null; stale: boolean; log: TaskLog | null;
}
export interface Container { name: string; image: string | null; status: string; up: boolean; health: string | null; ok: boolean; ports: string[]; watched?: boolean }
export interface Gpu { index: number; name: string; mem_used_mib: number; mem_total_mib: number; mem_pct: number; util_pct: number | null; temp_c: number | null }
export interface Service { name: string; url: string; ok: boolean; status: number | null; latency_ms: number; error: string | null; note?: string }
export interface Backup { root: string | null; mounted: boolean; error: string | null; run_at?: string | null; status?: string | null; failures?: string[]; warnings?: string[]; age_h?: number | null }
export interface Disk { path: string; total_gb?: number; free_gb?: number; used_pct?: number; error?: string }
export interface Repo { name: string; path: string; branch?: string; dirty?: number; changed?: string[]; last_commit?: { hash: string; date: string; subject: string }; last_commit_age_days?: number | null; error: string | null; alert_dirty?: boolean }
export interface ProjectMemory { name: string; path_hint: string | null; status_raw: string; next: string | null; blockers: string[]; rules: string[]; cautions: string[]; done: boolean }
export interface ProjectNote { last_session: string | null; last_session_title?: string | null; sessions?: number; next?: string | null; mtime?: string | null; error?: string }
export interface Project { key: string; label: string; repo: string | null; memory: ProjectMemory | null; note: ProjectNote | null; note_path: string | null; next: string | null }
export interface CalEvent { summary: string; start: string; end: string | null; all_day: boolean; location: string | null }
export interface Mail { from: string; subject: string; date: string | null }
export interface Gmail { unread: number; items: Mail[]; hours: number }
export interface Deadline { label: string; project: string | null; date: string | null; days_left: number | null; note: string | null; gate?: boolean; condition?: string | null }
export interface Pending { id: string; project: string | null; type: "decizie" | "așteptare"; text: string; since: string | null; age_days: number | null; from: string | null; blocks: string | null; severity: Severity }
export interface Vault { memory_md: string; bytes?: number; kb?: number; over_limit?: boolean; limit_kb?: number; mtime?: string; error: string | null }

export interface SnapshotData {
  tasks?: Task[]; docker?: Container[]; gpu?: Gpu[]; services?: Service[]; backup?: Backup; disk?: Disk[];
  git?: Repo[]; projects?: Project[]; calendar?: CalEvent[] | null; gmail?: Gmail | null; deadlines?: Deadline[];
  pending?: Pending[]; vault?: Vault;
}
export interface Snapshot {
  version: number; generated: string; data: SnapshotData;
  updated: Record<string, string>; errors: Record<string, string>; alerts: Alert[];
}

export type BrainEvent =
  | { type: "token"; text: string }
  | { type: "sentence"; text: string }
  | { type: "tool"; name: string }
  | { type: "done"; text: string; ok: boolean; cost_usd: number | null; duration_ms: number | null; first_token_ms: number | null; turns: number | null; error?: string | null }
  | { type: "error"; text: string };

export interface ChatTurn { role: "user" | "jarvis"; text: string; at: string; meta?: string }

declare global {
  interface Window {
    jarvis?: {
      onPttToggle: (cb: () => void) => () => void;
      info: () => Promise<{ hotkey: string; version: string; dev: boolean }>;
      token: () => Promise<string>;
      show: () => void;
    };
  }
}
