import type { Project, Repo } from "../types";
import { ago } from "../format";

export function Projects({ projects, repos, now }: { projects: Project[]; repos: Repo[]; now: number }) {
  const byRepo = new Map(repos.map((r) => [r.name, r]));
  const withNext = projects.filter((p) => p.next || p.memory?.blockers.length);
  const quiet = projects.filter((p) => !p.next && !p.memory?.blockers.length);
  return (
    <section className="panel">
      <div className="panel-head"><h2>Proiecte</h2><span className="meta">{withNext.length} cu pas următor · {quiet.length} liniștite</span></div>
      <div className="projects">
        {withNext.map((p) => {
          const repo = p.repo ? byRepo.get(p.repo) : undefined;
          const blocked = (p.memory?.blockers.length ?? 0) > 0;
          return (
            <article key={p.key} className={`project ${blocked ? "blocked" : ""}`} title={p.memory?.status_raw}>
              <div className="name">
                <span>{p.label}</span>
                <span className="sess">{p.note?.last_session ? `sesiune ${p.note.last_session.slice(5).replace("-", ".")}` : ""}</span>
              </div>
              {p.next ? <div className="next">{p.next}</div> : null}
              {p.memory?.blockers.map((b) => <div key={b} className="block">Blocant: {b}</div>)}
              {repo && !repo.error ? (
                <div className="git" title={repo.changed?.length ? repo.changed.join("\n") : undefined}>
                  {repo.branch} · {repo.dirty ? <span className="dirty">{repo.dirty} necomise</span> : "curat"} · commit {ago(repo.last_commit?.date, now)}
                  {repo.changed?.length && (repo.dirty ?? 0) <= 6 ? <div className="files">{repo.changed.map((f) => f.split("/").pop()).join(", ")}</div> : null}
                </div>
              ) : null}
            </article>
          );
        })}
      </div>
      {quiet.length ? <div className="sub" style={{ marginTop: 8 }}>Fără pas următor: {quiet.map((p) => p.label).join(", ")}</div> : null}
    </section>
  );
}
