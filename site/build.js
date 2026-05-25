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

function main() {
  const roadmap = fs.readFileSync(ROADMAP_PATH, 'utf8');
  const phases = parseRoadmap(roadmap);
  const phaseFolders = getPhaseFolderMap();

  for (const phase of phases) {
    phase.slug = phaseFolders[phase.id] || null;
    if (!phase.slug) continue;

    const lessonFolders = getLessonFolderMap(phase.slug);
    for (const lesson of phase.lessons) {
      lesson.slug = lessonFolders[lesson.id] || null;
      if (lesson.slug) {
        lesson.artifact = getLessonArtifact(phase.slug, lesson.slug);
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
