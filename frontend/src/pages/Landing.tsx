import { loginUrl } from '../lib/api';

const MODELS = [
  { id: 'llama3:8b',   verdict: 'ACCEPTED', sats: -5,   delta: '+0.4%' },
  { id: 'mistral:7b',  verdict: 'ACCEPTED', sats: -10,  delta: '+0.7%' },
  { id: 'gemma2:9b',   verdict: 'REJECTED', sats: -12,  delta: '-1.8%' },
  { id: 'gemini-pro',  verdict: 'ACCEPTED', sats: -150, delta: '+2.1%' },
];

const FEATURES = [
  { icon: '₿', title: 'Real sats, not credits',   body: 'Each review is a Lightning-style debit. Money actually moves. Theres no take-back.' },
  { icon: '⚖', title: 'Bad answers cost the model', body: 'A rejected finding is a refund to you, weighted against the model\'s reputation.' },
  { icon: '📈', title: 'The router learns',          body: 'Each accepted or rejected finding updates a per-tag classifier. Good models inherit the next chunk.' },
  { icon: '📉', title: 'Your bill compounds down',   body: 'Cheap models get a chance to prove themselves on easy hunks. Expensive ones earn the hard ones.' },
];

export default function Landing() {
  return (
    <div className="landing">
      {/* NAV */}
      <nav className="nav">
        <div className="nav-left">
          <a href="/" className="logo"><span className="logo-icon">⚡</span><span>Veri<span className="accent-text">Sync</span></span></a>
          <a href="#how" className="nav-link">How it works</a>
          <a href="#models" className="nav-link">Models</a>
          <a href="#pricing" className="nav-link">Pricing</a>
          <a href="/dashboard" className="nav-link">Dashboard</a>
        </div>
        <div className="nav-right">
          <a href="https://github.com/FilipDolejsi/VeriSync" target="_blank" rel="noreferrer" className="btn-outline">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>
            GitHub
          </a>
          <a href={loginUrl()} className="btn-primary">Sign in</a>
        </div>
      </nav>

      {/* HERO */}
      <section className="hero" id="how">
        <h1>
          The cheapest AI that can <em>actually</em> review<br/>
          your code, paid in <span className="sats-text">sats</span>.
        </h1>
        <p className="hero-sub">
          VeriSync is a GitHub webhook that cuts every push into pieces, sends each piece to the cheapest
          model that can reliably review it, and charges real Bitcoin per finding.
          Models that waste your budget lose traffic. The router learns. Your bill shrinks.
        </p>
        <div className="hero-actions">
          <a href={loginUrl()} className="btn-primary large">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>
            Connect a repository
          </a>
          <a href="#economics" className="btn-secondary large">⚡ Why money?</a>
        </div>
      </section>

      {/* ECONOMICS */}
      <section className="economics" id="economics">
        <div className="economics-left">
          <div className="section-label">THE MECHANISM</div>
          <h2>
            A model earns the right to charge more by{' '}
            <span className="purple-text">proving it wastes less</span> of your budget.
          </h2>
          <p>
            Reputation isn't a score we display. It's a multiplier on every future routing
            decision. Models that produce findings you accept keep getting picked. Models
            that get rejected pay for their mistake — in real sats — and slowly lose traffic.
          </p>
          <p>
            The result is a market where the core promise — save you money by routing
            intelligently — becomes mathematically honest. No vendor negotiation. No
            marketing. Just bids and outcomes.
          </p>

          <div className="model-table">
            <div className="model-table-head">
              <span>Model</span><span>Verdict</span><span>Sats</span><span>Rep Δ</span>
            </div>
            {MODELS.map(m => (
              <div key={m.id} className="model-table-row">
                <span className="mono">{m.id}</span>
                <span className={`verdict ${m.verdict === 'ACCEPTED' ? 'accepted' : 'rejected'}`}>{m.verdict}</span>
                <span className="mono sats-dim">{m.sats} sats</span>
                <span className={`mono ${m.verdict === 'ACCEPTED' ? 'pos' : 'neg'}`}>{m.delta}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="economics-right">
          {FEATURES.map(f => (
            <div key={f.title} className="feature-card">
              <div className="feature-icon">{f.icon}</div>
              <div>
                <div className="feature-title">{f.title}</div>
                <div className="feature-body">{f.body}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* FOOTER */}
      <footer className="footer">
        <span>© 2025 VeriSync · Built by Filip & Abdalaziz</span>
        <a href={loginUrl()} className="btn-primary">Get started →</a>
      </footer>
    </div>
  );
}
