# Forking This Curriculum

How to adapt appliedaifromscratch.com for a specific domain or organization.

---

## Why Fork

This curriculum is built for a general practitioner audience. You may want to fork it if you are building for a specific domain (fintech, healthcare, internal tooling), need to remove phases that are not relevant to your context, or want to integrate company-specific tooling and delivery patterns. A focused fork is more useful to your audience than the general version.

---

## What the License Allows

MIT license. Fork freely. Use commercially. Adapt as needed. Keep the LICENSE file in your fork. Attribution is appreciated but not required.

---

## How to Fork Well

Start by removing phases rather than adding. A 6-phase curriculum that is fully relevant beats a 12-phase curriculum where half the lessons do not apply to your context.

After you have cut the scope:

1. Update README.md to reflect your domain's angle on the manifesto. The framing that works for a general audience will not land the same way for an internal healthcare engineering team.
2. Update Phase 11 (Forward-Deployed Skillset) to reflect your delivery context. A consulting shop has different last-mile concerns than an internal platform team.
3. Replace the blessed stack section with your stack. If your organization has approved vendors, list them. If you are opinionated about libraries, say so.
4. Keep the 7-beat lesson format. It works. The Problem-Concept-Build-Use-Ship-Evaluate-Exercises structure is why lessons feel complete rather than like blog posts.

---

## What Not to Change

Three things are load-bearing for tooling and should stay as-is:

- **checks.json format** - used by the /gate playbook. Change the schema and the gate breaks.
- **outputs/ frontmatter format** - used by the artifact catalog. Fields must match exactly.
- **Phase and lesson folder naming convention** - must stay NN-kebab-case. Tooling depends on this pattern for indexing.

Everything else is yours to adapt.

---

## Tell Us What You Built

If you build something useful on this fork, open an issue on the original repo and let us know. We are interested in what domains people take this into and what structural changes turn out to work well.
