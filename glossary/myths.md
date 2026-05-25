# AI Engineering Myths

Common misconceptions practitioners encounter constantly.
Each one has caused real production failures or wasted engineering time.

---

## "More context is always better"

**Reality:** Relevant context improves answers. Irrelevant context degrades them. Studies on lost-in-the-middle attention show models struggle to retrieve facts from the middle of long prompts. Stuffing a context window with loosely related documents increases noise, raises cost, and can cause the model to ignore the content that actually matters. Retrieval and filtering exist for a reason.

---

## "RAG solves hallucination"

**Reality:** RAG reduces hallucination for knowledge retrieval tasks by grounding responses in retrieved documents. It does not eliminate hallucination. A model can still confabulate details not in the retrieved context, misinterpret what it retrieved, or hallucinate when the retrieved content is ambiguous. Grounding reduces the surface area; it does not seal it.

---

## "Fine-tuning is always better than prompting"

**Reality:** Fine-tuning is expensive, slow to iterate, and brittle when the underlying model is updated. The correct order is: prompt first, then add RAG, then consider fine-tuning if you have labeled data and a clear behavioral gap that neither prompts nor retrieval can close. Most teams that jump to fine-tuning regret it.

---

## "LLM-as-judge is circular and unreliable"

**Reality:** Poorly calibrated LLM judges are unreliable. Well-built ones are not. Research consistently shows that LLM judges with detailed rubrics, reference answers, and calibration against human annotations achieve agreement rates of 85% or higher on structured evaluation tasks. The failure mode is lazy judge prompts, not the technique itself.

---

## "Agents are just better chatbots"

**Reality:** Agents are software with non-deterministic decision-making baked in. They fail in ways chatbots do not: tool call loops, context exhaustion, planning errors that compound over multiple steps, and security vulnerabilities from processing untrusted input. Building an agent requires a different engineering discipline than building a chat interface.

---

## "Vector search finds the right answer"

**Reality:** Vector search finds semantically similar text. Similarity is not correctness. A chunk about a related topic can score higher than the chunk with the actual answer. Retrieval precision is a measured property, not a guarantee. This is why retrieval metrics, reranking, and the RAG Triad exist.

---

## "Prompt engineering is not real engineering"

**Reality:** Prompts are the primary interface to a stochastic system. They encode business logic, constraints, output format requirements, and persona. They need versioning, regression testing, and CI pipelines. A prompt change can silently break downstream parsing, eval scores, or safety behaviors. Treating prompts as informal text is how you end up with silent production regressions.

---

## "If the demo worked, the product will work"

**Reality:** The demo-to-production gap is where the majority of AI projects fail. Demos use curated inputs. Production has typos, adversarial users, edge cases, schema changes in upstream data, and latency requirements. The demo proves the approach is plausible. Evals, observability, and a real deployment pipeline prove it works.

---

## "Bigger model equals better results"

**Reality:** Model size matters less than task-model fit, context quality, and eval discipline. A well-prompted smaller model with clean retrieved context frequently outperforms a larger model with a vague prompt and noisy context. Bigger models also cost more and have higher latency. Start with the smallest model that can plausibly do the task, then upgrade only when evals show a gap.

---

## "You need a GPU to build AI applications"

**Reality:** API-based development requires no local GPU. You can build and ship production RAG pipelines, agents, and evaluation frameworks entirely against hosted APIs. Local GPU access matters for fine-tuning and for organizations with data residency requirements. For the vast majority of applied AI work, a laptop and API keys are sufficient.

---

## "Semantic similarity equals relevance"

**Reality:** Cosine similarity measures the angle between two vectors in embedding space. It reflects distributional similarity in the training corpus, not factual correctness or task-specific relevance. Two chunks about the same topic can have high cosine similarity while one directly answers the query and the other discusses something tangentially related. Retrieval metrics like MRR and nDCG exist because cosine similarity alone is not a reliable proxy for retrieval quality.

---

## "Frameworks make everything easier"

**Reality:** Frameworks add abstraction layers that reduce boilerplate at the cost of debuggability and flexibility. When something goes wrong, you are debugging two systems: your application logic and the framework's behavior. Raw API calls with explicit logic are easier to test, trace, and modify. Adopt a framework when the complexity of your own code exceeds the complexity of the framework's abstractions. Not before.

---

## "Evals are just tests you write after the fact"

**Reality:** Evals written after the fact measure the behavior you already built, not the behavior you need. Eval-driven development means defining what success looks like before writing application code, running evals on every change, and using metric regressions to catch drift. Error analysis comes before metrics infrastructure. Understanding how your system fails is more valuable than a dashboard that confirms it sometimes works.

---

## "Retrieval quality does not matter if the LLM is smart enough"

**Reality:** Even a highly capable model cannot reason correctly from missing or incorrect retrieved content. Garbage in, garbage out applies to RAG. The generation step is bounded by retrieval quality. A precision@5 of 0.4 means 60% of what you sent the model is irrelevant noise. No model compensates for systematically bad retrieval.

---

## "Streaming is just a UX improvement"

**Reality:** Streaming affects architecture in ways that go beyond perceived latency. Streaming changes how you handle errors, partial outputs, and tool call parsing. It affects how downstream systems consume responses. If you add streaming as an afterthought, you will likely need to refactor your output handling, error recovery logic, and any middleware that inspects model responses.
