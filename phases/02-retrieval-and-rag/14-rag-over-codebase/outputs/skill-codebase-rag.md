---
name: skill-codebase-rag
description: Guide for building a retrieval system over a software codebase - covers symbol-based chunking, AST parsing, incremental indexing, and cross-file queries.
version: "1.0"
phase: "02"
lesson: "14"
tags: [codebase-rag, ast-parsing, symbol-search, incremental-indexing]
---

# Skill: Building a Codebase Q&A System

Use this skill to build a retrieval system over a software codebase that answers natural language questions by finding the relevant functions, classes, and modules.

---

## Core Principle: Chunk by Symbol, Not by Line

Line-based chunking destroys code semantics. A function split in the middle has no context, no name, and cannot be used. Always chunk by semantic units.

The right unit of retrieval for code:
- **Function**: the most common query target
- **Class**: useful for "what methods does X have?" queries
- **Module/file**: useful for "which file handles X?" queries

---

## Step 1: Extract Symbols with ast

```python
import ast
from pathlib import Path

def extract_functions_and_classes(filepath: str) -> list[dict]:
    """Parse a Python file and extract all function/class definitions."""
    source = Path(filepath).read_text(encoding="utf-8")
    tree = ast.parse(source)
    source_lines = source.splitlines(keepends=True)

    chunks = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if not hasattr(node, "end_lineno"):
            continue

        start = node.lineno - 1
        node_source = "".join(source_lines[start:node.end_lineno])
        kind = "class" if isinstance(node, ast.ClassDef) else "function"

        chunks.append({
            "name": node.name,
            "kind": kind,
            "file": filepath,
            "lineno_start": node.lineno,
            "lineno_end": node.end_lineno,
            "docstring": ast.get_docstring(node) or "",
            "source": node_source,
        })

    return chunks
```

For TypeScript: use `@typescript-eslint/typescript-estree` or `tree-sitter`.
For Go: use `go/ast` from the standard library.
For Rust: use `syn` crate or `tree-sitter-rust`.
The AST pattern is identical across all languages.

---

## Step 2: Build the Rich Text Representation

```python
def to_embed_text(chunk: dict) -> str:
    """
    Combine name + docstring + source for embedding.
    Do NOT embed raw source alone: it has no natural language.
    """
    file_name = Path(chunk["file"]).name
    parts = [
        f"{chunk['kind'].capitalize()} `{chunk['name']}` in {file_name}:",
    ]
    if chunk["docstring"]:
        parts.append(chunk["docstring"])
    parts.append("")
    parts.append(chunk["source"])
    return "\n".join(parts)
```

The embedding text must contain the function **name** and **docstring**: these are what match query vocabulary. Pure source code has little semantic signal for queries like "how does authentication work?"

---

## Step 3: Index All Symbols

```python
from sentence_transformers import SentenceTransformer
import numpy as np

def build_index(directory: str, model_name: str = "all-MiniLM-L6-v2") -> dict:
    """Build a codebase index from all Python files in a directory."""
    model = SentenceTransformer(model_name)

    all_chunks = []
    for filepath in Path(directory).rglob("*.py"):
        chunks = extract_functions_and_classes(str(filepath))
        all_chunks.extend(chunks)

    texts = [to_embed_text(c) for c in all_chunks]
    vectors = model.encode(texts)  # shape: (n_chunks, 384)

    return {"chunks": all_chunks, "vectors": vectors, "model": model}
```

---

## Step 4: Query the Index

```python
def query_codebase(question: str, index: dict, top_k: int = 5) -> list[dict]:
    """Retrieve the top-k most relevant code chunks for a question."""
    model = index["model"]
    query_vec = model.encode([question])[0]

    vectors = index["vectors"]
    norms = np.linalg.norm(vectors, axis=1) * np.linalg.norm(query_vec)
    norms = np.where(norms == 0, 1e-10, norms)
    scores = vectors @ query_vec / norms

    top_indices = np.argsort(scores)[::-1][:top_k]
    return [
        {"chunk": index["chunks"][i], "score": float(scores[i])}
        for i in top_indices
    ]
```

---

## Step 5: Incremental Indexing (On Git Change)

Re-embed the entire codebase every time any file changes is expensive. Use content hashing to only re-embed modified symbols:

```python
import hashlib

def get_symbol_hash(source: str) -> str:
    return hashlib.md5(source.encode()).hexdigest()

# On each file change:
def update_index_for_file(filepath: str, index: dict) -> int:
    """Re-index a single file. Returns number of changed chunks."""
    model = index["model"]

    # Remove old chunks for this file
    old_chunks = [(i, c) for i, c in enumerate(index["chunks"]) if c["file"] == filepath]
    old_hashes = {c["source"] for _, c in old_chunks}
    keep = [i for i, c in enumerate(index["chunks"]) if c["file"] != filepath]
    index["chunks"] = [index["chunks"][i] for i in keep]
    index["vectors"] = index["vectors"][keep]

    # Add new chunks
    new_chunks = extract_functions_and_classes(filepath)
    new_hashes = {c["source"] for c in new_chunks}
    changed = len(old_hashes.symmetric_difference(new_hashes))

    if new_chunks:
        texts = [to_embed_text(c) for c in new_chunks]
        new_vecs = model.encode(texts)
        index["chunks"].extend(new_chunks)
        index["vectors"] = np.vstack([index["vectors"], new_vecs])

    return changed
```

---

## Query Scoping

Scope queries to a subset of the codebase for better precision:

```python
def query_in_scope(question: str, index: dict, file_pattern: str = None, top_k: int = 5) -> list[dict]:
    """
    Restrict retrieval to chunks matching a file pattern.
    Example: file_pattern="auth" retrieves only from auth*.py files.
    """
    if file_pattern:
        scoped_chunks = [c for c in index["chunks"] if file_pattern in c["file"]]
        scoped_vectors = np.array([
            index["vectors"][i]
            for i, c in enumerate(index["chunks"]) if file_pattern in c["file"]
        ])
        # Build a temporary scoped index
        scoped_index = {**index, "chunks": scoped_chunks, "vectors": scoped_vectors}
        return query_codebase(question, scoped_index, top_k=top_k)
    return query_codebase(question, index, top_k=top_k)
```

---

## Evaluation

Build an eval set of (natural language query, expected function name) pairs:

```python
eval_set = [
    {"query": "how does login work?", "expected": "authenticate"},
    {"query": "where is the rate limiter?", "expected": "apply_rate_limit"},
    {"query": "create a new session", "expected": "create_session"},
]

hits = 0
for item in eval_set:
    results = query_codebase(item["query"], index, top_k=3)
    top3_names = [r["chunk"]["name"] for r in results]
    if item["expected"] in top3_names:
        hits += 1

print(f"Top-3 hit rate: {hits}/{len(eval_set)} = {hits/len(eval_set)*100:.0f}%")
```

Target: **>80% top-3 hit rate** on a representative eval set. If you're below 80%, common fixes:
- Add more context to `to_embed_text()` (better docstrings help more than longer source)
- Use a better model (`all-mpnet-base-v2` vs `all-MiniLM-L6-v2`)
- Add symbol search as a fallback for queries that contain function names

---

## Production Checklist

- [ ] AST-based chunking (never line-based for code)
- [ ] Rich embed text: name + docstring + source (not source alone)
- [ ] Content hashing for incremental indexing
- [ ] Symbol name lookup as a complement to vector search
- [ ] File-level scoping for large codebases
- [ ] Eval set of 20+ (query, expected function) pairs
- [ ] Top-3 hit rate >80% before connecting to an LLM for answer generation
- [ ] Multi-language: same pattern works with ast/tree-sitter/typescript-estree
