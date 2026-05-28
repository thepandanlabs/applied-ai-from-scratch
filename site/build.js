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

const PHASE_TITLES_AR = {
  '00': 'الإعداد والعقلية',
  '01': 'هندسة الـ Prompt والسياق',
  '02': 'الاسترجاع و RAG',
  '03': 'الأدوات واستدعاء الدوال و MCP',
  '04': 'الوكلاء: أنماط تصمد في الإنتاج',
  '05': 'التقييم والتطوير المبني على التقييم',
  '06': 'الإطلاق: من Notebook إلى خدمة',
  '07': 'المراقبة والتكلفة والموثوقية',
  '08': 'الأمان والسلامة وحواجز الحماية',
  '09': 'الضبط الدقيق (Fine-Tuning) والتخصيص',
  '10': 'ما بعد النص: متعدد الوسائط والصوت',
  '11': 'مهارات المهندس المنتشَر ميدانيًا (FDE)',
  '12': 'مشاريع التتويج (Capstones)',
};

const PHASE_DESCRIPTIONS_AR = {
  '00': 'سلسلة الأدوات، ومفاتيح الـ API، وأول استدعاء للنموذج، والانتقال الذهني من الكود الحتمي إلى الاحتمالي.',
  '01': 'تشريح الـ prompt، والأمثلة القليلة (few-shot)، وسلسلة التفكير (chain-of-thought)، والمخرجات المنظَّمة، والتحقق، وإصدارات الـ prompt، والـ caching.',
  '02': 'الـ embeddings، ومخازن المتجهات (vector stores)، والتقطيع (chunking)، من RAG البسيط إلى RAG الوكيلي، والبحث الهجين، ومنظومة التقييم.',
  '03': 'استدعاء الدوال (function calling)، وتصميم مخطط الأدوات، وخوادم وعملاء MCP، وأنماط الأدوات الإنتاجية، والأمان.',
  '04': 'حلقة الوكيل (agent loop) من الصفر، والأنماط (التوجيه، المنسّق-العمال، المُقيِّم-المُحسِّن)، والـ SDKs، وتعدّد الوكلاء.',
  '05': 'تحليل الأخطاء، والمجموعات الذهبية (golden sets)، والنموذج كحَكَم (LLM-as-judge)، ومنظومات التقييم، والـ CI للـ prompts، وكشف الانحراف، واختبارات A/B.',
  '06': 'تغليف النموذج بـ FastAPI، والبثّ (streaming)، و Docker، وحدود المعدّل، والبدائل (fallbacks)، وإدارة الإصدارات، وأعلام الميزات، ومسارات النشر.',
  '07': 'تتبّع OTel GenAI، وهندسة التكلفة، والـ caching الدلالي، وتحليل زمن الاستجابة، و SLOs، واختبار الحِمل.',
  '08': 'أعلى 10 مخاطر OWASP لنماذج اللغة، ودفاعات حقن الـ prompt، ومعالجة الـ PII، وحواجز الحماية، وتهذيب المحتوى.',
  '09': 'سُلّم القرار، وهندسة مجموعات البيانات، و SFT، و LoRA، و DPO، والتقطير (distillation)، وتشغيل النماذج مفتوحة الأوزان.',
  '10': 'نماذج الرؤية واللغة، وذكاء المستندات، والكلام، والوكلاء الصوتيون، وواجهات الزمن الحقيقي، و RAG متعدد الوسائط.',
  '11': 'تحديد النطاق، والاكتشاف، والانتقال من العرض إلى الإنتاج، وبيئات العملاء الفوضوية، والتسليم، والتواصل مع أصحاب المصلحة.',
  '12': 'ستة مشاريع تتويجية تجمع كل المراحل السابقة في قطع محفظة قابلة للإطلاق ومُقيَّمة وقابلة للمراقبة.',
};

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

// Pull the Arabic lesson title from the first H1 of docs/ar.md, if present.
function getLessonTitleAr(phaseSlug, lessonSlug) {
  const arPath = path.join(PHASES_DIR, phaseSlug, lessonSlug, 'docs', 'ar.md');
  if (!fs.existsSync(arPath)) return null;
  const content = fs.readFileSync(arPath, 'utf8');
  const m = content.match(/^#\s+(.+?)\s*$/m);
  return m ? m[1].trim() : null;
}

function main() {
  const roadmap = fs.readFileSync(ROADMAP_PATH, 'utf8');
  const phases = parseRoadmap(roadmap);
  const phaseFolders = getPhaseFolderMap();

  for (const phase of phases) {
    phase.title_ar = PHASE_TITLES_AR[phase.id] || null;
    phase.description_ar = PHASE_DESCRIPTIONS_AR[phase.id] || null;
    phase.slug = phaseFolders[phase.id] || null;
    if (!phase.slug) continue;

    const lessonFolders = getLessonFolderMap(phase.slug);
    for (const lesson of phase.lessons) {
      lesson.slug = lessonFolders[lesson.id] || null;
      if (lesson.slug) {
        lesson.artifact = getLessonArtifact(phase.slug, lesson.slug);
        lesson.notebook = getLessonNotebook(phase.id, lesson.slug);
        lesson.title_ar = getLessonTitleAr(phase.slug, lesson.slug);
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
