"""
Lesson 04-05: Pattern: Parallelization
Two sub-patterns: Sectioning (fan-out/fan-in) and Voting (majority pick).
"""

import asyncio
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import anthropic

# ---------------------------------------------------------------------------
# SUB-PATTERN 1: SECTIONING (async version)
# ---------------------------------------------------------------------------

async def summarize_document(client: anthropic.AsyncAnthropic, doc: str, doc_id: int) -> dict:
    """Summarize a single document. Designed to run concurrently."""
    message = await client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=256,
        messages=[
            {
                "role": "user",
                "content": f"Summarize this document in 2-3 sentences:\n\n{doc}"
            }
        ]
    )
    return {
        "doc_id": doc_id,
        "summary": message.content[0].text
    }


async def summarize_all(documents: list[str]) -> list[dict]:
    """Fan-out: run all summaries concurrently. Fan-in: collect results."""
    client = anthropic.AsyncAnthropic()

    tasks = [
        summarize_document(client, doc, i)
        for i, doc in enumerate(documents)
    ]

    results = await asyncio.gather(*tasks)
    return list(results)


async def synthesize_summaries(summaries: list[dict]) -> str:
    """Merge step: synthesize all summaries into a final report."""
    client = anthropic.AsyncAnthropic()

    summaries_text = "\n\n".join(
        f"Document {s['doc_id']}:\n{s['summary']}"
        for s in sorted(summaries, key=lambda x: x["doc_id"])
    )

    message = await client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": (
                    "You have received summaries of multiple documents. "
                    "Write a 1-paragraph synthesis that identifies the key themes "
                    "across all documents.\n\n"
                    f"{summaries_text}"
                )
            }
        ]
    )
    return message.content[0].text


async def research_pipeline(documents: list[str]) -> str:
    """Full sectioning pipeline: parallel summarize then synthesize."""
    print(f"Summarizing {len(documents)} documents in parallel...")
    start = time.time()

    summaries = await summarize_all(documents)

    elapsed = time.time() - start
    print(f"All {len(documents)} summaries done in {elapsed:.1f}s")

    print("Synthesizing summaries...")
    synthesis = await synthesize_summaries(summaries)
    return synthesis


# ---------------------------------------------------------------------------
# SUB-PATTERN 2: VOTING (async version)
# ---------------------------------------------------------------------------

async def synthesize_votes(text: str, votes: list[str]) -> str:
    """Fallback when there is no clear majority: ask the model to resolve."""
    client = anthropic.AsyncAnthropic()
    message = await client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=64,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Three classifiers disagreed on this text: {votes}. "
                    f"Text: '{text}'. "
                    "Give the single best label: POSITIVE, NEGATIVE, or NEUTRAL."
                )
            }
        ]
    )
    return message.content[0].text.strip().upper()


async def vote_on_classification(text: str, n_votes: int = 3) -> str:
    """
    Run the same classification prompt N times with temperature > 0.
    Return the majority vote or synthesize on a tie.
    """
    client = anthropic.AsyncAnthropic()

    async def single_vote(vote_id: int) -> str:
        message = await client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=64,
            temperature=0.7,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Classify the sentiment of this text as exactly one of: "
                        "POSITIVE, NEGATIVE, or NEUTRAL.\n"
                        "Respond with only the label.\n\n"
                        f"Text: {text}"
                    )
                }
            ]
        )
        return message.content[0].text.strip().upper()

    votes = await asyncio.gather(*[single_vote(i) for i in range(n_votes)])
    print(f"Votes received: {votes}")

    counts = Counter(votes)
    winner, count = counts.most_common(1)[0]

    if count > n_votes // 2:
        return winner
    else:
        return await synthesize_votes(text, list(votes))


# ---------------------------------------------------------------------------
# SYNC VERSION: ThreadPoolExecutor (for non-async codebases)
# ---------------------------------------------------------------------------

def summarize_document_sync(args: tuple) -> dict:
    """Sync version. Takes a tuple because executor.map passes single args."""
    client, doc, doc_id = args
    message = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=256,
        messages=[{"role": "user", "content": f"Summarize in 2-3 sentences:\n\n{doc}"}]
    )
    return {"doc_id": doc_id, "summary": message.content[0].text}


def summarize_all_sync(documents: list[str], max_workers: int = 10) -> list[dict]:
    """ThreadPoolExecutor version for sync codebases."""
    client = anthropic.Anthropic()
    args = [(client, doc, i) for i, doc in enumerate(documents)]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(summarize_document_sync, args))

    return results


def vote_sync(text: str, n_votes: int = 3) -> str:
    """Voting pattern via threads."""
    client = anthropic.Anthropic()

    def single_vote(_: int) -> str:
        message = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=64,
            temperature=0.7,
            messages=[{
                "role": "user",
                "content": (
                    "Classify as POSITIVE, NEGATIVE, or NEUTRAL. "
                    f"Respond with only the label.\n\nText: {text}"
                )
            }]
        )
        return message.content[0].text.strip().upper()

    with ThreadPoolExecutor(max_workers=n_votes) as executor:
        votes = list(executor.map(single_vote, range(n_votes)))

    print(f"Votes: {votes}")
    counts = Counter(votes)
    return counts.most_common(1)[0][0]


# ---------------------------------------------------------------------------
# DEMO
# ---------------------------------------------------------------------------

SAMPLE_DOCUMENTS = [
    "Quantum computing leverages superposition and entanglement to process information in ways classical computers cannot. IBM and Google are racing to achieve practical quantum advantage for real-world problems.",
    "The Mediterranean diet, rich in olive oil, fish, and vegetables, has been linked to reduced cardiovascular disease risk in multiple large-scale studies spanning decades of research.",
    "Remote work adoption accelerated dramatically during 2020 and many companies found productivity remained stable or improved. However, collaboration and culture challenges emerged as persistent concerns.",
    "CRISPR-Cas9 gene editing technology allows precise modification of DNA sequences. Therapeutic applications include sickle cell disease treatment and potential cures for genetic disorders.",
    "Electric vehicle battery technology continues to improve with energy density increasing roughly 5-8% annually. Solid-state batteries are expected to reach commercial scale by 2027.",
]

SAMPLE_REVIEWS = [
    "This product completely changed my morning routine. I feel more energized and focused.",
    "It was okay, nothing special. Does what it says but I expected more.",
    "Terrible experience. Broke after two weeks and customer service was unresponsive.",
]


async def main():
    print("=" * 60)
    print("DEMO 1: Sectioning (parallel document summaries)")
    print("=" * 60)

    result = await research_pipeline(SAMPLE_DOCUMENTS[:3])
    print("\nSynthesis:")
    print(result)

    print("\n" + "=" * 60)
    print("DEMO 2: Voting (sentiment classification)")
    print("=" * 60)

    for review in SAMPLE_REVIEWS:
        print(f"\nReview: {review[:60]}...")
        label = await vote_on_classification(review, n_votes=3)
        print(f"Majority vote: {label}")

    print("\n" + "=" * 60)
    print("DEMO 3: Sync version (ThreadPoolExecutor)")
    print("=" * 60)

    start = time.time()
    sync_results = summarize_all_sync(SAMPLE_DOCUMENTS[:3], max_workers=3)
    elapsed = time.time() - start
    print(f"Sync parallel completed in {elapsed:.1f}s")
    for r in sync_results:
        print(f"  Doc {r['doc_id']}: {r['summary'][:80]}...")


if __name__ == "__main__":
    asyncio.run(main())
