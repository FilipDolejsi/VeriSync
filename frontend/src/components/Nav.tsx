import { useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import { api, loginUrl } from '../lib/api';

interface NavProps { page?: 'dashboard' | 'docs' }

export default function Nav({ page }: NavProps) {
  const { user, logout } = useAuth();
  const [repos, setRepos]   = useState<{ full_name: string; private: boolean }[]>([]);
  const [open, setOpen]     = useState(false);

  const openRepos = async () => {
    if (!open) {
      const r = await api.repos().catch(() => []);
      setRepos(r);
    }
    setOpen(v => !v);
  };

  const watch = async (repo: string) => {
    await api.watch([repo]).catch(() => {});
    setOpen(false);
    window.location.reload();
  };

  return (
    <nav className="nav">
      <div className="nav-left">
        <a href="/" className="logo">
          <span className="logo-icon">⚡</span>
          <span>Veri<span className="accent-text">Sync</span></span>
        </a>
        <a href="/" className={`nav-link${!page ? ' active' : ''}`}>How it works</a>
        <a href="/dashboard" className={`nav-link${page === 'dashboard' ? ' active' : ''}`}>Dashboard</a>
      </div>
      <div className="nav-right">
        {user ? (
          <>
            <div className="balance-chip">
              <span>⚡</span>
              <span id="satBalance">{user.sat_balance.toLocaleString()}</span>
              <span className="dim-text">sats</span>
            </div>
            <div style={{ position: 'relative' }}>
              <button className="btn-outline" onClick={openRepos}>+ Watch repo</button>
              {open && repos.length > 0 && (
                <div className="repo-dropdown">
                  {repos.map(r => (
                    <button key={r.full_name} className="repo-item" onClick={() => watch(r.full_name)}>
                      {r.full_name} {r.private && '🔒'}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="user-chip">
              <img src={user.avatar_url} alt="" className="avatar" />
              <span className="dim-text">{user.login}</span>
              <button className="btn-ghost" onClick={logout}>Sign out</button>
            </div>
          </>
        ) : (
          <a href={loginUrl(window.location.href)} className="btn-primary">
            <GithubIcon />
            Sign in
          </a>
        )}
      </div>
    </nav>
  );
}

function GithubIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/>
    </svg>
  );
}
