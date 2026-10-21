import type { Pending as PendingItem } from "../types";

export function Pending({ items }: { items: PendingItem[] }) {
  const mine = items.filter((p) => p.type === "decizie");
  const others = items.filter((p) => p.type !== "decizie");
  return (
    <section className="panel">
      <div className="panel-head"><h2>Aștept</h2><span className="meta">{mine.length} de la tine · {others.length} de la alții</span></div>
      {items.length === 0 ? <div className="muted">Nimic în așteptare. Sesiunile scriu aici la final (_inbox/pending.yaml).</div> : null}
      <div className="pending">
        {items.map((p) => (
          <div key={p.id} className={`pend ${p.severity}`} title={[p.from ? `de la: ${p.from}` : "", p.blocks ? `blochează: ${p.blocks}` : "", p.since ? `din ${p.since}` : ""].filter(Boolean).join("\n")}>
            <span className={`who ${p.type === "decizie" ? "me" : ""}`}>{p.type === "decizie" ? "tu" : (p.from ?? "alții").split(" ")[0].slice(0, 12)}</span>
            <span className="txt"><span className="proj">{p.project}</span> {p.text}</span>
            <span className="age">{p.age_days == null ? "" : p.age_days === 0 ? "azi" : `${p.age_days} z`}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
