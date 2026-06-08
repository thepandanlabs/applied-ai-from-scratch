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
      <button class="copy-btn" onclick="copyCode(this, event)">${t('copy')}</button>
    </div>
    <pre><code class="hljs language-${validLang}">${highlighted}</code></pre>
  </div>`;
};

renderer.table = function (header, body) {
  return `<div style="overflow-x:auto"><table>${header}${body}</table></div>`;
};

marked.use({ renderer, breaks: false, gfm: true });

// ── i18n ──────────────────────────────────────────────────────────────────
const SUPPORTED_LANGS = ['en', 'ar'];

const I18N = {
  en: {
    statusComplete: 'Available',
    statusProgress: 'Currently Building',
    statusPlanned: 'Planned',
    copy: 'Copy',
    copied: 'Copied!',
    heroBadge: 'Open Source · MIT License · 2026',
    heroTitle: 'The <em>applied</em> AI engineering<br>curriculum',
    heroSub: 'Build production AI systems from scratch: RAG, agents, evals, observability, security, and the forward-deployed skillset. No math gate. Eval-first. Ship something in Phase 0.',
    statPhases: 'Phases',
    statLessons: 'Lessons',
    statTime: 'Est. Time',
    statPublished: 'Published',
    allPhases: 'All Phases',
    lessons: 'lessons',
    home: 'Home',
    phase: 'Phase',
    colNum: '#',
    colLesson: 'Lesson',
    colStatus: 'Status',
    colTime: 'Time',
    lessonsBtn: '☰ Lessons',
    loadingLesson: 'Loading lesson…',
    loading: 'Loading…',
    prev: 'Previous',
    next: 'Next',
    notBuiltTitle: 'Not built yet',
    notBuiltBody: (title) => `<strong>${title}</strong> is on the roadmap but hasn't been authored yet. Star the repo to get notified when it drops.`,
    backToPhase: 'Back to Phase',
    starGithub: 'Star on GitHub ↗',
    notFoundTitle: 'Page not found',
    notFoundBody: "That phase or lesson doesn't exist.",
    backHome: 'Back to home',
    slides: '⧉ Slides',
    slidesTitle: 'Open facilitator slide deck',
    navPhases: 'Phases',
    siteTitle: 'Applied AI From Scratch',
    footerText: 'Built with ❤️ from 🇸🇦 Saudi Arabia',
    footerOpen: 'open source',
    couldNotLoad: (p) => `Could not load lesson content from <code>${p}</code>.`,
    serveHint: 'If running locally, use a static server: <code>npx serve .</code> or <code>python -m http.server 8000</code>',
    buildHint: 'Run <code>node site/build.js</code> to generate curriculum data, then serve with <code>npx serve .</code>',
  },
  ar: {
    statusComplete: 'متاح',
    statusProgress: 'قيد الإنشاء',
    statusPlanned: 'مُخطَّط له',
    copy: 'نسخ',
    copied: 'تم النسخ!',
    heroBadge: 'مفتوح المصدر · رخصة MIT · 2026',
    heroTitle: 'منهج هندسة الذكاء الاصطناعي <em>التطبيقي</em>',
    heroSub: 'ابنِ أنظمة ذكاء اصطناعي إنتاجية من الصفر: RAG، والوكلاء، والتقييمات، والقابلية للمراقبة، والأمان، ومهارات المهندس الميداني. لا بوابة رياضيات. التقييم أولًا. اشحن شيئًا في المرحلة 0.',
    statPhases: 'مراحل',
    statLessons: 'دروس',
    statTime: 'الوقت التقديري',
    statPublished: 'منشورة',
    allPhases: 'كل المراحل',
    lessons: 'دروس',
    home: 'الرئيسية',
    phase: 'المرحلة',
    colNum: '#',
    colLesson: 'الدرس',
    colStatus: 'الحالة',
    colTime: 'الوقت',
    lessonsBtn: '☰ الدروس',
    loadingLesson: 'جارٍ تحميل الدرس…',
    loading: 'جارٍ التحميل…',
    prev: 'السابق',
    next: 'التالي',
    notBuiltTitle: 'لم يُكتب بعد',
    notBuiltBody: (title) => `<strong>${title}</strong> مُدرَج في خارطة الطريق لكنه لم يُكتب بعد. ضع نجمة للمستودع ليصلك إشعار عند نشره.`,
    backToPhase: 'العودة إلى المرحلة',
    starGithub: 'ضع نجمة على GitHub ↗',
    notFoundTitle: 'الصفحة غير موجودة',
    notFoundBody: 'هذه المرحلة أو الدرس غير موجود.',
    backHome: 'العودة إلى الرئيسية',
    slides: '⧉ الشرائح',
    slidesTitle: 'افتح شرائح الميسِّر',
    navPhases: 'المراحل',
    siteTitle: 'الذكاء الاصطناعي التطبيقي من الصفر',
    footerText: 'صُنع بـ ❤️ من 🇸🇦 المملكة العربية السعودية',
    footerOpen: 'مفتوح المصدر',
    couldNotLoad: (p) => `تعذّر تحميل محتوى الدرس من <code>${p}</code>.`,
    serveHint: 'إذا كنت تشغّله محليًا، استخدم خادمًا ثابتًا: <code>npx serve .</code> أو <code>python -m http.server 8000</code>',
    buildHint: 'شغّل <code>node site/build.js</code> لتوليد بيانات المنهج، ثم قدّمه عبر <code>npx serve .</code>',
  },
};

function getInitialLang() {
  const fromUrl = new URLSearchParams(window.location.search).get('lang');
  if (SUPPORTED_LANGS.includes(fromUrl)) return fromUrl;
  const saved = localStorage.getItem('lang');
  if (SUPPORTED_LANGS.includes(saved)) return saved;
  return 'en';
}

let currentLang = getInitialLang();

// Translate a UI string key. Falls back to English, then the key itself.
function t(key, ...args) {
  const dict = I18N[currentLang] || I18N.en;
  let v = dict[key];
  if (v === undefined) v = I18N.en[key];
  if (v === undefined) return key;
  return typeof v === 'function' ? v(...args) : v;
}

// Localize a curriculum data field (title/description/time) for the current lang.
function L(obj, field) {
  if (currentLang === 'ar') return obj[`${field}_ar`] || obj[field];
  return obj[field];
}

function applyLang(lang) {
  currentLang = SUPPORTED_LANGS.includes(lang) ? lang : 'en';
  const root = document.documentElement;
  root.setAttribute('lang', currentLang);
  root.setAttribute('dir', currentLang === 'ar' ? 'rtl' : 'ltr');
  localStorage.setItem('lang', currentLang);
}

function updateLangToggle() {
  const label = document.querySelector('#lang-toggle .lang-label');
  if (label) label.textContent = currentLang === 'ar' ? 'EN' : 'ع';
}

// Updates chrome that lives in index.html and is not re-rendered by route().
function updateStaticChrome() {
  document.title = t('siteTitle');
  const navPhases = document.querySelector('.nav-link[data-i18n="navPhases"]');
  if (navPhases) navPhases.textContent = t('navPhases');
  const footer = document.querySelector('.site-footer');
  if (footer) footer.innerHTML = `${t('footerText')} &nbsp;·&nbsp; <a href="https://github.com/thepandanlabs/applied-ai-from-scratch" target="_blank" rel="noopener">${t('footerOpen')}</a>`;
}

window.toggleLang = function () {
  applyLang(currentLang === 'ar' ? 'en' : 'ar');
  const url = new URL(window.location.href);
  url.searchParams.set('lang', currentLang);
  history.replaceState(null, '', url);
  updateLangToggle();
  updateStaticChrome();
  route();
};

function initLang() {
  applyLang(currentLang);
  updateLangToggle();
  updateStaticChrome();
}

// ── Utilities ─────────────────────────────────────────────────────────────
function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function statusLabel(status) {
  const map = { complete: t('statusComplete'), progress: t('statusProgress'), planned: t('statusPlanned') };
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
    btn.textContent = t('copied');
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = t('copy'); btn.classList.remove('copied'); }, 2000);
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
          <div class="legend-item"><div class="legend-dot complete"></div> ${t('statusComplete')}</div>
          <div class="legend-item"><div class="legend-dot progress"></div> ${t('statusProgress')}</div>
          <div class="legend-item"><div class="legend-dot planned"></div> ${t('statusPlanned')}</div>
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
    ? `<a class="slides-btn" href="site/slides/${slideDeck}.html" target="_blank" rel="noopener" title="${t('slidesTitle')}">${t('slides')}</a>`
    : '';

  return `
    <div class="phase-card-wrap">
      <a class="phase-card ${phase.status}" href="${href}" style="display:block; text-decoration:none;">
        <div class="phase-card-num">${phase.id}</div>
        <div class="phase-card-status">
          <span class="status-dot ${phase.status}"></span>
          <span class="status-label ${phase.status}">${statusLabel(phase.status)}</span>
        </div>
        <div class="phase-card-title">${L(phase, 'title')}</div>
        <div class="phase-card-desc">${L(phase, 'description')}</div>
        <div class="phase-progress">
          <div class="phase-progress-bar">
            <div class="phase-progress-fill" style="width:${pct}%"></div>
          </div>
          <div class="phase-progress-text">${done} / ${total} ${t('lessons')} · ${L(phase, 'time')}</div>
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
        <span>${t('phase')} ${phase.id}</span>
      </div>

      <div class="phase-header">
        <div class="phase-num-badge">${t('phase')} ${phase.id}</div>
        <h1>${L(phase, 'title')}</h1>
        <div class="phase-header-meta">
          ${statusPill(phase.status)}
          <span class="tag">${done}/${phase.lessons.length} ${t('lessons')}</span>
          <span class="tag">${L(phase, 'time')}</span>
        </div>
        <p class="phase-desc">${L(phase, 'description')}</p>
      </div>

      <table class="lesson-table">
        <thead>
          <tr>
            <th>${t('colNum')}</th>
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
      <td class="lesson-title-cell">${L(lesson, 'title')}</td>
      <td>${statusPill(lesson.status)}</td>
      <td class="lesson-time">${L(lesson, 'time')}</td>
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
        <div class="sidebar-phase-title">${t('phase')} ${phase.id}: ${L(phase, 'title')}</div>
        ${phase.lessons.map(l => sidebarItem(phase, lesson, l)).join('')}
      </aside>
      <div class="lesson-content">
        <div class="lesson-content-inner">
          <button class="mobile-toc-btn" onclick="openSidebar()" aria-label="${t('colLesson')}">${t('lessonsBtn')}</button>
          <div class="breadcrumb">
            <a href="#">${t('home')}</a>
            <span class="breadcrumb-sep">/</span>
            <a href="#phase/${phase.id}">${t('phase')} ${phase.id}</a>
            <span class="breadcrumb-sep">/</span>
            <span>${L(lesson, 'title')}</span>
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
      <span style="flex:1">${L(lesson, 'title')}</span>
      <span class="sidebar-status" style="font-size:11px; color:${lesson.status === 'complete' ? 'var(--green)' : 'var(--text-faint)'}">${statusIcon}</span>
    </div>
  `;
}

function lessonNavButtons(phase, idx) {
  const prev = phase.lessons[idx - 1];
  const next = phase.lessons[idx + 1];
  const rtl = currentLang === 'ar';
  const backArrow = rtl ? '→' : '←';
  const fwdArrow = rtl ? '←' : '→';
  const prevBtn = prev
    ? `<div class="lesson-nav-btn prev" onclick="window.location.hash='phase/${phase.id}/${prev.id}'">
        <span class="lesson-nav-dir">${backArrow} ${t('prev')}</span>
        <span class="lesson-nav-title">${L(prev, 'title')}</span>
      </div>`
    : `<div></div>`;
  const nextBtn = next && next.status !== 'planned'
    ? `<div class="lesson-nav-btn next" onclick="window.location.hash='phase/${phase.id}/${next.id}'">
        <span class="lesson-nav-dir">${t('next')} ${fwdArrow}</span>
        <span class="lesson-nav-title">${L(next, 'title')}</span>
      </div>`
    : `<div></div>`;
  return `<div class="lesson-nav">${prevBtn}${nextBtn}</div>`;
}

async function loadLessonContent(phase, lesson) {
  const dir = `phases/${phase.slug}/${lesson.slug}/docs`;
  const mdPath = `${dir}/${currentLang === 'ar' ? 'ar' : 'en'}.md`;
  const body = document.getElementById('lesson-body');

  try {
    let res = await fetch(mdPath);
    if (!res.ok && currentLang === 'ar') res = await fetch(`${dir}/en.md`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const md = await res.text();
    const colabBadge = lesson.notebook
      ? `<div class="colab-badge-wrap"><a href="https://colab.research.google.com/github/thepandanlabs/applied-ai-from-scratch/blob/main/${lesson.notebook}" target="_blank" rel="noopener noreferrer"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"></a></div>`
      : '';
    body.innerHTML = colabBadge + renderMarkdown(md);
    await runMermaid();
    hljs.highlightAll();
  } catch (e) {
    body.innerHTML = `
      <div class="not-built" style="text-align:left; padding:0">
        <p style="color:var(--text-muted)">${t('couldNotLoad', mdPath)}</p>
        <p style="color:var(--text-muted); font-size:13px; margin-top:8px">${t('serveHint')}</p>
      </div>
    `;
  }
}

function renderMarkdown(md) {
  // Extract header metadata (Type, Languages, Prerequisites, Time lines at top)
  const metaMatch = md.match(/^(\*\*(?:Type|Languages?|Prerequisites?|Time|Phase|النوع|اللغات|اللغة|المتطلبات|الوقت|المرحلة):\*\*[^\n]*\n?)+/m);
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
      <p>${t('notBuiltBody', L(lesson, 'title'))}</p>
      <div style="display:flex; gap:12px; justify-content:center; flex-wrap:wrap">
        <a class="btn" href="#phase/${phase.id}">${currentLang === 'ar' ? '→' : '←'} ${t('backToPhase')} ${phase.id}</a>
        <a class="btn" href="https://github.com/appliedaifromscratch/appliedaifromscratch.com"
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
      <a class="btn" href="#">${currentLang === 'ar' ? '→' : '←'} ${t('backHome')}</a>
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
  initLang();
  if (window.CURRICULUM) {
    route();
  } else {
    document.getElementById('app').innerHTML =
      `<div class="loading">${t('buildHint')}</div>`;
  }
});
