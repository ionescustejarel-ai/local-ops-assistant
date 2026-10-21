import type { CalEvent, Deadline, Gmail } from "../types";
import { dayLabel, daysLeft, hhmm } from "../format";

export function Today({ calendar, gmail, deadlines }: { calendar: CalEvent[] | null | undefined; gmail: Gmail | null | undefined; deadlines: Deadline[] }) {
  return (
    <section className="panel">
      <div className="panel-head"><h2>Azi și mâine</h2></div>
      <div className="today">
        <div>
          {calendar === null || calendar === undefined ? (
            <div className="unconfigured">Calendar neconfigurat. Pune adresa ICS privată în <code>config/secrets.yaml</code>.</div>
          ) : calendar.length === 0 ? (
            <div className="muted">Nimic în calendar.</div>
          ) : (
            <div className="list">
              {calendar.map((e) => (
                <div key={e.start + e.summary} className="item">
                  <span className="when">{dayLabel(e.start)} {e.all_day ? "" : hhmm(e.start)}</span>
                  <span>{e.summary}{e.location ? <span className="muted"> · {e.location}</span> : null}</span>
                </div>
              ))}
            </div>
          )}
          <div className="list" style={{ marginTop: 10 }}>
            {deadlines.map((d) => d.gate ? (
              <div key={d.label} className="deadline gate" title={d.condition ?? d.note ?? ""}>
                <span><span className="lock" aria-label="poartă">⊘</span> {d.label}</span>
                <span className="left">{d.days_left == null ? "condiție" : d.days_left <= 0 ? "deschisă" : `se deschide în ${d.days_left} z`}</span>
              </div>
            ) : (
              <div key={d.label} className={`deadline ${(d.days_left ?? 0) < 0 ? "over" : (d.days_left ?? 99) <= 3 ? "soon" : ""}`} title={d.note ?? ""}>
                <span>{d.label}</span>
                <span className="left">{daysLeft(d.days_left ?? 0)}</span>
              </div>
            ))}
          </div>
        </div>
        <div>
          {gmail === null || gmail === undefined ? (
            <div className="unconfigured">Email neconfigurat. Pune userul și parola de aplicație în <code>config/secrets.yaml</code>.</div>
          ) : (
            <>
              <div className="sub">{gmail.unread} necitite în {gmail.hours} h</div>
              <div className="list" style={{ marginTop: 4 }}>
                {gmail.items.slice(0, 8).map((m, i) => (
                  <div key={i} className="item" title={m.from}>
                    <span className="when">{m.date ? hhmm(m.date) : ""}</span>
                    <span><span className="muted">{m.from.replace(/<.*>/, "").trim().slice(0, 22)}</span> {m.subject}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
