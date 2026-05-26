---
marp: true
theme: applied-ai
class: title
paginate: true
footer: 'Applied AI From Scratch · Phase 04: Agents'
---

# Phase 04: Agents

### Patterns That Survive Production

**Applied AI From Scratch**
16 lessons · ~18 hours · Python + TypeScript

<!-- SPEAKER: Welcome to Phase 04. Agents are the most hyped and most misunderstood pattern in AI engineering. By the end, you will know exactly when to use an agent, when not to, and how to make it reliable in production. Time: ~5 min -->

---

## Who this is for

You are a **working software engineer** who:

- Has called an LLM API and gotten a structured response
- Has used tool/function calling (or skipped it and are paying for that)
- Wants to build agents that **don't blow up in production**

**What you will NOT get:**
- Agents presented as magic
- Frameworks without understanding what they do
- 5-step tutorials that stop before the system crashes

<!-- SPEAKER: Set realistic expectations. Agents are not magic. They are loops with tools and memory. The challenge is making those loops reliable. -->

---

## What you will build

| Artifact | Lesson |
|----------|--------|
| Raw agent loop (~120 lines, zero deps) | 04-01 |
| Prompt chaining pipeline | 04-03 |
| Parallelized voting system | 04-05 |
| Orchestrator-worker scaffold | 04-06 |
| ReAct agent with tool recovery | 04-09 |
| Multi-agent supervisor (when warranted) | 04-12 |
| Production agent: tracing + guardrails | Capstone |

<!-- SPEAKER: Every lesson ships a reusable artifact. By the capstone you have a complete production agent scaffold. -->

---
<!-- _class: section -->

## The Core Mental Model

### What is an agent, really?

---

## The agent loop

The raw loop. No framework. No magic.

```python
def agent_loop(task: str, tools: list[Tool]) -> str:
    messages = [{"role": "user", "content": task}]
    while True:
        response = client.messages.create(
            model="claude-opus-4-5",
            messages=messages,
            tools=[t.schema for t in tools],
        )
        if response.stop_reason == "end_turn":
            return response.content[0].text
        if response.stop_reason == "tool_use":
            tool_results = execute_tools(response.content, tools)
            messages.extend(build_tool_messages(response, tool_results))
```

Loop = call model, check stop reason, execute tools, repeat.

<!-- SPEAKER: This is the whole thing. 120 lines with error handling, cost governor, and timeout. The frameworks add ergonomics on top of this core. -->

---

## Agent loop: the flow

<div class="mermaid">
flowchart TD
    A([Task]) --> B[Call Model]
    B --> C{Stop reason?}
    C -->|end_turn| D([Return answer])
    C -->|tool_use| E[Execute tools]
    E --> F[Append results]
    F --> G{Budget limit?}
    G -->|exceeded| H([Abort])
    G -->|ok| B
    style A fill:#4f46e5,color:#fff
    style D fill:#10b981,color:#fff
    style H fill:#ef4444,color:#fff
</div>

<!-- SPEAKER: The kill switch is not optional. Runaway agents are a real production incident. Always have a cost governor. -->

---

## Workflows vs agents: the decision

**Use a workflow when** the steps are known in advance.

**Use an agent when** the next step depends on the result of the previous one.

| | Workflow | Agent |
|---|----------|-------|
| Control flow | Deterministic | Dynamic |
| Debugging | Easy | Hard |
| Cost | Predictable | Variable |
| Right for | Known pipelines | Open-ended tasks |

> Most production systems are **workflows** wearing agent costumes.

<!-- SPEAKER: This is the most important slide in the phase. Agents are expensive and hard to debug. Default to workflows. Agents earn their complexity. -->

---
<!-- _class: section -->

## The 5 Patterns

### From Anthropic's "Building Effective Agents"

---

## Pattern 1: Prompt Chaining

Output of step N feeds input of step N+1. Works when steps are independent and ordered.

<div class="mermaid">
flowchart LR
    A[Input] --> B[Step 1: Extract intent]
    B --> C[Step 2: Retrieve context]
    C --> D[Step 3: Generate response]
    D --> E[Output]
    style A fill:#1e1e1e,color:#e8e8e8,stroke:#4f46e5
    style E fill:#1e1e1e,color:#e8e8e8,stroke:#10b981
    style B fill:#141414,color:#a78bfa,stroke:#2a2a2a
    style C fill:#141414,color:#a78bfa,stroke:#2a2a2a
    style D fill:#141414,color:#a78bfa,stroke:#2a2a2a
</div>

**When to use:** multi-step generation, data transformation pipelines, document processing.

<!-- SPEAKER: This is the simplest pattern and often the most reliable. Data flows one direction. Easy to test, easy to debug. -->

---

## Pattern 2: Routing

Classifier sends input to the right specialized handler.

<div class="mermaid">
flowchart TD
    A[Input] --> B[Classifier LLM]
    B -->|billing| C[Billing Agent]
    B -->|technical| D[Tech Support Agent]
    B -->|general| E[General Agent]
    C --> F[Output]
    D --> F
    E --> F
    style B fill:#4f46e5,color:#fff
    style C fill:#141414,color:#e8e8e8,stroke:#2a2a2a
    style D fill:#141414,color:#e8e8e8,stroke:#2a2a2a
    style E fill:#141414,color:#e8e8e8,stroke:#2a2a2a
    style F fill:#10b981,color:#fff
</div>

**When to use:** different input types need different logic (customer support, query routing).

---

## Pattern 3: Parallelization

Two sub-patterns: **sectioning** and **voting**.

<div class="mermaid">
flowchart LR
    subgraph Sectioning
    A1[Long doc] --> B1[Chunk 1 to LLM]
    A1 --> B2[Chunk 2 to LLM]
    A1 --> B3[Chunk 3 to LLM]
    B1 & B2 & B3 --> C1[Aggregate]
    end
    subgraph Voting
    A2[Query] --> D1[LLM call 1]
    A2 --> D2[LLM call 2]
    A2 --> D3[LLM call 3]
    D1 & D2 & D3 --> E1[Majority vote]
    end
</div>

Sectioning = throughput. Voting = accuracy (at 3x cost).

<!-- SPEAKER: Voting is how you get near-deterministic answers from probabilistic models. Expensive but powerful for high-stakes decisions. -->

---

## Pattern 4: Orchestrator-Workers

One agent decomposes the task, N worker agents execute in parallel.

<div class="mermaid">
flowchart TD
    A([Task]) --> B[Orchestrator: decompose]
    B --> C[Worker 1: Subtask A]
    B --> D[Worker 2: Subtask B]
    B --> E[Worker 3: Subtask C]
    C & D & E --> F[Orchestrator: synthesize]
    F --> G([Final answer])
    style A fill:#4f46e5,color:#fff
    style B fill:#a78bfa,color:#0a0a0a
    style F fill:#a78bfa,color:#0a0a0a
    style G fill:#10b981,color:#fff
    style C fill:#1e1e1e,color:#e8e8e8
    style D fill:#1e1e1e,color:#e8e8e8
    style E fill:#1e1e1e,color:#e8e8e8
</div>

Workers can be specialized: code executor, web search, calculator.

---

## Pattern 5: Evaluator-Optimizer

Generator produces; evaluator scores and gives feedback; loop until threshold met.

<div class="mermaid">
flowchart LR
    A([Task]) --> B[Generator LLM]
    B --> C[Evaluator LLM]
    C -->|score below threshold| D[Feedback]
    D --> B
    C -->|score above threshold| E([Output])
    style A fill:#4f46e5,color:#fff
    style E fill:#10b981,color:#fff
    style C fill:#f59e0b,color:#0a0a0a
</div>

**The catch:** you need a reliable evaluator. A bad judge means infinite loops or wrong answers.

<!-- SPEAKER: This is the DSPy insight: if you can write a good eval, you can use it to optimize the generator automatically. The eval IS the bottleneck. -->

---
<!-- _class: section -->

## Production Concerns

### What the tutorials don't cover

---

## What breaks agents in production

| Failure mode | Cause | Fix |
|---|---|---|
| Infinite loop | No turn limit | `max_turns=20` governor |
| Cost explosion | Unbounded tool calls | Per-request budget cap |
| Tool timeout hang | No timeout on network calls | All tools: `timeout=10s` |
| Wrong tool called | Ambiguous tool descriptions | Sharp, exclusive tool schemas |
| Context overflow | Long tool outputs | Truncate + summarize |
| Silent wrong answer | No stopping condition check | Validate final output |

<!-- SPEAKER: Each of these is a real production incident that someone has paged for. The fixes are mostly boring: limits, timeouts, validation. -->

---

## The kill switch (non-optional)

```python
class CostGovernor:
    def __init__(self, max_turns: int = 20, max_cost_usd: float = 0.50):
        self.turns = 0
        self.cost = 0.0
        self.max_turns = max_turns
        self.max_cost = max_cost_usd

    def check(self, response) -> None:
        self.turns += 1
        self.cost += calculate_cost(response.usage)
        if self.turns >= self.max_turns:
            raise AgentBudgetExceeded(f"Turn limit {self.max_turns} reached")
        if self.cost >= self.max_cost:
            raise AgentBudgetExceeded(f"Cost limit ${self.max_cost:.2f} reached")
```

Wire this into the loop. No exceptions.

<!-- SPEAKER: A runaway agent at $50/request will get you paged. The governor is 20 lines and prevents a class of incidents entirely. -->

---

## Memory: only add when you need it

<div class="mermaid">
flowchart LR
    A{Memory needed?} -->|no - most agents| B[In-context messages]
    A -->|cross-session| C[External store: Redis or Postgres]
    A -->|user preferences| D[Key-value store: simple dict or DB]
    A -->|tool outputs over 50k tokens| E[Summarize into context]
    style A fill:#4f46e5,color:#fff
    style B fill:#10b981,color:#fff
</div>

Start with in-context memory. Add persistent memory only when users report forgetting things across sessions.

<!-- SPEAKER: The most common mistake is adding a vector DB for memory before you know you need it. In-context is fast, simple, and debuggable. -->

---

## Multi-agent: when it earns its complexity

**Use multi-agent when:**
- Tasks need parallel specialized workers (different tools, different system prompts)
- You need isolation between steps (one agent's context does not pollute another)
- Scale requires it (fan-out across thousands of items)

**Do NOT use multi-agent when:**
- You just want a "smarter" agent
- A single agent with more tools would work
- You want to debug it next week

Most production systems that claim to be multi-agent are **orchestrator-workers** with one hop.

<!-- SPEAKER: Multi-agent adds coordination overhead, communication cost, and debugging complexity. It's earned. Don't start there. -->

---
<!-- _class: section -->

## The Capstone

### A production agent with guardrails + tracing

---

## Capstone architecture

<div class="mermaid">
flowchart TD
    A([User request]) --> B[Input guardrail: Llama Guard]
    B -->|blocked| C([Reject with reason])
    B -->|pass| D[Agent loop with cost governor]
    D --> E{Tool calls}
    E --> F[Tool executor: timeout + validation]
    F --> D
    D --> G[Output guardrail: PII + content check]
    G --> H[OTel span: full trace]
    H --> I([Response])
    style A fill:#4f46e5,color:#fff
    style C fill:#ef4444,color:#fff
    style I fill:#10b981,color:#fff
    style B fill:#f59e0b,color:#0a0a0a
    style G fill:#f59e0b,color:#0a0a0a
    style H fill:#1e1e1e,color:#a78bfa,stroke:#4f46e5
</div>

<!-- SPEAKER: This is what a production agent looks like. Every box is a lesson. The capstone wires them together. -->

---

## What the capstone ships

```
phases/04-agents/16-capstone-agent/
├── code/
│   ├── agent.py           # core loop with cost governor
│   ├── tools.py           # tool registry + executor
│   ├── guardrails.py      # input + output validation
│   ├── tracing.py         # OTel GenAI spans
│   └── Dockerfile
├── outputs/
│   ├── agent-scaffold.md       # reusable scaffold
│   └── production-checklist.md # pre-deploy checklist
└── checks.json
```

**Deploy target:** Docker + any container host.

---

## Summary: the decisions

| Decision | Default |
|----------|---------|
| Workflow vs agent | Workflow unless next step truly unknown |
| Pattern choice | Prompt chaining first; escalate to orchestrator |
| Memory | In-context first; external only cross-session |
| Multi-agent | Single agent with more tools first |
| Kill switch | Always. `max_turns` + `max_cost`. |
| Observability | One OTel span per agent run, always |

<!-- SPEAKER: These are the defaults. Every deviation needs a reason. The defaults will serve you well for 90% of production agents. -->

---

## Further study

- **Anthropic "Building Effective Agents"** (2024) - the canonical patterns paper
- **MAST: Multi-Agent System Taxonomy** - failure mode catalog
- **LangGraph documentation** - when stateful graphs earn their place
- **OpenTelemetry GenAI conventions** - `gen_ai.*` span attributes

**Next phase:** Phase 05 Evaluation - how do you know the agent works?

---
<!-- _class: title -->

# Questions?

**Phase 04: Agents - Patterns That Survive Production**

Applied AI From Scratch
github.com/thepandanlabs/applied-ai-from-scratch

<!-- SPEAKER: Open for questions. If running a workshop, this is a good point for a 10-minute break before the hands-on section. -->

<!-- MERMAID INIT - enables diagram rendering in browser -->
<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
  mermaid.initialize({
    startOnLoad: true,
    theme: 'dark',
    themeVariables: {
      primaryColor: '#4f46e5',
      primaryTextColor: '#e8e8e8',
      primaryBorderColor: '#2a2a2a',
      lineColor: '#8a8a8a',
      secondaryColor: '#141414',
      tertiaryColor: '#1e1e1e',
      background: '#0a0a0a',
      mainBkg: '#141414',
      nodeBorder: '#2a2a2a',
      clusterBkg: '#1e1e1e',
      titleColor: '#a78bfa',
      edgeLabelBackground: '#1e1e1e',
      attributeBackgroundColorEven: '#141414',
      attributeBackgroundColorOdd: '#1e1e1e',
    }
  });
</script>
