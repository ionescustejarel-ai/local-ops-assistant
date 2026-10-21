import { useEffect, useState } from "react";
import { subscribeSnapshot } from "./api";
import { AlertBar } from "./components/AlertBar";
import { Machine, Services, Tasks } from "./components/Infra";
import { Jarvis } from "./components/Jarvis";
import { Pending } from "./components/Pending";
import { Projects } from "./components/Projects";
import { Today } from "./components/Today";
import type { Snapshot } from "./types";

export default function App() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [connected, setConnected] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [hotkey, setHotkey] = useState("Ctrl+Alt+J");

  useEffect(() => subscribeSnapshot(setSnap, setConnected), []);
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 30000); return () => clearInterval(id); }, []);
  useEffect(() => { window.jarvis?.info().then((i) => setHotkey(i.hotkey.replace("Control", "Ctrl"))).catch(() => {}); }, []);

  const d = snap?.data ?? {};
  return (
    <div className="shell">
      <AlertBar alerts={snap?.alerts ?? []} connected={connected} generated={snap?.generated} />
      <main className="grid">
        <div className="col">
          <Tasks tasks={d.tasks ?? []} now={now} />
          <Services services={d.services ?? []} docker={d.docker ?? []} />
          <Machine gpus={d.gpu ?? []} disks={d.disk ?? []} backup={d.backup} now={now} />
        </div>
        <div className="col">
          <Pending items={d.pending ?? []} />
          <Projects projects={d.projects ?? []} repos={d.git ?? []} now={now} />
          <Today calendar={d.calendar} gmail={d.gmail} deadlines={d.deadlines ?? []} />
        </div>
        <div className="col">
          <Jarvis hotkey={hotkey} />
        </div>
      </main>
    </div>
  );
}
