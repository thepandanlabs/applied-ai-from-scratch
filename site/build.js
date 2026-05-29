#!/usr/bin/env node
// site/build.js — generates site/data.js from ROADMAP.md + phases/ directory
// Run: node site/build.js

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const ROADMAP_PATH = path.join(ROOT, 'ROADMAP.md');
const PHASES_DIR = path.join(ROOT, 'phases');
const OUTPUT_PATH = path.join(__dirname, 'data.js');

const PHASE_DESCRIPTIONS = {
  '00': 'Toolchain, API keys, first model call, and the mindset shift from deterministic to probabilistic code.',
  '01': 'Prompt anatomy, few-shot, chain-of-thought, structured outputs, validation, prompt versioning, and caching.',
  '02': 'Embeddings, vector stores, chunking, naive RAG through agentic RAG, hybrid search, and evaluation harness.',
  '03': 'Function calling, tool schema design, MCP servers and clients, production tool patterns, and security.',
  '04': 'The agent loop from scratch, patterns (routing, orchestrator-workers, evaluator-optimizer), SDKs, multi-agent.',
  '05': 'Error analysis, golden sets, LLM-as-judge, eval harnesses, CI for prompts, drift detection, and A/B testing.',
  '06': 'FastAPI wrapping, streaming, Docker, rate limits, fallbacks, versioning, feature flags, and deploy paths.',
  '07': 'OTel GenAI tracing, cost engineering, semantic caching, latency profiling, SLOs, and load testing.',
  '08': 'OWASP LLM Top 10, prompt injection defenses, PII handling, guardrails, and content moderation.',
  '09': 'The decision ladder, dataset engineering, SFT, LoRA, DPO, distillation, and serving open-weight models.',
  '10': 'Vision-language models, document AI, speech, voice agents, realtime APIs, and multimodal RAG.',
  '11': 'Scoping, discovery, demo-to-production, messy customer environments, handoff, and stakeholder communication.',
  '12': 'Six capstone projects combining all prior phases into shippable, evaluated, observable portfolio pieces.',
};

// ── Arabic (ar) curriculum strings ──────────────────────────────────────────
// Lesson titles are sourced from each ar.md H1 at build time. The maps below
// cover what does not live in the markdown: phase titles, phase descriptions,
// and the 13 lessons whose ar.md (mirroring its en.md) has no title heading.
const PHASE_TITLES_AR = {
  '00': 'الإعداد وعقلية الذكاء الاصطناعي التطبيقي',
  '01': 'هندسة الموجِّهات والسياق',
  '02': 'الاسترجاع وRAG',
  '03': 'الأدوات واستدعاء الدوال وMCP',
  '04': 'الوكلاء: أنماط تصمد في الإنتاج',
  '05': 'التقييم والتطوير القائم على التقييم',
  '06': 'الشحن إلى الإنتاج: من الدفتر إلى خدمة إنتاجية',
  '07': 'القابلية للمراقبة والتكلفة والموثوقية',
  '08': 'الأمان والسلامة وحواجز الحماية',
  '09': 'الضبط الدقيق والتخصيص',
  '10': 'ما وراء النص: متعدد الوسائط والصوت',
  '11': 'مهارات المهندس الميداني (Forward-Deployed)',
  '12': 'المشاريع الختامية: ابنِ معرض أعمالك',
};

const PHASE_DESCRIPTIONS_AR = {
  '00': 'سلسلة الأدوات، ومفاتيح الـ API، وأول استدعاء للنموذج، والتحوّل الذهني من الكود الحتمي إلى الكود الاحتمالي.',
  '01': 'تشريح الموجِّه، والأمثلة القليلة (few-shot)، وسلسلة التفكير (chain-of-thought)، والمخرجات المنظَّمة، والتحقق، وإصدارات الموجِّهات، والتخزين المؤقت.',
  '02': 'التضمينات (embeddings)، ومخازن المتجهات، والتقطيع (chunking)، وRAG من البسيط إلى الوكيلي، والبحث الهجين، وإطار التقييم.',
  '03': 'استدعاء الدوال، وتصميم مخطط الأدوات، وخوادم وعملاء MCP، وأنماط الأدوات الإنتاجية، والأمان.',
  '04': 'حلقة الوكيل من الصفر، والأنماط (التوجيه، والمنسِّق-العمال، والمقيِّم-المحسِّن)، وحِزَم التطوير (SDKs)، وتعدّد الوكلاء.',
  '05': 'تحليل الأخطاء، والمجموعات الذهبية، ونموذج LLM كحَكَم، وأُطُر التقييم، والتكامل المستمر للموجِّهات، وكشف الانحراف، واختبار A/B.',
  '06': 'التغليف بـ FastAPI، والبث، وDocker، وحدود المعدّل، والبدائل الاحتياطية، والإصدارات، وأعلام الميزات، ومسارات النشر.',
  '07': 'تتبّع OTel للذكاء التوليدي، وهندسة التكلفة، والتخزين المؤقت الدلالي، وتحليل زمن الاستجابة، وأهداف مستوى الخدمة (SLOs)، واختبار الحِمل.',
  '08': 'قائمة OWASP لأخطر 10 ثغرات في نماذج اللغة، ودفاعات حقن الموجِّهات، والتعامل مع البيانات الشخصية (PII)، وحواجز الحماية، وإشراف المحتوى.',
  '09': 'سلّم القرار، وهندسة مجموعات البيانات، والضبط الخاضع للإشراف (SFT)، وLoRA، وDPO، والتقطير، وتقديم النماذج مفتوحة الأوزان.',
  '10': 'نماذج الرؤية واللغة، والذكاء الاصطناعي للمستندات، والكلام، والوكلاء الصوتيون، وواجهات الزمن الفعلي، وRAG متعدد الوسائط.',
  '11': 'تحديد النطاق، والاستكشاف، والانتقال من العرض التوضيحي إلى الإنتاج، وبيئات العملاء الفوضوية، والتسليم، والتواصل مع أصحاب المصلحة.',
  '12': 'ستة مشاريع ختامية تجمع كل المراحل السابقة في أعمال قابلة للشحن ومُقيَّمة وقابلة للمراقبة تصلح لمعرض الأعمال.',
};

// Lessons whose ar.md has no title H1 (the en.md lacks one too). Keyed by phase/lesson id.
const LESSON_TITLE_AR_OVERRIDES = {
  '05': {
    '04': 'بناء مجموعة ذهبية (Golden Set)',
    '05': 'المقاييس المهمة مقابل مقاييس الغرور',
    '06': 'نموذج LLM كحَكَم: البناء والمعايرة ومعرفة أنماط فشله',
    '07': 'التقييمات الزوجية والمرجعية',
    '08': 'أُطُر التقييم: من الخام إلى Braintrust / LangSmith / Phoenix',
    '09': 'التكامل المستمر للموجِّهات: اختبار الانحدار عند كل تغيير',
    '10': 'تقييم RAG والوكلاء والأنظمة متعددة الخطوات',
    '11': 'التقييمات الفورية وحلقات التغذية الراجعة في الإنتاج',
    '12': 'كشف الانحراف والانحدار',
    '13': 'اختبار A/B لميزات نماذج اللغة',
    '14': 'مشروع ختامي: التطوير القائم على التقييم لميزة',
  },
  '09': {
    '04': 'LoRA / QLoRA: الحدس وتطبيق عملي',
    '05': 'تقييم نموذج مُحسَّن (Fine-Tune) مقابل خطّ الأساس',
  },
};

// Reads the Arabic lesson title from the ar.md H1 (first non-empty line).
// Returns null when the first non-empty line is not an H1 (handled via overrides).
function getArLessonTitle(phaseSlug, lessonSlug) {
  const arPath = path.join(PHASES_DIR, phaseSlug, lessonSlug, 'docs', 'ar.md');
  if (!fs.existsSync(arPath)) return null;
  const lines = fs.readFileSync(arPath, 'utf8').split('\n');
  for (const line of lines) {
    const t = line.trim();
    if (!t) continue;
    const m = t.match(/^#\s+(.+)$/);
    return m ? m[1].trim() : null;
  }
  return null;
}

// Translates the English time estimate (e.g. "~45 min", "~8 hours") to Arabic.
function translateTime(time) {
  if (!time) return time;
  return time.replace(/(\d+(?:\.\d+)?)\s*(hours?|minutes?|min)\b/gi, (_, num, unit) => {
    if (/^h/i.test(unit)) {
      const n = parseFloat(num);
      return `${num} ${n >= 3 && n <= 10 ? 'ساعات' : 'ساعة'}`;
    }
    return `${num} دقيقة`;
  });
}

function glyphToStatus(glyph) {
  if (glyph === '✅') return 'complete';
  if (glyph === '🚧') return 'progress';
  return 'planned';
}

function parseRoadmap(content) {
  const phases = [];
  const lines = content.split('\n');
  let currentPhase = null;

  for (const line of lines) {
    // ## Phase 05: Title [✅] (~15 hours)
    const phaseMatch = line.match(/^## Phase (\d+):\s*(.+?)\s*\[([✅🚧⬚])\]\s*\((.+?)\)/);
    if (phaseMatch) {
      currentPhase = {
        id: phaseMatch[1].padStart(2, '0'),
        title: phaseMatch[2].trim(),
        status: glyphToStatus(phaseMatch[3]),
        time: phaseMatch[4].trim(),
        description: PHASE_DESCRIPTIONS[phaseMatch[1].padStart(2, '0')] || '',
        slug: null,
        lessons: [],
      };
      phases.push(currentPhase);
      continue;
    }

    // | 01 | Lesson Name | ✅ | ~45 min |
    if (currentPhase) {
      const lessonMatch = line.match(/^\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*([✅🚧⬚])\s*\|\s*(.+?)\s*\|/);
      if (lessonMatch) {
        currentPhase.lessons.push({
          id: lessonMatch[1].padStart(2, '0'),
          title: lessonMatch[2].trim(),
          status: glyphToStatus(lessonMatch[3]),
          time: lessonMatch[4].trim(),
          slug: null,
          artifact: null,
        });
      }
    }
  }

  return phases;
}

function getSubdirs(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true })
    .filter(d => d.isDirectory() && /^\d{2}-/.test(d.name))
    .map(d => d.name);
}

function getPhaseFolderMap() {
  const map = {};
  for (const folder of getSubdirs(PHASES_DIR)) {
    map[folder.slice(0, 2)] = folder;
  }
  return map;
}

function getLessonFolderMap(phaseFolder) {
  const map = {};
  for (const folder of getSubdirs(path.join(PHASES_DIR, phaseFolder))) {
    map[folder.slice(0, 2)] = folder;
  }
  return map;
}

function getLessonArtifact(phaseSlug, lessonSlug) {
  const outputDir = path.join(PHASES_DIR, phaseSlug, lessonSlug, 'outputs');
  if (!fs.existsSync(outputDir)) return null;
  const files = fs.readdirSync(outputDir).filter(f => f.endsWith('.md'));
  return files[0] || null;
}

function getLessonNotebook(phaseId, lessonSlug) {
  const nbPath = path.join(ROOT, 'notebooks', `phase-${phaseId}`, `${lessonSlug}.ipynb`);
  return fs.existsSync(nbPath) ? `notebooks/phase-${phaseId}/${lessonSlug}.ipynb` : null;
}

function main() {
  const roadmap = fs.readFileSync(ROADMAP_PATH, 'utf8');
  const phases = parseRoadmap(roadmap);
  const phaseFolders = getPhaseFolderMap();

  for (const phase of phases) {
    phase.title_ar = PHASE_TITLES_AR[phase.id] || phase.title;
    phase.description_ar = PHASE_DESCRIPTIONS_AR[phase.id] || phase.description;
    phase.time_ar = translateTime(phase.time);

    phase.slug = phaseFolders[phase.id] || null;
    if (!phase.slug) continue;

    const lessonFolders = getLessonFolderMap(phase.slug);
    for (const lesson of phase.lessons) {
      lesson.time_ar = translateTime(lesson.time);
      lesson.slug = lessonFolders[lesson.id] || null;
      if (lesson.slug) {
        lesson.artifact = getLessonArtifact(phase.slug, lesson.slug);
        lesson.notebook = getLessonNotebook(phase.id, lesson.slug);
        lesson.title_ar =
          getArLessonTitle(phase.slug, lesson.slug) ||
          (LESSON_TITLE_AR_OVERRIDES[phase.id] && LESSON_TITLE_AR_OVERRIDES[phase.id][lesson.id]) ||
          lesson.title;
      } else {
        lesson.title_ar = lesson.title;
      }
    }
  }

  const totalLessons = phases.reduce((s, p) => s + p.lessons.length, 0);
  const completeLessons = phases.reduce(
    (s, p) => s + p.lessons.filter(l => l.status === 'complete').length, 0
  );
  const completePhases = phases.filter(p => p.status === 'complete').length;
  const progressPhases = phases.filter(p => p.status === 'progress').length;

  const data = {
    generated: new Date().toISOString().slice(0, 10),
    stats: { totalPhases: phases.length, completePhases, progressPhases, totalLessons, completeLessons },
    phases,
  };

  const output = `// Generated by site/build.js — do not edit manually
// Regenerate: node site/build.js
window.CURRICULUM = ${JSON.stringify(data, null, 2)};
`;

  fs.writeFileSync(OUTPUT_PATH, output);
  console.log(`site/data.js generated`);
  console.log(`  ${phases.length} phases  |  ${completeLessons}/${totalLessons} lessons complete  |  ${completePhases} phases done`);
}

main();
