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

// ── i18n (site language: en / ar) ───────────────────────────────────────────
const I18N = {
  en: {
    dir: 'ltr',
    navPhases: 'Phases',
    langName: 'العربية',
    heroBadge: 'Open Source · MIT License · 2026',
    heroTitle: 'The <em>applied</em> AI engineering<br>curriculum',
    heroSub: 'Build production AI systems from scratch: RAG, agents, evals, observability, security, and the forward-deployed skillset. No math gate. Eval-first. Ship something in Phase 0.',
    statPhases: 'Phases',
    statLessons: 'Lessons',
    statTime: 'Est. Time',
    statPublished: 'Published',
    allPhases: 'All Phases',
    legendAvailable: 'Available',
    legendBuilding: 'Currently Building',
    legendPlanned: 'Planned',
    statusAvailable: 'Available',
    statusBuilding: 'Currently Building',
    statusPlanned: 'Planned',
    slides: '⧉ Slides',
    home: 'Home',
    phaseWord: 'Phase',
    lessonsWord: 'lessons',
    lessonsUnit: 'lessons',
    colHash: '#',
    colLesson: 'Lesson',
    colStatus: 'Status',
    colTime: 'Time',
    mobileLessons: '☰ Lessons',
    prev: '← Previous',
    next: 'Next →',
    loading: 'Loading…',
    loadingLesson: 'Loading lesson…',
    notBuiltTitle: 'Not built yet',
    notBuiltBody: 'is on the roadmap but hasn\'t been authored yet. Star the repo to get notified when it drops.',
    backToPhase: '← Back to Phase',
    starGithub: 'Star on GitHub ↗',
    notFoundTitle: 'Page not found',
    notFoundBody: 'That phase or lesson doesn\'t exist.',
    backHome: '← Back to home',
    loadError: 'Could not load lesson content from',
    loadHint: 'If running locally, use a static server:',
  },
  ar: {
    dir: 'rtl',
    navPhases: 'المراحل',
    langName: 'EN',
    heroBadge: 'مفتوح المصدر · رخصة MIT · 2026',
    heroTitle: 'منهج هندسة الذكاء الاصطناعي <em>التطبيقي</em>',
    heroSub: 'ابنِ أنظمة ذكاء اصطناعي إنتاجية من الصفر: RAG، والوكلاء (agents)، والتقييمات (evals)، والمراقبة (observability)، والأمان، ومهارات المهندس المنتشَر ميدانيًا (FDE). بلا بوابة رياضيات. التقييم أولًا. وصّل شيئًا فعليًا من المرحلة 0.',
    statPhases: 'المراحل',
    statLessons: 'الدروس',
    statTime: 'الوقت التقديري',
    statPublished: 'المنشورة',
    allPhases: 'كل المراحل',
    legendAvailable: 'متاح',
    legendBuilding: 'قيد الإنشاء',
    legendPlanned: 'مخطّط له',
    statusAvailable: 'متاح',
    statusBuilding: 'قيد الإنشاء',
    statusPlanned: 'مخطّط له',
    slides: '⧉ الشرائح',
    home: 'الرئيسية',
    phaseWord: 'المرحلة',
    lessonsWord: 'درس',
    lessonsUnit: 'درس',
    colHash: '#',
    colLesson: 'الدرس',
    colStatus: 'الحالة',
    colTime: 'الوقت',
    mobileLessons: '☰ الدروس',
    prev: 'السابق →',
    next: '← التالي',
    loading: 'جارٍ التحميل…',
    loadingLesson: 'جارٍ تحميل الدرس…',
    notBuiltTitle: 'لم يُكتب بعد',
    notBuiltBody: 'مُدرَج في خارطة الطريق لكنه لم يُكتب بعد. أضِف نجمة للمستودع ليصلك إشعار عند نشره.',
    backToPhase: 'الرجوع إلى المرحلة →',
    starGithub: 'أضِف نجمة على GitHub ↗',
    notFoundTitle: 'الصفحة غير موجودة',
    notFoundBody: 'هذه المرحلة أو هذا الدرس غير موجود.',
    backHome: 'الرجوع إلى الرئيسية →',
    loadError: 'تعذّر تحميل محتوى الدرس من',
    loadHint: 'إذا كنت تشغّله محليًا، استخدم خادمًا ثابتًا:',
  },
};

function getLang() {
  return localStorage.getItem('siteLang') === 'ar' ? 'ar' : 'en';
}

function t(key) {
  const lang = getLang();
  return (I18N[lang] && I18N[lang][key] != null) ? I18N[lang][key] : I18N.en[key];
}

function phaseTitle(phase) {
  return (getLang() === 'ar' && phase.title_ar) ? phase.title_ar : phase.title;
}

function phaseDesc(phase) {
  return (getLang() === 'ar' && phase.description_ar) ? phase.description_ar : phase.description;
}

function lessonTitle(lesson) {
  return (getLang() === 'ar' && lesson.title_ar) ? lesson.title_ar : lesson.title;
}

function applyLangToDocument() {
  const lang = getLang();
  document.documentElement.setAttribute('lang', lang);
  document.documentElement.setAttribute('dir', I18N[lang].dir);
  // The toggle button shows the language it switches TO.
  const btn = document.getElementById('lang-toggle');
  if (btn) btn.textContent = I18N[lang].langName;
  const navPhases = document.getElementById('nav-phases');
  if (navPhases) navPhases.textContent = t('navPhases');
}

window.toggleLang = function () {
  const next = getLang() === 'ar' ? 'en' : 'ar';
  localStorage.setItem('siteLang', next);
  applyLangToDocument();
  route();
};

function statusLabel(status) {
  const map = { complete: t('statusAvailable'), progress: t('statusBuilding'), planned: t('statusPlanned') };
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
    app.innerHTML = `<div class="loading">${t('loading')}</div>`;
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
      <div class="hero-badge">${t('heroBadge')}</div>
      <h1>${t('heroTitle')}</h1>
      <p class="hero-sub">${t('heroSub')}</p>
      <div class="stats-bar">
        <div class="stat">
          <div class="stat-value">${stats.totalPhases}</div>
          <div class="stat-label">${t('statPhases')}</div>
        </div>
        <div class="stat">
          <div class="stat-value">${stats.totalLessons}</div>
          <div class="stat-label">${t('statLessons')}</div>
        </div>
        <div class="stat">
          <div class="stat-value">~${Math.round(totalHours)}h</div>
          <div class="stat-label">${t('statTime')}</div>
        </div>
        <div class="stat">
          <div class="stat-value">${stats.completeLessons}</div>
          <div class="stat-label">${t('statPublished')}</div>
        </div>
      </div>
    </section>

    <section class="phases-section" id="phases">
      <div class="section-header">
        <span class="section-title">${t('allPhases')}</span>
        <div class="legend">
          <div class="legend-item"><div class="legend-dot complete"></div> ${t('legendAvailable')}</div>
          <div class="legend-item"><div class="legend-dot progress"></div> ${t('legendBuilding')}</div>
          <div class="legend-item"><div class="legend-dot planned"></div> ${t('legendPlanned')}</div>
        </div>
      </div>
      <div class="phase-grid">
        ${phases.map(phaseCard).join('')}
      </div>
    </section>
  `;
}

// Phases with slide decks available (add slug as key, filename stem as value)
const SLIDE_DECKS = {
  '00': 'phase-00-setup',
  '01': 'phase-01-prompt-and-context',
  '02': 'phase-02-rag',
  '03': 'phase-03-tools-and-mcp',
  '04': 'phase-04-agents',
  '05': 'phase-05-evaluation',
  '06': 'phase-06-shipping',
  '07': 'phase-07-observability',
  '08': 'phase-08-security',
  '09': 'phase-09-fine-tuning',
  '10': 'phase-10-multimodal',
  '11': 'phase-11-fde-skillset',
  '12': 'phase-12-capstones',
};

function phaseCard(phase) {
  const done = phase.lessons.filter(l => l.status === 'complete').length;
  const total = phase.lessons.length;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  const clickable = phase.status !== 'planned' || phase.slug;
  const href = clickable ? `#phase/${phase.id}` : 'javascript:void(0)';
  const slideDeck = SLIDE_DECKS[phase.id];
  // slides-btn is a sibling of the card anchor, not nested inside it
  const slidesBtn = slideDeck
    ? `<a class="slides-btn" href="site/slides/${slideDeck}.html" target="_blank" rel="noopener" title="Open facilitator slide deck">${t('slides')}</a>`
    : '';

  return `
    <div class="phase-card-wrap">
      <a class="phase-card ${phase.status}" href="${href}" style="display:block; text-decoration:none;">
        <div class="phase-card-num">${phase.id}</div>
        <div class="phase-card-status">
          <span class="status-dot ${phase.status}"></span>
          <span class="status-label ${phase.status}">${statusLabel(phase.status)}</span>
        </div>
        <div class="phase-card-title">${phaseTitle(phase)}</div>
        <div class="phase-card-desc">${phaseDesc(phase)}</div>
        <div class="phase-progress">
          <div class="phase-progress-bar">
            <div class="phase-progress-fill" style="width:${pct}%"></div>
          </div>
          <div class="phase-progress-text">${done} / ${total} ${t('lessonsUnit')} · ${phase.time}</div>
        </div>
      </a>
      ${slidesBtn}
    </div>
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
        <a href="#">${t('home')}</a>
        <span class="breadcrumb-sep">/</span>
        <span>${t('phaseWord')} ${phase.id}</span>
      </div>

      <div class="phase-header">
        <div class="phase-num-badge">${t('phaseWord')} ${phase.id}</div>
        <h1>${phaseTitle(phase)}</h1>
        <div class="phase-header-meta">
          ${statusPill(phase.status)}
          <span class="tag">${done}/${phase.lessons.length} ${t('lessonsUnit')}</span>
          <span class="tag">${phase.time}</span>
        </div>
        <p class="phase-desc">${phaseDesc(phase)}</p>
      </div>

      <table class="lesson-table">
        <thead>
          <tr>
            <th>${t('colHash')}</th>
            <th>${t('colLesson')}</th>
            <th>${t('colStatus')}</th>
            <th style="text-align:right">${t('colTime')}</th>
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
      <td class="lesson-title-cell">${lessonTitle(lesson)}</td>
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
        <div class="sidebar-phase-title">${t('phaseWord')} ${phase.id}: ${phaseTitle(phase)}</div>
        ${phase.lessons.map(l => sidebarItem(phase, lesson, l)).join('')}
      </aside>
      <div class="lesson-content">
        <div class="lesson-content-inner">
          <button class="mobile-toc-btn" onclick="openSidebar()" aria-label="Open lesson list">${t('mobileLessons')}</button>
          <div class="breadcrumb">
            <a href="#">${t('home')}</a>
            <span class="breadcrumb-sep">/</span>
            <a href="#phase/${phase.id}">${t('phaseWord')} ${phase.id}</a>
            <span class="breadcrumb-sep">/</span>
            <span>${lessonTitle(lesson)}</span>
          </div>
          <div id="lesson-body" class="md-body"><div class="loading">${t('loadingLesson')}</div></div>
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
      <span style="flex:1">${lessonTitle(lesson)}</span>
      <span class="sidebar-status" style="font-size:11px; color:${lesson.status === 'complete' ? 'var(--green)' : 'var(--text-faint)'}">${statusIcon}</span>
    </div>
  `;
}

function lessonNavButtons(phase, idx) {
  const prev = phase.lessons[idx - 1];
  const next = phase.lessons[idx + 1];
  const prevBtn = prev
    ? `<div class="lesson-nav-btn prev" onclick="window.location.hash='phase/${phase.id}/${prev.id}'">
        <span class="lesson-nav-dir">${t('prev')}</span>
        <span class="lesson-nav-title">${lessonTitle(prev)}</span>
      </div>`
    : `<div></div>`;
  const nextBtn = next && next.status !== 'planned'
    ? `<div class="lesson-nav-btn next" onclick="window.location.hash='phase/${phase.id}/${next.id}'">
        <span class="lesson-nav-dir">${t('next')}</span>
        <span class="lesson-nav-title">${lessonTitle(next)}</span>
      </div>`
    : `<div></div>`;
  return `<div class="lesson-nav">${prevBtn}${nextBtn}</div>`;
}

async function loadLessonContent(phase, lesson) {
  const lang = getLang();
  const enPath = `phases/${phase.slug}/${lesson.slug}/docs/en.md`;
  const mdPath = lang === 'ar' ? `phases/${phase.slug}/${lesson.slug}/docs/ar.md` : enPath;
  const body = document.getElementById('lesson-body');

  try {
    let res = await fetch(mdPath);
    let usedFallback = false;
    if (!res.ok && lang === 'ar') {
      // Arabic translation not available yet — fall back to English.
      res = await fetch(enPath);
      usedFallback = true;
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const md = await res.text();
    const isArabic = lang === 'ar' && !usedFallback;

    body.setAttribute('dir', isArabic ? 'rtl' : 'ltr');
    body.classList.toggle('lang-ar', isArabic);

    const colabBadge = lesson.notebook
      ? `<div class="colab-badge-wrap"><a href="https://colab.research.google.com/github/thepandanlabs/applied-ai-from-scratch/blob/main/${lesson.notebook}" target="_blank" rel="noopener noreferrer"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"></a></div>`
      : '';
    const fallbackNote = usedFallback
      ? `<div class="lang-fallback-note">الترجمة العربية لهذا الدرس غير متوفرة بعد — يتم عرض النسخة الإنجليزية.</div>`
      : '';
    body.innerHTML = colabBadge + fallbackNote + renderMarkdown(md);
    await runMermaid();
    hljs.highlightAll();
  } catch (e) {
    body.innerHTML = `
      <div class="not-built" style="text-align:start; padding:0">
        <p style="color:var(--text-muted)">${t('loadError')} <code>${mdPath}</code>.</p>
        <p style="color:var(--text-muted); font-size:13px; margin-top:8px">
          ${t('loadHint')} <code>npx serve .</code> · <code>python -m http.server 8000</code>
        </p>
      </div>
    `;
  }
}

function renderMarkdown(md) {
  // Extract header metadata (Type, Languages, Prerequisites, Time lines at top)
  const metaMatch = md.match(/^(\*\*(?:Type|Languages?|Prerequisites?|Time|Phase|النوع|اللغات|المتطلبات|الوقت|المرحلة):\*\*[^\n]*\n?)+/m);
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
      <h2>${t('notBuiltTitle')}</h2>
      <p>
        <strong>${lessonTitle(lesson)}</strong> ${t('notBuiltBody')}
      </p>
      <div style="display:flex; gap:12px; justify-content:center; flex-wrap:wrap">
        <a class="btn" href="#phase/${phase.id}">${t('backToPhase')} ${phase.id}</a>
        <a class="btn" href="https://github.com/thepandanlabs/applied-ai-from-scratch"
           target="_blank" rel="noopener">${t('starGithub')}</a>
      </div>
    </div>
  `;
}

function renderNotFound() {
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="not-built">
      <div class="not-built-icon">🔍</div>
      <h2>${t('notFoundTitle')}</h2>
      <p>${t('notFoundBody')}</p>
      <a class="btn" href="#">${t('backHome')}</a>
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
  applyLangToDocument();
  if (window.CURRICULUM) {
    route();
  } else {
    document.getElementById('app').innerHTML =
      '<div class="loading">Run <code>node site/build.js</code> to generate curriculum data, then serve with <code>npx serve .</code></div>';
  }
});
