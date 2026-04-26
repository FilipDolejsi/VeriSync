import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useSSE, FeedEvent } from '../hooks/useSSE';
import { api, Analytics, PR } from '../lib/api';
import Nav from '../components/Nav';

const TAG_COLORS: Record<string, string> = {
  chunk_started:   '#818cf8',
  model_selected:  '#a78bfa',
  sat_spent:       '#f59e0b',
  finding_found:   '#ef4444',
  chunk_done:      '#10b981',
  review_complete: '#22d3ee',
  error:           '#f87171',
};

const TAG_LABELS: Record<string, string> = {
  chunk_started:   'CHUNK',
  model_selected:  'ROUTE',
  sat_spent:       'WALLET',
  finding_found:   'FINDING',
  chunk_done:      'REPORT',
  review_complete: 'DONE',
};

function eventText(ev: FeedEvent): string {
  switch (ev.type) {
    case 'chunk_started':   return `${ev.file as string}  [${ev.tag as string}]`;
    case 'model_selected':  return `→ ${ev.model_id as string}  ${ev.cost_sats as number} sats  conf ${Math.round((ev.confidence as number ?? 0) * 100)}%`;
    case 'sat_spent':       return `−${ev.amount as number} sats  bal: ${(ev.new_balance as number).toLocaleString()}`;
    case 'finding_found':   return `${(ev.severity as string).toUpperCase()} · ${ev.description as string}`;
    case 'chunk_done':      return `${ev.finding_count as number} finding(s)  ${ev.cost_sats as number} sats`;
    case 'review_complete': return `Review complete  ${ev.total_cost as number} sats  🔴${ev.critical as number} ⚠${ev.warning as number}`;
    default:                return JSON.stringify(ev);
  }
}

export default function Dashboard() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const { events, live } = useSSE(!!user);

  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [history,   setHistory]   = useState<PR[]>([]);
  const [balance,   setBalance]   = useState<number>(0);

  useEffect(() => { if (!loading && !user) navigate('/'); }, [user, loading]);

  useEffect(() => {
    if (!user) return;
    setBalance(user.sat_balance);
    api.analytics().then(setAnalytics).catch(() => {});
    api.history(15).then(setHistory).catch(() => {});
  }, [user]);

  // Update balance from SSE
  useEffect(() => {
    const last = events.find(e => e.type === 'sat_spent');
    if (last) setBalance(last.new_balance as number);
    const done = events[0];
    if (done?.type === 'review_complete') {
      api.analytics().then(setAnalytics).catch(() => {});
      api.history(15).then(setHistory).catch(() => {});
    }
  }, [events]);

  if (loading) return <div className="loader">Loading…</div>;
  if (!user)   return null;

  const totals      = analytics?.totals;
  const byModel     = analytics?.spend_by_model ?? [];
  const bySeverity  = analytics?.findings_by_severity ?? {};
  const maxSats     = Math.max(...byModel.map(m => m.total_sats), 1);

  return (
    <div className="page">
      <Nav page="dashboard" />

      <main className="dashboard-main">
        {/* ── Stats ── */}
        <div className="stats-row">
          <StatCard label="SAT BALANCE"    value={balance.toLocaleString()} color="#f59e0b" />
          <StatCard label="REVIEWS TODAY"  value={String(totals?.total_prs ?? 0)} color="#e2e4ed" />
          <StatCard label="AVG COST / PR"  value={totals?.total_prs
            ? `${Math.round((totals.total_spent ?? 0) / totals.total_prs)} sats`
            : '— sats'} color="#e2e4ed" />
        </div>

        <div className="dashboard-cols">
          {/* ── Live feed ── */}
          <div className="card feed-card">
            <div className="card-head">
              <span className="card-label">LIVE EVENT STREAM</span>
              <span className={`live-pill ${live ? 'on' : ''}`}>
                {live ? '● LIVE' : '○ IDLE'}
              </span>
            </div>
            <div className="feed">
              {events.length === 0 ? (
                <div className="feed-empty">Waiting for a review to start…</div>
              ) : events.map((ev, i) => (
                <div key={i} className="feed-row">
                  <span className="feed-ts">{ev.ts}</span>
                  <span className="feed-tag" style={{ background: TAG_COLORS[ev.type] + '22', color: TAG_COLORS[ev.type] }}>
                    {TAG_LABELS[ev.type] ?? ev.type.toUpperCase()}
                  </span>
                  <span className="feed-text">{eventText(ev)}</span>
                </div>
              ))}
            </div>
          </div>

          {/* ── Findings by model ── */}
          <div className="card model-card">
            <div className="card-label" style={{ marginBottom: 20 }}>FINDINGS BY MODEL</div>
            {byModel.length === 0 ? (
              <div className="empty-state">No reviews yet</div>
            ) : byModel.map(m => (
              <div key={m.model_id} className="model-row">
                <span className="model-name">{m.model_id}</span>
                <div className="model-bar-wrap">
                  <div className="model-bar" style={{ width: `${(m.total_sats / maxSats) * 100}%` }} />
                </div>
                <span className="model-cost">⚡ {m.total_sats}</span>
              </div>
            ))}
          </div>
        </div>

        {/* ── PR history ── */}
        <div className="card">
          <div className="card-label" style={{ marginBottom: 16 }}>PULL REQUEST HISTORY</div>
          {history.length === 0 ? (
            <div className="empty-state">No pull requests reviewed yet. Connect a repo and push some code.</div>
          ) : (
            <table className="pr-table">
              <thead>
                <tr><th>Pull request</th><th>Repo</th><th>Findings</th><th>Cost</th><th>Status</th><th>Time</th></tr>
              </thead>
              <tbody>
                {history.map(pr => (
                  <tr key={pr.id}>
                    <td className="pr-title">{pr.pr_title ?? `PR #${pr.pr_number}`}</td>
                    <td className="mono dim">{pr.repo_full_name}</td>
                    <td>
                      {pr.finding_count > 0
                        ? <span className="badge-red">{pr.finding_count} findings</span>
                        : <span className="badge-green">clean</span>}
                    </td>
                    <td className="mono amber">⚡ {pr.total_cost_sats}</td>
                    <td className={`status-${pr.status}`}>{pr.status}</td>
                    <td className="dim mono">{(pr.started_at ?? '').slice(0, 16)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </main>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={{ color }}>{value}</div>
    </div>
  );
}
