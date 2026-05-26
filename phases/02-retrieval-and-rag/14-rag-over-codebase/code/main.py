# pip install sentence-transformers numpy
# ast, os, hashlib, pathlib are part of Python's standard library.
# No API key needed - sentence-transformers runs locally on CPU.

import ast
import os
import re
import textwrap
import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import NamedTuple, Optional

import numpy as np
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class CodeChunk(NamedTuple):
    """A semantic unit extracted from source code via AST parsing."""
    name: str           # function or class name
    kind: str           # 'function' or 'class'
    file_path: str      # path to source file
    lineno_start: int   # first line number (1-indexed)
    lineno_end: int     # last line number (inclusive)
    docstring: str      # extracted docstring, empty string if none
    source: str         # full source text of the definition
    content_hash: str   # MD5 hash for incremental indexing


# ---------------------------------------------------------------------------
# AST-based chunk extraction
# ---------------------------------------------------------------------------

def extract_chunks_from_file(filepath: str) -> list[CodeChunk]:
    """
    Parse a Python file with ast and extract all function and class definitions
    as CodeChunk objects.

    Works on: top-level functions, top-level classes, nested functions/methods.
    Preserves: name, kind, file path, line numbers, docstring, full source.
    """
    path = Path(filepath)
    try:
        source_text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"Could not read {filepath}: {e}")
        return []

    try:
        tree = ast.parse(source_text, filename=str(filepath))
    except SyntaxError as e:
        print(f"Syntax error in {filepath}: {e}")
        return []

    source_lines = source_text.splitlines(keepends=True)
    chunks = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue

        # end_lineno is available in Python 3.8+
        if not hasattr(node, "end_lineno"):
            continue

        start = node.lineno - 1   # convert to 0-indexed for slice
        end = node.end_lineno     # end_lineno is 1-indexed; slice [start:end] is correct

        node_source = "".join(source_lines[start:end])
        docstring = ast.get_docstring(node) or ""

        kind = "class" if isinstance(node, ast.ClassDef) else "function"
        content_hash = hashlib.md5(node_source.encode()).hexdigest()

        chunks.append(CodeChunk(
            name=node.name,
            kind=kind,
            file_path=str(path),
            lineno_start=node.lineno,
            lineno_end=node.end_lineno,
            docstring=docstring,
            source=node_source,
            content_hash=content_hash,
        ))

    return chunks


# ---------------------------------------------------------------------------
# Rich text representation for embedding
# ---------------------------------------------------------------------------

def chunk_to_embed_text(chunk: CodeChunk) -> str:
    """
    Build the text string that will be embedded for a code chunk.

    Why not just embed raw source?
    - Raw source has no natural language → poor semantic matching
    - Function name + docstring bridge code vocabulary to query vocabulary
    - File context helps with module-level queries

    Format:
      Function `name` in file.py (lines N–M):
      [docstring]

      [full source]
    """
    file_name = Path(chunk.file_path).name
    lines_ref = f"lines {chunk.lineno_start}–{chunk.lineno_end}"

    parts = [
        f"{chunk.kind.capitalize()} `{chunk.name}` in {file_name} ({lines_ref}):",
    ]

    if chunk.docstring:
        parts.append(chunk.docstring)

    parts.append("")  # blank line separator
    parts.append(chunk.source)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# In-memory codebase index
# ---------------------------------------------------------------------------

EMBED_MODEL = "all-MiniLM-L6-v2"   # 384-dim, fast on CPU, ~80MB download


class CodebaseIndex:
    """
    In-memory index of code chunks with vector embeddings.

    Supports:
    - build_from_directory: parse and index a full Python directory
    - query: vector similarity search
    - symbol_search: exact/partial function name lookup
    - hybrid_search: symbol matches first, vector results fill the rest
    - incremental_update: re-embed only modified files
    """

    def __init__(self, model_name: str = EMBED_MODEL):
        print(f"Loading embedding model: {model_name}...")
        self.model = SentenceTransformer(model_name)
        self.chunks: list[CodeChunk] = []
        self.vectors: Optional[np.ndarray] = None  # shape: (n_chunks, embed_dim)

    def add_chunks(self, chunks: list[CodeChunk]) -> None:
        """Embed and add chunks to the index."""
        if not chunks:
            return

        texts = [chunk_to_embed_text(c) for c in chunks]
        print(f"  Embedding {len(texts)} chunks...", end=" ", flush=True)
        new_vectors = self.model.encode(texts, show_progress_bar=False)
        print("done.")

        self.chunks.extend(chunks)

        if self.vectors is None:
            self.vectors = new_vectors
        else:
            self.vectors = np.vstack([self.vectors, new_vectors])

    def build_from_directory(self, directory: str, pattern: str = "**/*.py") -> None:
        """Walk a directory tree and index all matching Python files."""
        py_files = sorted(Path(directory).glob(pattern))
        print(f"Found {len(py_files)} Python file(s) in {directory}")

        all_chunks: list[CodeChunk] = []
        for filepath in py_files:
            file_chunks = extract_chunks_from_file(str(filepath))
            all_chunks.extend(file_chunks)
            print(f"  {filepath.name}: {len(file_chunks)} symbol(s)")

        self.add_chunks(all_chunks)
        print(f"Index built: {len(self.chunks)} total chunks.")

    def _cosine_scores(self, query_vec: np.ndarray) -> np.ndarray:
        """Compute cosine similarity between query_vec and all stored vectors."""
        if self.vectors is None or len(self.vectors) == 0:
            return np.array([])
        norms = np.linalg.norm(self.vectors, axis=1) * np.linalg.norm(query_vec)
        norms = np.where(norms == 0, 1e-10, norms)
        return self.vectors @ query_vec / norms

    def query(self, nl_query: str, top_k: int = 5) -> list[dict]:
        """
        Retrieve top-k most relevant code chunks for a natural language query.
        Returns: list of {chunk, score, rank}
        """
        if not self.chunks:
            return []

        query_vec = self.model.encode([nl_query])[0]
        scores = self._cosine_scores(query_vec)

        if len(scores) == 0:
            return []

        top_k = min(top_k, len(scores))
        top_indices = np.argsort(scores)[::-1][:top_k]

        return [
            {"chunk": self.chunks[i], "score": float(scores[i]), "rank": rank + 1}
            for rank, i in enumerate(top_indices)
        ]

    def symbol_search(self, name: str) -> list[dict]:
        """
        Exact and partial symbol name lookup (case-insensitive).
        Ranks exact matches first, then prefix matches, then substring matches.
        """
        name_lower = name.lower()
        exact, prefix, substring = [], [], []

        for chunk in self.chunks:
            chunk_name_lower = chunk.name.lower()
            if chunk_name_lower == name_lower:
                exact.append({"chunk": chunk, "score": 1.0, "rank": 1})
            elif chunk_name_lower.startswith(name_lower):
                prefix.append({"chunk": chunk, "score": 0.9, "rank": 1})
            elif name_lower in chunk_name_lower:
                substring.append({"chunk": chunk, "score": 0.7, "rank": 1})

        results = exact + prefix + substring
        for rank, r in enumerate(results, 1):
            r["rank"] = rank
        return results

    def hybrid_search(self, query: str, top_k: int = 5) -> list[dict]:
        """
        Hybrid: symbol matches first (ranked high), then vector similarity.

        Extracts potential symbol names from the query (backtick-quoted,
        snake_case, or CamelCase words), then merges with vector results.
        Symbol exact matches are always ranked above vector results.
        """
        # Extract symbol candidates from query
        backtick = re.findall(r'`([\w_]+)`', query)
        quoted = re.findall(r'[\'\"]([\w_]+)[\'\"]', query)
        snake_case = re.findall(r'\b([a-z][a-z_]{2,}[a-z])\b', query)
        camel_case = re.findall(r'\b([A-Z][a-zA-Z]{2,})\b', query)
        candidates = list(dict.fromkeys(backtick + quoted + snake_case + camel_case))

        seen_keys: set[tuple] = set()
        symbol_hits: list[dict] = []

        for sym in candidates:
            for result in self.symbol_search(sym):
                key = (result["chunk"].file_path, result["chunk"].name)
                if key not in seen_keys:
                    symbol_hits.append(result)
                    seen_keys.add(key)

        # Vector search (fetch extra to account for dedup)
        vector_results = self.query(query, top_k=top_k + len(symbol_hits))

        for vr in vector_results:
            key = (vr["chunk"].file_path, vr["chunk"].name)
            if key not in seen_keys:
                symbol_hits.append(vr)
                seen_keys.add(key)

        # Re-rank and cap
        combined = symbol_hits[:top_k]
        for rank, item in enumerate(combined, 1):
            item["rank"] = rank

        return combined

    def incremental_update(self, filepath: str) -> int:
        """
        Re-index a single modified file: remove old chunks, add new ones.
        Returns the number of chunks changed.
        """
        # Remove old chunks from this file
        old_hashes = {c.content_hash for c in self.chunks if c.file_path == filepath}
        keep_mask = [c.file_path != filepath for c in self.chunks]

        if self.vectors is not None and len(keep_mask) > 0:
            keep_indices = [i for i, keep in enumerate(keep_mask) if keep]
            self.chunks = [self.chunks[i] for i in keep_indices]
            self.vectors = self.vectors[keep_indices] if keep_indices else None

        # Add new chunks
        new_chunks = extract_chunks_from_file(filepath)
        new_hashes = {c.content_hash for c in new_chunks}
        changed = len(old_hashes.symmetric_difference(new_hashes))
        self.add_chunks(new_chunks)
        return changed


# ---------------------------------------------------------------------------
# Line-based chunking for comparison
# ---------------------------------------------------------------------------

def line_chunk_file(filepath: str, chunk_size: int = 20) -> list[dict]:
    """
    Naive line-based chunking - what most document RAG systems do with code.
    Used for side-by-side comparison with AST-based chunking.
    """
    lines = Path(filepath).read_text(encoding="utf-8").splitlines()
    chunks = []
    for i in range(0, len(lines), chunk_size):
        chunk_lines = lines[i:i + chunk_size]
        chunks.append({
            "text": "\n".join(chunk_lines),
            "start_line": i + 1,
            "end_line": min(i + chunk_size, len(lines)),
        })
    return chunks


def compare_chunking_strategies(
    filepath: str,
    query: str,
    model: SentenceTransformer,
    top_k: int = 3,
) -> None:
    """
    Side-by-side comparison: line-chunking vs AST-chunking for a given query.
    Demonstrates why line chunking loses code semantics.
    """
    file_name = Path(filepath).name
    print(f"\n{'=' * 65}")
    print(f"COMPARISON: Line chunking vs AST chunking")
    print(f"File: {file_name}  |  Query: \"{query}\"")
    print(f"{'=' * 65}")

    query_vec = model.encode([query])[0]

    # Line-chunking results
    line_chunks = line_chunk_file(filepath, chunk_size=15)
    if line_chunks:
        lc_texts = [c["text"] for c in line_chunks]
        lc_vecs = model.encode(lc_texts, show_progress_bar=False)
        norms = np.linalg.norm(lc_vecs, axis=1) * np.linalg.norm(query_vec)
        norms = np.where(norms == 0, 1e-10, norms)
        lc_scores = lc_vecs @ query_vec / norms
        top_lc = np.argsort(lc_scores)[::-1][:top_k]

        print(f"\n--- LINE-CHUNKED (15 lines/chunk) ---")
        for rank, i in enumerate(top_lc, 1):
            c = line_chunks[i]
            preview = c["text"][:250].strip()
            print(f"\n  Rank {rank} (score: {lc_scores[i]:.3f}, lines {c['start_line']}–{c['end_line']}):")
            print(textwrap.indent(preview, "    "))
            if len(c["text"]) > 250:
                print("    ... [truncated]")

    # AST-chunking results
    ast_chunks = extract_chunks_from_file(filepath)
    if ast_chunks:
        ast_texts = [chunk_to_embed_text(c) for c in ast_chunks]
        ast_vecs = model.encode(ast_texts, show_progress_bar=False)
        norms = np.linalg.norm(ast_vecs, axis=1) * np.linalg.norm(query_vec)
        norms = np.where(norms == 0, 1e-10, norms)
        ast_scores = ast_vecs @ query_vec / norms
        top_ast = np.argsort(ast_scores)[::-1][:top_k]

        print(f"\n--- AST-CHUNKED (1 symbol = 1 chunk) ---")
        for rank, i in enumerate(top_ast, 1):
            c = ast_chunks[i]
            doc = f"\n    Docstring: \"{c.docstring[:80]}\"" if c.docstring else ""
            print(
                f"\n  Rank {rank} (score: {ast_scores[i]:.3f}):\n"
                f"    {c.kind.upper()}: `{c.name}` - {Path(c.file_path).name} "
                f"lines {c.lineno_start}–{c.lineno_end}{doc}"
            )
    else:
        print("\n  (no AST chunks extracted)")


# ---------------------------------------------------------------------------
# Sample codebase for demo
# ---------------------------------------------------------------------------

SAMPLE_AUTH_CODE = '''"""
auth.py - Authentication, session management, and rate limiting.
"""

import hashlib
import secrets
import time
from typing import Optional


def authenticate(username: str, password: str) -> Optional[dict]:
    """
    Verify user credentials against the database.
    Returns the user record dict if valid, None if invalid.
    Uses SHA-256 password hashing with a per-user salt.
    """
    user = _db_find_user(username)
    if not user:
        return None
    expected_hash = hashlib.sha256(
        (password + user["salt"]).encode()
    ).hexdigest()
    if expected_hash != user["password_hash"]:
        return None
    return user


def create_session(user_id: int, ttl_seconds: int = 3600) -> str:
    """
    Create a new authentication session for the given user.
    Returns a secure random session token (64 hex chars).
    Session expires after ttl_seconds (default: 1 hour).
    """
    token = secrets.token_hex(32)
    expiry = int(time.time()) + ttl_seconds
    _session_store[token] = {"user_id": user_id, "expiry": expiry}
    return token


def validate_session(token: str) -> Optional[int]:
    """
    Check if a session token is valid and not expired.
    Returns the user_id if valid, None if expired or not found.
    Automatically removes expired sessions from the store.
    """
    session = _session_store.get(token)
    if not session:
        return None
    if time.time() > session["expiry"]:
        del _session_store[token]
        return None
    return session["user_id"]


def logout(token: str) -> bool:
    """
    Invalidate a session token immediately.
    Returns True if the session existed and was removed, False otherwise.
    """
    if token in _session_store:
        del _session_store[token]
        return True
    return False


def reset_password(email: str) -> str:
    """
    Generate a time-limited password reset token for the given email address.
    Token expires after 15 minutes. Returns the token string.
    """
    token = secrets.token_urlsafe(24)
    expiry = int(time.time()) + 900
    _reset_tokens[email] = {"token": token, "expiry": expiry}
    return token


def apply_rate_limit(user_id: int, endpoint: str, limit: int = 100) -> bool:
    """
    Check and enforce rate limits using a sliding 1-minute window counter.
    Returns True if the request is allowed, False if the user is rate-limited.
    Each (user_id, endpoint) pair has its own counter.
    """
    key = f"{user_id}:{endpoint}"
    current_window = int(time.time()) // 60
    count = _rate_counters.get((key, current_window), 0)
    if count >= limit:
        return False
    _rate_counters[(key, current_window)] = count + 1
    return True


# In-memory stores (use Redis in production)
_session_store: dict = {}
_reset_tokens: dict = {}
_rate_counters: dict = {}


def _db_find_user(username: str) -> Optional[dict]:
    """Internal stub: look up user by username."""
    users = {
        "alice": {"id": 1, "salt": "abc123", "password_hash": "demo_hash"},
    }
    return users.get(username)
'''


def write_sample_codebase(directory: str) -> str:
    """Write sample auth.py to a directory. Returns file path."""
    os.makedirs(directory, exist_ok=True)
    filepath = os.path.join(directory, "auth.py")
    with open(filepath, "w") as f:
        f.write(SAMPLE_AUTH_CODE)
    return filepath


# ---------------------------------------------------------------------------
# Main demo
# ---------------------------------------------------------------------------

def main():
    tmpdir = tempfile.mkdtemp(prefix="coderag_")
    try:
        print("Creating sample codebase...")
        sample_file = write_sample_codebase(tmpdir)

        # Load the model once - reuse across comparisons
        print(f"\nLoading embedding model: {EMBED_MODEL}")
        model = SentenceTransformer(EMBED_MODEL)

        # ----------------------------------------------------------------
        # Part 1: Show the chunking strategy difference
        # ----------------------------------------------------------------
        compare_chunking_strategies(
            filepath=sample_file,
            query="how is authentication handled?",
            model=model,
            top_k=3,
        )

        compare_chunking_strategies(
            filepath=sample_file,
            query="where is the rate limiter?",
            model=model,
            top_k=3,
        )

        # ----------------------------------------------------------------
        # Part 2: Build a full AST-based index and run retrieval
        # ----------------------------------------------------------------
        print(f"\n{'=' * 65}")
        print("FULL CODEBASE INDEX (AST-based)")
        print(f"{'=' * 65}")

        index = CodebaseIndex(model_name=EMBED_MODEL)
        index.build_from_directory(tmpdir)

        demo_queries = [
            "how does login work?",
            "where is the session token created?",
            "how are passwords hashed?",
            "show me the logout function",
            "how do I reset a user password?",
            "what handles the rate limit check?",
        ]

        print()
        for query in demo_queries:
            print(f"Query: \"{query}\"")
            results = index.hybrid_search(query, top_k=3)
            for r in results:
                c = r["chunk"]
                doc_preview = f" - {c.docstring[:55]}..." if c.docstring else ""
                print(f"  [{r['rank']}] {c.kind} `{c.name}` (score={r['score']:.3f}){doc_preview}")
            print()

        # ----------------------------------------------------------------
        # Part 3: Evaluation
        # ----------------------------------------------------------------
        print(f"{'=' * 65}")
        print("RETRIEVAL EVALUATION - top-3 hit rate")
        print(f"{'=' * 65}")

        eval_set = [
            {"query": "verify user credentials against the database", "expected": "authenticate"},
            {"query": "start a new user session", "expected": "create_session"},
            {"query": "is this session still valid?", "expected": "validate_session"},
            {"query": "how to log the user out", "expected": "logout"},
            {"query": "enforce request rate limits", "expected": "apply_rate_limit"},
            {"query": "generate password reset token", "expected": "reset_password"},
        ]

        hits = 0
        for item in eval_set:
            results = index.query(item["query"], top_k=3)
            top3 = [r["chunk"].name for r in results]
            hit = item["expected"] in top3
            hits += int(hit)
            mark = "HIT " if hit else "MISS"
            print(f"  [{mark}] \"{item['query'][:45]}\"")
            print(f"         expected: {item['expected']!r}  |  got: {top3}")

        rate = hits / len(eval_set)
        print(f"\nTop-3 hit rate: {hits}/{len(eval_set)} = {rate * 100:.0f}%")

        # ----------------------------------------------------------------
        # Part 4: Incremental update demo
        # ----------------------------------------------------------------
        print(f"\n{'=' * 65}")
        print("INCREMENTAL UPDATE DEMO")
        print(f"{'=' * 65}")

        # Modify the file slightly and re-index only that file
        with open(sample_file, "a") as f:
            f.write('\n\ndef check_2fa(user_id: int, code: str) -> bool:\n'
                    '    """Verify a two-factor authentication code for a user."""\n'
                    '    return len(code) == 6 and code.isdigit()\n')

        changed = index.incremental_update(sample_file)
        print(f"File modified. Chunks changed: {changed}")
        print(f"Index now has: {len(index.chunks)} chunks")

        # Verify new function is retrievable
        results = index.query("two factor authentication", top_k=3)
        print("\nQuery: 'two factor authentication'")
        for r in results:
            print(f"  [{r['rank']}] {r['chunk'].kind} `{r['chunk'].name}` (score={r['score']:.3f})")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
