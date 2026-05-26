# Roadmap

Status tracker for every phase and lesson. Glyphs are parsed by `site/build.js` to power the curriculum navigator. Do not change their format.

Total estimated time: ~200 hours, at your own pace.

**Legend:** ✅ Complete · 🚧 In Progress · ⬚ Planned

---

## Phase 00: Setup & the Applied AI Mindset [✅] (~8 hours)

| # | Lesson | Status | Est. |
|---|--------|--------|------|
| 01 | Dev Environment (uv, Node/TS) | ✅ | ~45 min |
| 02 | API Keys, Providers & the 2026 Model Landscape | ✅ | ~45 min |
| 03 | First API Call: Python + TypeScript, Streaming, Tokens | ✅ | ~45 min |
| 04 | The Probabilistic Mindset: Why Deterministic Thinking Breaks | ✅ | ~45 min |
| 05 | Reading Model Docs: Context Windows, Pricing, Limits | ✅ | ~30 min |
| 06 | Cost & Latency from Line One | ✅ | ~45 min |
| 07 | Git + Running the Lesson Repo | ✅ | ~30 min |
| 08 | Docker Basics for AI Apps | ✅ | ~45 min |
| 09 | Notebook vs Script vs Service | ✅ | ~30 min |
| 10 | Debugging Non-Deterministic Systems | ✅ | ~45 min |

---

## Phase 01: Prompt & Context Engineering [✅] (~15 hours)

| # | Lesson | Status | Est. |
|---|--------|--------|------|
| 01 | Request Anatomy: System, User, Assistant | ✅ | ~45 min |
| 02 | Prompt Fundamentals | ✅ | ~45 min |
| 03 | Few-Shot & Chain-of-Thought | ✅ | ~60 min |
| 04 | Context Engineering | ✅ | ~60 min |
| 05 | Context-Window Management | ✅ | ~45 min |
| 06 | Structured Outputs: JSON Schema, Constrained Decoding | ✅ | ~60 min |
| 07 | Validation + Retry Loops: Pydantic / Zod | ✅ | ~60 min |
| 08 | Prompt Templates & Versioning | ✅ | ~45 min |
| 09 | Programmatic Prompt Optimization: DSPy | ✅ | ~60 min |
| 10 | Multi-Turn Conversations & State | ✅ | ~45 min |
| 11 | System Prompt Design | ✅ | ~45 min |
| 12 | Handling Refusals & Edge Cases | ✅ | ~45 min |
| 13 | Prompt Caching: Cost and Latency | ✅ | ~45 min |
| 14 | Capstone: Structured-Extraction Service + Prompt Library | ✅ | ~90 min |

---

## Phase 02: Retrieval & RAG [✅] (~17 hours)

| # | Lesson | Status | Est. |
|---|--------|--------|------|
| 01 | Embeddings Intuition | ✅ | ~45 min |
| 02 | Embedding Models | ✅ | ~50 min |
| 03 | Vector Stores | ✅ | ~55 min |
| 04 | Chunking Strategies | ✅ | ~60 min |
| 05 | Naive RAG: End-to-End, No Framework | ✅ | ~75 min |
| 06 | Retrieval Metrics | ✅ | ~60 min |
| 07 | Hybrid Search: BM25 + Dense + Reranking | ✅ | ~75 min |
| 08 | Query Transformation | ✅ | ~70 min |
| 09 | Citation Grounding | ✅ | ~60 min |
| 10 | RAG Evaluation: the RAG Triad + LLM-as-Judge | ✅ | ~75 min |
| 11 | Advanced RAG: Parent-Doc, Multi-Vector, Contextual | ✅ | ~70 min |
| 12 | Agentic RAG: Retrieval as a Tool | ✅ | ~70 min |
| 13 | Structured Retrieval: Text-to-SQL | ✅ | ~65 min |
| 14 | RAG Over a Codebase | ✅ | ~70 min |
| 15 | RAG Frameworks: LlamaIndex + LangChain | ✅ | ~60 min |
| 16 | Capstone: Production RAG Service | ✅ | ~90 min |

---

## Phase 03: Tools, Function Calling & MCP [✅] (~14 hours)

| # | Lesson | Status | Est. |
|---|--------|--------|------|
| 01 | Function Calling Fundamentals | ✅ | ~45 min |
| 02 | Tool Schema Design: the Agent-Computer Interface | ✅ | ~60 min |
| 03 | Parallel & Streaming Tool Calls | ✅ | ~45 min |
| 04 | Structured Tool Outputs & Error Handling | ✅ | ~45 min |
| 05 | Robust Tools: Idempotency, Timeouts, Validation | ✅ | ~60 min |
| 06 | MCP Fundamentals: Tools, Resources, Prompts, Sampling | ✅ | ~60 min |
| 07 | Build an MCP Server: Python + TypeScript | ✅ | ~75 min |
| 08 | Build an MCP Client | ✅ | ~60 min |
| 09 | MCP Transports: stdio, HTTP, Streamable | ✅ | ~45 min |
| 10 | MCP Resources & Prompts | ✅ | ~45 min |
| 11 | MCP Security: Tool Poisoning, OAuth 2.1, Prod Auth | ✅ | ~60 min |
| 12 | MCP Gateways & Registries | ✅ | ~45 min |
| 13 | Integrating Real Systems: DBs, SaaS APIs, Internal Tools | ✅ | ~75 min |
| 14 | Capstone: MCP Tool Ecosystem for a Domain | ✅ | ~90 min |

---

## Phase 04: Agents: Patterns That Survive Production [✅] (~18 hours)

| # | Lesson | Status | Est. |
|---|--------|--------|------|
| 01 | The Agent Loop: Raw, No Dependencies | ✅ | ~60 min |
| 02 | Workflows vs Agents: When NOT to Use an Agent | ✅ | ~45 min |
| 03 | Pattern: Prompt Chaining | ✅ | ~45 min |
| 04 | Pattern: Routing | ✅ | ~45 min |
| 05 | Pattern: Parallelization | ✅ | ~45 min |
| 06 | Pattern: Orchestrator-Workers | ✅ | ~60 min |
| 07 | Pattern: Evaluator-Optimizer | ✅ | ~60 min |
| 08 | Tool Use + Error Recovery in the Loop | ✅ | ~60 min |
| 09 | Memory: Short-Term, Long-Term, When You Don't Need It | ✅ | ~60 min |
| 10 | Planning: ReAct, Plan-and-Execute | ✅ | ~60 min |
| 11 | Stopping Conditions, Cost Governors, Kill Switches | ✅ | ~45 min |
| 12 | Agent SDKs: Claude, OpenAI, LangGraph Tradeoffs | ✅ | ~60 min |
| 13 | Multi-Agent: Supervisor, Handoffs, and When It Is Overkill | ✅ | ~60 min |
| 14 | Agent Failure Modes: MAST Taxonomy | ✅ | ~45 min |
| 15 | Human-in-the-Loop & Approval Gates | ✅ | ~45 min |
| 16 | Capstone: Production Agent with Guardrails + Tracing | ✅ | ~90 min |

---

## Phase 05: Evaluation & Eval-Driven Development [✅] (~15 hours)

| # | Lesson | Status | Est. |
|---|--------|--------|------|
| 01 | Why Evals Are the Job | ✅ | ~45 min |
| 02 | Error Analysis First: Look at Your Data | ✅ | ~60 min |
| 03 | Trace Review & Failure Taxonomy | ✅ | ~60 min |
| 04 | Building a Golden Set | ✅ | ~60 min |
| 05 | Metrics That Matter vs Vanity Metrics | ✅ | ~45 min |
| 06 | LLM-as-Judge: Build, Calibrate, Know Its Failure Modes | ✅ | ~75 min |
| 07 | Pairwise & Reference-Based Evals | ✅ | ~45 min |
| 08 | Eval Harnesses: Raw to Braintrust / LangSmith / Phoenix | ✅ | ~75 min |
| 09 | CI for Prompts: Regression on Every Change | ✅ | ~60 min |
| 10 | Evaluating RAG, Agents, Multi-Step Systems | ✅ | ~60 min |
| 11 | Online Evals & Production Feedback Loops | ✅ | ~60 min |
| 12 | Drift & Regression Detection | ✅ | ~45 min |
| 13 | A/B Testing LLM Features | ✅ | ~45 min |
| 14 | Capstone: Eval-First Development of a Feature | ✅ | ~90 min |

---

## Phase 06: Shipping It: Notebook to Production Service [⬚] (~15 hours)

| # | Lesson | Status | Est. |
|---|--------|--------|------|
| 01 | The Demo-to-Production Gap | ⬚ | ~45 min |
| 02 | Wrapping a Model in FastAPI | ⬚ | ~60 min |
| 03 | Streaming Responses: SSE, Async, Concurrency | ⬚ | ~60 min |
| 04 | Input Validation & Safe Output Handling | ⬚ | ~45 min |
| 05 | Docker Image for an AI App | ⬚ | ~60 min |
| 06 | Config & Secrets Management | ⬚ | ~45 min |
| 07 | Rate Limits, Retries, Backoff, Circuit Breakers | ⬚ | ~60 min |
| 08 | Fallbacks & Model Failover | ⬚ | ~45 min |
| 09 | Background Jobs & Batch APIs | ⬚ | ~45 min |
| 10 | A Minimal TypeScript Frontend | ⬚ | ~60 min |
| 11 | Deploying: Managed + Container Paths | ⬚ | ~60 min |
| 12 | Versioning Prompts, Models, Configs in Production | ⬚ | ~45 min |
| 13 | Feature Flags & Progressive Rollout | ⬚ | ~45 min |
| 14 | Capstone: Deploy a RAG-or-Agent App Publicly | ⬚ | ~90 min |

---

## Phase 07: Observability, Cost & Reliability [⬚] (~14 hours)

| # | Lesson | Status | Est. |
|---|--------|--------|------|
| 01 | Why LLM Observability Differs | ⬚ | ~45 min |
| 02 | OpenTelemetry GenAI Conventions | ⬚ | ~60 min |
| 03 | Instrument an App: Raw OTel to Langfuse / Phoenix | ⬚ | ~75 min |
| 04 | The Trace as the Unit of Debugging | ⬚ | ~60 min |
| 05 | Logging Prompts, Responses, Tool Calls | ⬚ | ~45 min |
| 06 | Cost Engineering: Token Accounting, Dashboards | ⬚ | ~60 min |
| 07 | Caching Deep-Dive: Prompt/Prefix + Semantic | ⬚ | ~75 min |
| 08 | Latency: p50/p95/p99, TTFT, Where Time Goes | ⬚ | ~60 min |
| 09 | Model Routing & LLM Gateways | ⬚ | ~60 min |
| 10 | Load Testing LLM APIs | ⬚ | ~45 min |
| 11 | SLOs, SLIs & Alerting for AI Features | ⬚ | ~45 min |
| 12 | Chaos & Failure Injection | ⬚ | ~45 min |
| 13 | Capstone: Full Observability + Cost Dashboard | ⬚ | ~90 min |

---

## Phase 08: Security, Safety & Guardrails [⬚] (~12 hours)

| # | Lesson | Status | Est. |
|---|--------|--------|------|
| 01 | Threat Model: OWASP LLM Top 10 (2025) | ⬚ | ~60 min |
| 02 | Prompt Injection: Direct, Indirect, Cross-Modal | ⬚ | ~60 min |
| 03 | Injection Defenses: Sandboxing, Allow-Lists, Dual-LLM | ⬚ | ~60 min |
| 04 | Sensitive Info Disclosure & System Prompt Leakage | ⬚ | ~45 min |
| 05 | Excessive Agency & Tool Permissioning | ⬚ | ~45 min |
| 06 | Output Handling & Downstream Injection | ⬚ | ~45 min |
| 07 | Guardrails: Raw to Llama Guard / NeMo | ⬚ | ~60 min |
| 08 | PII Detection & Redaction | ⬚ | ~45 min |
| 09 | Content Moderation & Refusal Design | ⬚ | ~45 min |
| 10 | Unbounded Consumption & Cost-DoS | ⬚ | ~45 min |
| 11 | Capstone: Harden the App Against the Top 10 | ⬚ | ~90 min |

---

## Phase 09: Fine-Tuning & Customization [⬚] (~10 hours)

| # | Lesson | Status | Est. |
|---|--------|--------|------|
| 01 | The Decision Ladder: Prompt, RAG, or Finetune? | ⬚ | ~45 min |
| 02 | Dataset Engineering: the Durable Moat | ⬚ | ~60 min |
| 03 | Supervised Fine-Tuning: Managed APIs First | ⬚ | ~60 min |
| 04 | LoRA / QLoRA: Intuition + Hands-On Run | ⬚ | ~75 min |
| 05 | Evaluating a Fine-Tune vs Baseline | ⬚ | ~60 min |
| 06 | Preference Tuning: DPO | ⬚ | ~45 min |
| 07 | Distillation for Cost | ⬚ | ~45 min |
| 08 | Serving an Open-Weight Model: vLLM | ⬚ | ~60 min |
| 09 | Capstone: Fine-Tune for a Domain Task, Prove ROI with Evals | ⬚ | ~90 min |

---

## Phase 10: Beyond Text: Multimodal & Voice [⬚] (~10 hours)

| # | Lesson | Status | Est. |
|---|--------|--------|------|
| 01 | Vision-Language Models in Apps | ⬚ | ~45 min |
| 02 | Document AI: OCR to Structured Pipelines | ⬚ | ~60 min |
| 03 | Image Generation in Products | ⬚ | ~45 min |
| 04 | Speech-to-Text & Text-to-Speech | ⬚ | ~45 min |
| 05 | Building a Voice Agent | ⬚ | ~75 min |
| 06 | Realtime APIs & Voice Latency | ⬚ | ~60 min |
| 07 | Multimodal RAG | ⬚ | ~60 min |
| 08 | Multimodal Evals & Cross-Modal Injection | ⬚ | ~45 min |
| 09 | Capstone: A Multimodal Feature | ⬚ | ~75 min |

---

## Phase 11: The Forward-Deployed Skillset [⬚] (~10 hours)

| # | Lesson | Status | Est. |
|---|--------|--------|------|
| 01 | What an FDE Actually Does | ⬚ | ~45 min |
| 02 | Scoping Before Solving: Requirements Gathering | ⬚ | ~60 min |
| 03 | Discovery: Vague Ask to AI Spec | ⬚ | ~60 min |
| 04 | Choosing the Right Pattern | ⬚ | ~45 min |
| 05 | Demos That Survive Real Data | ⬚ | ~60 min |
| 06 | Mid-Stream Scope Changes & Expectation Setting | ⬚ | ~45 min |
| 07 | Integrating into a Messy Customer Environment | ⬚ | ~60 min |
| 08 | Measuring Business Impact | ⬚ | ~45 min |
| 09 | Handoff: Docs, Runbooks, Teaching the Team | ⬚ | ~60 min |
| 10 | Communicating with Non-Technical Stakeholders | ⬚ | ~45 min |

---

## Phase 12: Capstones: Build the Portfolio [⬚] (~18 hours)

| # | Lesson | Status | Est. |
|---|--------|--------|------|
| 01 | Production RAG Assistant Over a Real Corpus | ⬚ | ~3 hours |
| 02 | Customer-Support Agent with Tools + Guardrails + HITL | ⬚ | ~3 hours |
| 03 | Talk-to-Your-Data Analytics App (Text-to-SQL) | ⬚ | ~2.5 hours |
| 04 | Coding Automation Agent on a Real Repo | ⬚ | ~3 hours |
| 05 | Multimodal Feature: Voice or Document Extraction | ⬚ | ~2.5 hours |
| 06 | FDE Mock Engagement: Scope, Ship, Handoff | ⬚ | ~3 hours |
| 07 | Portfolio Packaging + Interview Prep | ⬚ | ~1 hour |
