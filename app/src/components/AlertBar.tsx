import type { Alert } from "../types";

const MAX_CHIPS = 6;

export function AlertBar({ alerts, connected, generated }: { alerts: Alert[]; connected: boolean; generated?: string }) {
  const shown = alerts.filter((a) => a.severity !== "info");
  const hidden = shown.length - MAX_CHIPS;
  const infos = alerts.length - shown.length;
  return (
    <header className="alerts" role="status" aria-live="polite">
      <div className="brand"><span>Jarvis</span></div>
      {shown.length === 0 ? <span className="empty">Nicio alertă. Totul rulează.</span> : null}
      {shown.slice(0, MAX_CHIPS).map((a) => (
        <span key={a.id} className={`chip ${a.severity}`} title={`${a.source}: ${a.text}`}>{a.text}</span>
      ))}
      {hidden > 0 ? <span className="more">+{hidden}</span> : null}
      {infos > 0 ? <span className="more" title="detalii în panouri">{infos} note</span> : null}
      <span className={`conn ${connected ? "" : "off"}`}>
        {connected ? `actualizat ${generated ? generated.slice(11, 19) : ""}` : "backend deconectat — pornește jarvis.server"}
      </span>
    </header>
  );
}
