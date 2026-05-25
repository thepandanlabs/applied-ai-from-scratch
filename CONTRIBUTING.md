# Contributing

Practical guide for contributors. Read this before opening a PR.

---

## What We Need Most

**New lesson content.** Planned phases include: prompt engineering foundations, retrieval and RAG, tool use and function calling, agents and orchestration, evals and reliability, deployment and observability, and the forward-deployed skillset. Open an issue before writing a new lesson so effort is not duplicated.

**Improvements to existing lessons.** Anything in this list is welcome without an issue first:
- checks.json questions that are definitional instead of scenario-based
- Code that does not run as written
- Broken or dead links in Further Reading

---

## Before You Write

1. Read LESSON_TEMPLATE.md cover to cover.
2. Look at a completed lesson in `phases/02-retrieval-and-rag/` as a reference for tone, structure, and what "done" looks like.
3. For new lessons: open a GitHub issue with the lesson title and a one-paragraph description. Wait for a green light before writing.

---

## Writing a Lesson

- Use the template. Fill every section. Do not skip beats.
- Run your code before submitting. If it requires credentials, note that clearly at the top of main.py.
- Check for em dashes before opening the PR. Use colons, commas, or hyphens instead.
- Make sure checks.json questions are scenario-based: "What do you do when X" not "What is X."

---

## PR Checklist

- [ ] Folder structure matches the template
- [ ] docs/en.md has all 7 beats including Evaluate It
- [ ] Real-world check in Build It, Perspective shift in Use It
- [ ] Code runs with the stated pip install
- [ ] checks.json questions are scenario-based
- [ ] outputs/ artifact has YAML frontmatter
- [ ] No em dashes

---

## Fixes and Improvements

Any PR is welcome for: broken code, outdated tool versions, better examples, improved checks.json questions. No issue needed for fixes.

---

## Questions

Open a GitHub issue. That is the right place for questions, proposals, and discussion.
