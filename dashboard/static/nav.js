// Shared bootstrap — included by every authenticated page

function updateRepoSelectLabel(watchedCount) {
  const sel = document.getElementById('repoSel');
  if (!sel || !sel.options.length) return;
  const base = 'Watch a repo…';
  sel.options[0].textContent = watchedCount > 0 ? `${base} (${watchedCount} watching)` : base;
}


function renderRepoOptions(repos, watchedSet) {
  const sel = document.getElementById('repoSel');
  if (!sel) return;

  sel.innerHTML = '<option value="">Watch a repo…</option>';
  repos.forEach(repo => {
    const watched = watchedSet.has(repo.full_name);
    const o = document.createElement('option');
    o.value = repo.full_name;
    o.textContent = `${repo.full_name}${repo.private ? ' 🔒' : ''}${watched ? ' ✅ watching' : ''}`;
    o.disabled = watched;
    sel.appendChild(o);
  });

  updateRepoSelectLabel(watchedSet.size);
}

async function initPage() {
  const res = await fetch('/api/me');
  if (!res.ok) { window.location.href = '/auth/login'; return null; }
  const user = await res.json();

  document.getElementById('avatar').src = user.avatar_url;
  document.getElementById('username').textContent = user.username;
  setBalance(user.sat_balance);

  let repos = [];
  const watchedSet = new Set();

  await Promise.all([
    fetch('/api/repos').then(r => r.json()).then(data => { repos = Array.isArray(data) ? data : []; }).catch(() => {}),
    fetch('/api/watched').then(r => r.json()).then(data => {
      const watched = Array.isArray(data) ? data : [];
      watched.forEach(item => {
        if (item.repo_full_name) watchedSet.add(item.repo_full_name);
      });
    }).catch(() => {}),
  ]);

  renderRepoOptions(repos, watchedSet);

  document.getElementById('repoSel')?.addEventListener('change', async e => {
    const repo = e.target.value; if (!repo) return;
    e.target.value = '';
    const d = await fetch('/repos/watch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repos: [repo] })
    }).then(r => r.json()).catch(() => ({}));

    if (d.registered?.length) {
      watchedSet.add(repo);
      renderRepoOptions(repos, watchedSet);
    }

    toast(
      d.registered?.length ? `Watching ${repo}` : (d.failed?.[0]?.error || 'Error'),
      !!d.registered?.length
    );
  });

  const es = new EventSource('/events');
  es.onmessage = e => {
    try {
      const ev = JSON.parse(e.data);
      if (ev.type === 'sat_spent') setBalance(ev.new_balance);
      window.dispatchEvent(new CustomEvent('vs', { detail: ev }));
    } catch (_) {}
  };

  return user;
}

function setBalance(n) {
  const el = document.getElementById('satBalance');
  if (el) el.textContent = Number(n).toLocaleString();
}

function toast(msg, ok = true) {
  const el = document.createElement('div');
  el.textContent = msg;
  el.style.cssText = `
    position:fixed;bottom:28px;right:28px;z-index:9999;
    padding:11px 20px;border-radius:10px;font-size:13px;font-weight:500;
    font-family:inherit;backdrop-filter:blur(12px);
    background:${ok ? 'rgba(5,46,22,.9)' : 'rgba(69,10,10,.9)'};
    color:${ok ? '#6ee7b7' : '#fca5a5'};
    border:1px solid ${ok ? 'rgba(16,185,129,.3)' : 'rgba(239,68,68,.3)'};
    box-shadow:0 8px 24px rgba(0,0,0,.5);
  `;
  document.body.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .3s'; }, 2700);
  setTimeout(() => el.remove(), 3100);
}
window.toast = toast;
