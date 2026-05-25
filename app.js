// app.js — SPA router for appliedaifromscratch.com

// ── Mermaid init ──────────────────────────────────────────────────────────
mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  themeVariables: {
    primaryColor: '#6366f1',
    primaryTextColor: '#e8e8e8',
    primaryBorderColor: '#4f46e5',
    lineColor: '#555',
    secondaryColor: '#1e1e1e',
    tertiaryColor: '#171717',
    background: '#101010',
    mainBkg: '#171717',
    nodeBorder: '#333',
    clusterBkg: '#1e1e1e',
    titleColor: '#e8e8e8',
    edgeLabelBackground: '#1e1e1e',
    attributeBackgroundColorEven: '#101010',
    attributeBackgroundColorOdd: '#171717',
  },
  fontFamily: 'system-ui, -apple-system, sans-serif',
  fontSize: 13,
});

// ── Marked config ─────────────────────────────────────────────────────────
const renderer = new marked.Renderer();

renderer.code = function (code, lang) {
  if (lang === 'mermaid') {
    return `<div class="mermaid-wrap"><div class="mermaid">${escapeHtml(code)}</div></div>`;
  }
  const validLang = lang && hljs.getLanguage(lang) ? lang : 'plaintext';
  const highlighted = hljs.highlight(code, { language: validLang, ignoreIllegals: true }).value;
  const langLabel = lang || 'text';
  return `<div class="code-block">
    <div class="code-block-header">
      <span class="code-lang">${langLabel}</span>
      <button class="copy-btn" onclick="copyCode(this, event)">Copy</button>
    </div>
    <pre><code class="hljs language-${validLang}">${highlighted}</code></pre>
  </div>`;
};

renderer.table = function (header, body) {
  return `<div style="overflow-x:auto"><table>${header}${body}</table></div>`;
};

marked.use({ renderer, breaks: false, gfm: true });

// ── Utilities ─────────────────────────────────────────────────────────────
function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function statusLabel(status) {
  const map = { complete: 'Complete', progress: 'In Progress', planned: 'Planned' };
  return map[status] || status;
}

function statusDot(status) {
  return `<span class="status-dot ${status}"></span>`;
}

function statusPill(status) {
  const label = statusLabel(status);
  const icon = status === 'complete' ? '✓' : status === 'progress' ? '◉' : '○';
  return `<span class="status-pill ${status}">${icon} ${label}</span>`;
}

window.copyCode = function (btn, e) {
  if (e) e.stopPropagation();
  const pre = btn.closest('.code-block').querySelector('code');
  navigator.clipboard.writeText(pre.textContent).then(() => {
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 2000);
  });
};

async function runMermaid() {
  const nodes = document.querySelectorAll('.mermaid:not([data-processed])');
  if (!nodes.length) return;
  try {
    await mermaid.run({ nodes });
  } catch (e) {
    console.warn('Mermaid render error:', e);
  }
}

function scrollToTop() {
  window.scrollTo({ top: 0, behavior: 'instant' });
}

// ── Router ─────────────────────────────────────────────────────────────────
function parseHash() {
  const hash = decodeURIComponent(window.location.hash.slice(1));
  if (!hash || hash === 'phases') return { view: 'home' };

  // #phase/02 or #phase/02/05
  const m = hash.match(/^phase\/(\d+)(?:\/(\d+))?$/);
  if (m) {
    return { view: m[2] ? 'lesson' : 'phase', phaseId: m[1], lessonId: m[2] };
  }
  return { view: 'home' };
}

function route() {
  const { view, phaseId, lessonId } = parseHash();
  const app = document.getElementById('app');

  if (!window.CURRICULUM) {
    app.innerHTML = '<div class="loading">Loading…</div>';
    return;
  }

  scrollToTop();

  if (view === 'lesson') {
    renderLesson(phaseId, lessonId);
  } else if (view === 'phase') {
    renderPhase(phaseId);
  } else {
    renderHome();
  }
}

// ── Home page ─────────────────────────────────────────────────────────────
function renderHome() {
  const { stats, phases } = window.CURRICULUM;
  const app = document.getElementById('app');

  const totalHours = phases.reduce((s, p) => {
    const h = parseFloat(p.time.replace(/[^0-9.]/g, ''));
    return s + (isNaN(h) ? 0 : h);
  }, 0);

  app.innerHTML = `
    <section class="hero">
      <div class="hero-badge">Open Source · MIT License · 2026</div>
      <h1>The <em>applied</em> AI engineering<br>curriculum</h1>
      <p class="hero-sub">
        Build production AI systems from scratch: RAG, agents, evals, observability,
        security, and the forward-deployed skillset. No math gate. Eval-first. Ship something in Phase 0.
      </p>
      <div class="stats-bar">
        <div class="stat">
          <div class="stat-value">${stats.totalPhases}</div>
          <div class="stat-label">Phases</div>
        </div>
        <div class="stat">
          <div class="stat-value">${stats.totalLessons}</div>
          <div class="stat-label">Lessons</div>
        </div>
        <div class="stat">
          <div class="stat-value">~${Math.round(totalHours)}h</div>
          <div class="stat-label">Est. Time</div>
        </div>
        <div class="stat">
          <div class="stat-value">${stats.completeLessons}</div>
          <div class="stat-label">Published</div>
        </div>
      </div>
    </section>

    <section class="phases-section" id="phases">
      <div class="section-header">
        <span class="section-title">All Phases</span>
        <div class="legend">
          <div class="legend-item"><div class="legend-dot complete"></div> Complete</div>
          <div class="legend-item"><div class="legend-dot progress"></div> In Progress</div>
          <div class="legend-item"><div class="legend-dot planned"></div> Planned</div>
        </div>
      </div>
      <div class="phase-grid">
        ${phases.map(phaseCard).join('')}
      </div>
    </section>
  `;
}

function phaseCard(phase) {
  const done = phase.lessons.filter(l => l.status === 'complete').length;
  const total = phase.lessons.length;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  const clickable = phase.status !== 'planned' || phase.slug;
  const href = clickable ? `#phase/${phase.id}` : 'javascript:void(0)';

  return `
    <a class="phase-card ${phase.status}" href="${href}" style="display:block; text-decoration:none;">
      <div class="phase-card-num">${phase.id}</div>
      <div class="phase-card-status">
        <span class="status-dot ${phase.status}"></span>
        <span class="status-label ${phase.status}">${statusLabel(phase.status)}</span>
      </div>
      <div class="phase-card-title">${phase.title}</div>
      <div class="phase-card-desc">${phase.description}</div>
      <div class="phase-progress">
        <div class="phase-progress-bar">
          <div class="phase-progress-fill" style="width:${pct}%"></div>
        </div>
        <div class="phase-progress-text">${done} / ${total} lessons · ${phase.time}</div>
      </div>
    </a>
  `;
}

// ── Phase page ────────────────────────────────────────────────────────────
function renderPhase(phaseId) {
  const phase = window.CURRICULUM.phases.find(p => p.id === phaseId.padStart(2, '0'));
  if (!phase) { renderNotFound(); return; }

  const app = document.getElementById('app');
  const done = phase.lessons.filter(l => l.status === 'complete').length;

  app.innerHTML = `
    <div class="phase-page">
      <div class="breadcrumb">
        <a href="#">Home</a>
        <span class="breadcrumb-sep">/</span>
        <span>Phase ${phase.id}</span>
      </div>

      <div class="phase-header">
        <div class="phase-num-badge">Phase ${phase.id}</div>
        <h1>${phase.title}</h1>
        <div class="phase-header-meta">
          ${statusPill(phase.status)}
          <span class="tag">${done}/${phase.lessons.length} lessons</span>
          <span class="tag">${phase.time}</span>
        </div>
        <p class="phase-desc">${phase.description}</p>
      </div>

      <table class="lesson-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Lesson</th>
            <th>Status</th>
            <th style="text-align:right">Time</th>
          </tr>
        </thead>
        <tbody>
          ${phase.lessons.map(lesson => lessonRow(phase, lesson)).join('')}
        </tbody>
      </table>
    </div>
  `;
}

function lessonRow(phase, lesson) {
  const canOpen = lesson.status !== 'planned' && lesson.slug;
  const rowClass = canOpen ? 'clickable' : 'planned';
  const onclick = canOpen
    ? `onclick="window.location.hash='phase/${phase.id}/${lesson.id}'"`
    : '';
  return `
    <tr class="${lesson.status} ${rowClass}" ${onclick}>
      <td class="lesson-num">${lesson.id}</td>
      <td class="lesson-title-cell">${lesson.title}</td>
      <td>${statusPill(lesson.status)}</td>
      <td class="lesson-time">${lesson.time}</td>
    </tr>
  `;
}

// ── Lesson page ────────────────────────────────────────────────────────────
async function renderLesson(phaseId, lessonId) {
  const phase = window.CURRICULUM.phases.find(p => p.id === phaseId.padStart(2, '0'));
  if (!phase) { renderNotFound(); return; }

  const lessonIdx = phase.lessons.findIndex(l => l.id === lessonId.padStart(2, '0'));
  const lesson = phase.lessons[lessonIdx];
  if (!lesson) { renderNotFound(); return; }

  if (!lesson.slug) {
    renderNotBuilt(phase, lesson);
    return;
  }

  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="sidebar-overlay" onclick="closeSidebar()"></div>
    <div class="lesson-layout">
      <aside class="lesson-sidebar">
        <div class="sidebar-phase-title">Phase ${phase.id}: ${phase.title}</div>
        ${phase.lessons.map(l => sidebarItem(phase, lesson, l)).join('')}
      </aside>
      <div class="lesson-content">
        <div class="lesson-content-inner">
          <button class="mobile-toc-btn" onclick="openSidebar()" aria-label="Open lesson list">☰ Lessons</button>
          <div class="breadcrumb">
            <a href="#">Home</a>
            <span class="breadcrumb-sep">/</span>
            <a href="#phase/${phase.id}">Phase ${phase.id}</a>
            <span class="breadcrumb-sep">/</span>
            <span>${lesson.title}</span>
          </div>
          <div id="lesson-body" class="md-body"><div class="loading">Loading lesson…</div></div>
          ${lessonNavButtons(phase, lessonIdx)}
        </div>
      </div>
    </div>
  `;

  await loadLessonContent(phase, lesson);
}

function sidebarItem(phase, currentLesson, lesson) {
  const active = lesson.id === currentLesson.id ? 'active' : '';
  const planned = lesson.status === 'planned' ? 'planned' : '';
  const onclick = lesson.slug && lesson.status !== 'planned'
    ? `onclick="closeSidebar(); window.location.hash='phase/${phase.id}/${lesson.id}'"`
    : '';
  const statusIcon = lesson.status === 'complete' ? '✓' : lesson.status === 'progress' ? '◉' : '○';
  return `
    <div class="sidebar-lesson ${active} ${planned}" ${onclick}>
      <span class="sidebar-lesson-num">${lesson.id}</span>
      <span style="flex:1">${lesson.title}</span>
      <span class="sidebar-status" style="font-size:11px; color:${lesson.status === 'complete' ? 'var(--green)' : 'var(--text-faint)'}">${statusIcon}</span>
    </div>
  `;
}

function lessonNavButtons(phase, idx) {
  const prev = phase.lessons[idx - 1];
  const next = phase.lessons[idx + 1];
  const prevBtn = prev
    ? `<div class="lesson-nav-btn prev" onclick="window.location.hash='phase/${phase.id}/${prev.id}'">
        <span class="lesson-nav-dir">← Previous</span>
        <span class="lesson-nav-title">${prev.title}</span>
      </div>`
    : `<div></div>`;
  const nextBtn = next && next.status !== 'planned'
    ? `<div class="lesson-nav-btn next" onclick="window.location.hash='phase/${phase.id}/${next.id}'">
        <span class="lesson-nav-dir">Next →</span>
        <span class="lesson-nav-title">${next.title}</span>
      </div>`
    : `<div></div>`;
  return `<div class="lesson-nav">${prevBtn}${nextBtn}</div>`;
}

async function loadLessonContent(phase, lesson) {
  const mdPath = `phases/${phase.slug}/${lesson.slug}/docs/en.md`;
  const body = document.getElementById('lesson-body');

  try {
    const res = await fetch(mdPath);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const md = await res.text();
    body.innerHTML = renderMarkdown(md);
    await runMermaid();
    hljs.highlightAll();
  } catch (e) {
    body.innerHTML = `
      <div class="not-built" style="text-align:left; padding:0">
        <p style="color:var(--text-muted)">Could not load lesson content from <code>${mdPath}</code>.</p>
        <p style="color:var(--text-muted); font-size:13px; margin-top:8px">
          If running locally, use a static server: <code>npx serve .</code> or <code>python -m http.server 8000</code>
        </p>
      </div>
    `;
  }
}

function renderMarkdown(md) {
  // Extract header metadata (Type, Languages, Prerequisites, Time lines at top)
  const metaMatch = md.match(/^(\*\*(?:Type|Languages?|Prerequisites?|Time|Phase):\*\*[^\n]*\n?)+/m);
  let metaHtml = '';
  let cleanMd = md;

  if (metaMatch) {
    const metaBlock = metaMatch[0];
    cleanMd = md.replace(metaBlock, '').trimStart();
    const lines = metaBlock.trim().split('\n').filter(Boolean);
    const tags = lines.map(line => {
      const m = line.match(/\*\*(.+?):\*\*\s*(.*)/);
      if (!m) return '';
      return `<span class="meta-tag"><strong>${m[1]}:</strong> ${m[2]}</span>`;
    }).join('');
    if (tags) metaHtml = `<div class="lesson-meta-bar">${tags}</div>`;
  }

  const html = marked.parse(cleanMd);
  return metaHtml + `<div>${html}</div>`;
}

// ── Not built / 404 ────────────────────────────────────────────────────────
function renderNotBuilt(phase, lesson) {
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="not-built">
      <div class="not-built-icon">📐</div>
      <h2>Not built yet</h2>
      <p>
        <strong>${lesson.title}</strong> is on the roadmap but hasn't been authored yet.
        Star the repo to get notified when it drops.
      </p>
      <div style="display:flex; gap:12px; justify-content:center; flex-wrap:wrap">
        <a class="btn" href="#phase/${phase.id}">← Back to Phase ${phase.id}</a>
        <a class="btn" href="https://github.com/appliedaifromscratch/appliedaifromscratch.com"
           target="_blank" rel="noopener">Star on GitHub ↗</a>
      </div>
    </div>
  `;
}

function renderNotFound() {
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="not-built">
      <div class="not-built-icon">🔍</div>
      <h2>Page not found</h2>
      <p>That phase or lesson doesn't exist.</p>
      <a class="btn" href="#">← Back to home</a>
    </div>
  `;
}

// ── Theme toggle ──────────────────────────────────────────────────────────
window.toggleTheme = function () {
  const root = document.documentElement;
  const current = root.getAttribute('data-theme') || 'dark';
  const next = current === 'dark' ? 'light' : 'dark';
  root.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);

  const dark = document.getElementById('hljs-dark');
  const light = document.getElementById('hljs-light');
  if (dark && light) {
    dark.disabled = next === 'light';
    light.disabled = next === 'dark';
  }

  const icon = document.querySelector('#theme-toggle .theme-icon');
  if (icon) icon.textContent = next === 'dark' ? '☀' : '◑';
};

function initTheme() {
  const theme = document.documentElement.getAttribute('data-theme') || 'dark';
  const icon = document.querySelector('#theme-toggle .theme-icon');
  if (icon) icon.textContent = theme === 'dark' ? '☀' : '◑';
}

// ── Mobile sidebar ────────────────────────────────────────────────────────
window.openSidebar = function () {
  document.querySelector('.lesson-sidebar')?.classList.add('open');
  document.querySelector('.sidebar-overlay')?.classList.add('open');
  document.body.style.overflow = 'hidden';
};

window.closeSidebar = function () {
  document.querySelector('.lesson-sidebar')?.classList.remove('open');
  document.querySelector('.sidebar-overlay')?.classList.remove('open');
  document.body.style.overflow = '';
};

// ── Boot ──────────────────────────────────────────────────────────────────
window.addEventListener('hashchange', route);
window.addEventListener('load', () => {
  initTheme();
  if (window.CURRICULUM) {
    route();
  } else {
    document.getElementById('app').innerHTML =
      '<div class="loading">Run <code>node site/build.js</code> to generate curriculum data, then serve with <code>npx serve .</code></div>';
  }
});
