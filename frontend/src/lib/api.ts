export const API = import.meta.env.VITE_API_URL ?? 'https://verisync-j5em.onrender.com';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw Object.assign(new Error(err.detail ?? 'API error'), { status: res.status });
  }
  return res.json();
}

export const api = {
  me:        ()                     => request<User>('/auth/me'),
  history:   (limit = 20)           => request<PR[]>(`/api/history?limit=${limit}`),
  analytics: ()                     => request<Analytics>('/api/analytics'),
  repos:     ()                     => request<Repo[]>('/api/repos'),
  watch:     (repos: string[])      => request('/repos/watch', { method: 'POST', body: JSON.stringify({ repos }) }),
  unwatch:   (repo: string)         => request(`/repos/unwatch?repo_full_name=${encodeURIComponent(repo)}`, { method: 'POST' }),
  logout:    ()                     => request('/auth/logout', { method: 'POST' }),
};

export function loginUrl(redirect?: string): string {
  const r = redirect ? `?redirect=${encodeURIComponent(redirect)}` : '';
  return `${API}/auth/login${r}`;
}

export function sseUrl(): string {
  return `${API}/events`;
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface User {
  id: string;
  login: string;
  name: string;
  avatar_url: string;
  sat_balance: number;
}

export interface PR {
  id: string;
  repo_full_name: string;
  pr_number: number | null;
  pr_title: string | null;
  pr_url: string | null;
  status: string;
  total_cost_sats: number;
  started_at: string;
  finding_count: number;
  chunk_count: number;
}

export interface ModelSpend {
  model_id: string;
  total_sats: number;
  chunk_count: number;
}

export interface Analytics {
  spend_by_model: ModelSpend[];
  findings_by_severity: Record<string, number>;
  totals: {
    total_prs: number;
    total_spent: number;
    verifier_pass_rate: number;
  };
  router: Record<string, unknown>;
}

export interface Repo {
  full_name: string;
  private: boolean;
}

export type EventType =
  | 'chunk_started' | 'model_selected' | 'sat_spent'
  | 'finding_found' | 'chunk_done' | 'review_complete'
  | 'router_retrained' | 'error';

export interface VSEvent {
  type: EventType;
  [key: string]: unknown;
}
