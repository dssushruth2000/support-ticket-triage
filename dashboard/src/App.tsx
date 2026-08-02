import { useEffect, useState } from "react";
import { fetchRecent, fetchSummary, type MetricsSummary, type RecentTicket } from "./api";

function pct(n: number) {
  return `${(n * 100).toFixed(1)}%`;
}

function money(n: number) {
  return `$${n.toFixed(4)}`;
}

function BarRow({ label, value, max }: { label: string; value: number; max: number }) {
  const width = max > 0 ? Math.max(4, (value / max) * 100) : 0;
  return (
    <div className="bar-row">
      <span className="bar-label">{label}</span>
      <div className="bar-track">
        <div className="bar-fill" style={{ width: `${width}%` }} />
      </div>
      <span className="bar-value">{value}</span>
    </div>
  );
}

export default function App() {
  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const [recent, setRecent] = useState<RecentTicket[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [s, r] = await Promise.all([fetchSummary(), fetchRecent(20)]);
      setSummary(s);
      setRecent(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 15000);
    return () => window.clearInterval(id);
  }, []);

  const catEntries = Object.entries(summary?.by_category ?? {}).sort((a, b) => b[1] - a[1]);
  const catMax = catEntries[0]?.[1] ?? 0;

  return (
    <div className="page">
      <header className="hero">
        <p className="brand">Support Triage</p>
        <h1>Observability</h1>
        <p className="lede">
          Cost, routing mix, and escalation health across triaged tickets.
        </p>
        <button type="button" className="refresh" onClick={() => void load()} disabled={loading}>
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </header>

      {error && (
        <p className="error">
          Could not reach the API ({error}). Start the backend with{" "}
          <code>uvicorn app.api.main:app --reload</code>.
        </p>
      )}

      {summary && (
        <section className="kpis" aria-label="Key metrics">
          <article>
            <h2>Tickets</h2>
            <p className="kpi">{summary.ticket_count}</p>
          </article>
          <article>
            <h2>Avg cost</h2>
            <p className="kpi">{money(summary.avg_cost_usd)}</p>
            <p className="sub">total {money(summary.total_cost_usd)}</p>
          </article>
          <article>
            <h2>Escalation</h2>
            <p className="kpi">{pct(summary.escalation_rate)}</p>
            <p className="sub">auto {pct(summary.auto_respond_rate)}</p>
          </article>
          <article>
            <h2>Routing</h2>
            <p className="kpi">{pct(summary.cheap_tier_share)} cheap</p>
            <p className="sub">{pct(summary.strong_tier_share)} strong</p>
          </article>
          <article>
            <h2>Avg latency</h2>
            <p className="kpi">{Math.round(summary.avg_latency_ms)} ms</p>
          </article>
        </section>
      )}

      <div className="grid">
        <section className="panel">
          <h2>By category</h2>
          {catEntries.length === 0 ? (
            <p className="empty">No tickets yet — POST /tickets or run the CLI.</p>
          ) : (
            catEntries.map(([label, value]) => (
              <BarRow key={label} label={label} value={value} max={catMax} />
            ))
          )}
        </section>

        <section className="panel">
          <h2>Recent tickets</h2>
          {recent.length === 0 ? (
            <p className="empty">Nothing to show yet.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Subject</th>
                  <th>Category</th>
                  <th>Action</th>
                  <th>Tier</th>
                  <th>Cost</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((t) => (
                  <tr key={t.id}>
                    <td>{t.id}</td>
                    <td className="subject">{t.subject}</td>
                    <td>{t.category ?? "—"}</td>
                    <td>{t.action ?? "—"}</td>
                    <td>
                      <span className={`tier tier-${t.model_tier ?? "none"}`}>
                        {t.model_tier ?? "—"}
                      </span>
                    </td>
                    <td>{money(t.cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </div>
  );
}
