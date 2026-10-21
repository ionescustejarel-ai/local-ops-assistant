import type { Backup, Container, Disk, Gpu, Service, Task } from "../types";
import { ago, gb, mib } from "../format";

const LABELS: Record<string, string> = {
  Ops_Backup: "Backup zilnic 21:00",
  Ops_Reranker: "Reranker :8009",
  Ops_Dashboard_UI: "Tablou web :8011",
  Ops_Daily_Report: "Raport zilnic",
  Ops_Price_Feed: "Flux de prețuri",
  Ops_Nightly_Sync: "Sincronizare nocturnă",
  Ops_News_Digest: "Rezumat știri",
  Ops_Precheck: "Verificare dimineața",
  Ops_Reference_Data: "Date de referință",
  Ops_Price_Snapshot: "Instantaneu prețuri",
  Ops_Daily_Ingest: "Ingest zilnic",
  Ops_Closing_Capture: "Captură de închidere",
  Jarvis_Backend: "Jarvis backend :8020",
  Jarvis_App: "Jarvis fereastră",
};

function taskRowClass(t: Task): string {
  if (!t.result_ok || t.log?.failed) return "bad";
  if (t.stale || t.state === "Disabled") return "warn";
  return "";
}

export function Tasks({ tasks, now }: { tasks: Task[]; now: number }) {
  return (
    <section className="panel">
      <div className="panel-head"><h2>Task-uri programate</h2><span className="meta">{tasks.length}</span></div>
      <table>
        <tbody>
          {tasks.map((t) => (
            <tr key={t.name} className={taskRowClass(t)} title={`${t.name}\n${t.result_text} ${t.result_hex ?? ""}\n${t.log?.summary ?? ""}`}>
              <td>{LABELS[t.name] ?? t.name}</td>
              <td className="sub">{!t.result_ok ? "eșuat" : t.state === "Running" ? "rulează" : t.log ? (t.log.failed ? "eroare" : t.log.idle ? "idle" : "ok") : "ok"}</td>
              <td className="num muted">{ago(t.last_run, now)}</td>
              <td className="num muted">{t.next_run ? ago(t.next_run, now) : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export function Services({ services, docker }: { services: Service[]; docker: Container[] }) {
  const watched = docker.filter((c) => c.watched !== false && c.image !== null);
  const others = docker.length - watched.length;
  return (
    <section className="panel">
      <div className="panel-head"><h2>Servicii</h2></div>
      <div className="row">
        {services.map((s) => (
          <span key={s.name} title={`${s.url}\n${s.error ?? s.status ?? ""} ${s.latency_ms} ms`}>
            <i className={`dot ${s.ok ? "" : "bad"}`} />{s.name}
          </span>
        ))}
      </div>
      <div className="row" style={{ marginTop: 6 }}>
        <span className="muted">docker</span>
        {watched.map((c) => (
          <span key={c.name} title={`${c.image ?? ""}\n${c.status}`}><i className={`dot ${c.ok ? "" : "bad"}`} />{c.name}</span>
        ))}
        {others > 0 ? <span className="muted">+{others} oprite</span> : null}
      </div>
    </section>
  );
}

export function Machine({ gpus, disks, backup, now }: { gpus: Gpu[]; disks: Disk[]; backup?: Backup; now: number }) {
  return (
    <section className="panel">
      <div className="panel-head"><h2>Mașina</h2></div>
      <div className="kv">
        {gpus.map((g) => (
          <>
            <b key={`g${g.index}`}>GPU {g.index}</b>
            <div key={`gv${g.index}`}>
              <span>{mib(g.mem_used_mib)} / {mib(g.mem_total_mib)}</span> <span className="muted">· {g.util_pct ?? "—"}% · {g.temp_c ?? "—"}°</span>
              <div className={`bar ${g.mem_pct > 90 ? "hot" : ""}`}><i style={{ width: `${g.mem_pct}%` }} /></div>
            </div>
          </>
        ))}
        {disks.map((d) => (
          <>
            <b key={`d${d.path}`}>{d.path.replace("/", "")}</b>
            <div key={`dv${d.path}`}>
              {d.error ? <span className="muted">{d.error}</span> : <><span>{gb(d.free_gb)} liberi</span> <span className="muted">· {d.used_pct}% folosit</span></>}
            </div>
          </>
        ))}
        <b>Backup</b>
        <div>
          {!backup ? <span className="muted">—</span>
            : !backup.mounted ? <span style={{ color: "var(--red)" }}>Drive nemontat</span>
            : backup.error ? <span style={{ color: "var(--amber)" }}>{backup.error}</span>
            : <>
                <span style={{ color: backup.status === "OK" ? undefined : "var(--red)" }}>{backup.status}</span>
                <span className="muted"> · {ago(backup.run_at, now)}</span>
                {backup.warnings?.length ? <div className="sub">{backup.warnings.length} avertismente</div> : null}
              </>}
        </div>
      </div>
    </section>
  );
}
