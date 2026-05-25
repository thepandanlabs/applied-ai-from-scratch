---
name: skill-vector-store-setup
description: >
  Guides setting up a vector store for a production use case. Covers the
  full decision path from in-memory local development through file-backed
  persistence to hosted Qdrant and pgvector. Includes configuration
  patterns, migration steps, and production readiness checks.
version: "1.0"
phase: "02"
lesson: "03"
tags:
  - vector-store
  - qdrant
  - pgvector
  - rag
  - retrieval
  - production
---

# Skill: Vector Store Setup

## Purpose

You are an applied AI engineering advisor specializing in vector storage and retrieval infrastructure. When a user needs to choose, set up, or debug a vector store, use this skill to guide them from their current state to a working production configuration.

---

## Decision Tree: Which Vector Store?

```
START: What is your situation?
  │
  ├─ "I'm prototyping / don't need persistence"
  │     → Use InMemoryVectorStore (custom, 50 lines) or Qdrant ':memory:'
  │     → Zero setup; loses data on restart; fine for dev
  │
  ├─ "I need persistence but don't want a server"
  │     → Qdrant local mode: QdrantClient(path='./qdrant_data')
  │     → File-backed; no Docker; survives restarts
  │     → pip install qdrant-client: that's it
  │
  ├─ "I already run Postgres and my corpus is < 5M vectors"
  │     → pgvector: add the extension, create an HNSW index
  │     → Stays in your existing DB; no new infra to operate
  │     → See pgvector setup section below
  │
  ├─ "I need ANN at scale (> 1M vectors) with filtering"
  │     → Qdrant server (Docker or Qdrant Cloud)
  │     → Best open-source dedicated vector DB; rich filter API
  │     → See Qdrant server setup section below
  │
  ├─ "I need fully managed (no ops)"
  │     → Qdrant Cloud, Pinecone, or Weaviate Cloud
  │     → Pay per vector, zero infra; good for early products
  │
  └─ "I need hybrid search (dense + sparse in one query)"
        → Qdrant (named vectors) or Weaviate
        → pgvector + pg_bm25 (ParadeDB) if staying in Postgres
```

---

## Setup Patterns

### Pattern 1: Qdrant In-Memory (Local Dev)

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

client = QdrantClient(":memory:")
client.create_collection(
    "my_docs",
    vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
)
```

No persistence. Good for: unit tests, notebooks, demos.

---

### Pattern 2: Qdrant File-Backed (Persistent Local)

```python
client = QdrantClient(path="./qdrant_data")
# Everything else is identical to :memory:
```

Data survives restarts. Good for: development, staging environments, single-server deployments.

---

### Pattern 3: Qdrant Server (Production)

```bash
# Docker (development)
docker run -p 6333:6333 -v $(pwd)/qdrant_data:/qdrant/storage qdrant/qdrant

# Or use Qdrant Cloud (https://cloud.qdrant.io)
```

```python
# Switch just this one line: rest of your code is unchanged
client = QdrantClient(
    url="https://your-cluster.cloud.qdrant.io",
    api_key="your-api-key",
)
```

---

### Pattern 4: pgvector (Stay in Postgres)

```sql
-- One-time setup (Postgres 15+)
CREATE EXTENSION IF NOT EXISTS vector;

-- Create table with vector column
CREATE TABLE documents (
    id          TEXT PRIMARY KEY,
    content     TEXT NOT NULL,
    embedding   vector(1536),   -- match your embedding model's dimension
    doc_type    TEXT,
    user_id     TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW index for approximate nearest neighbor search
-- m=16, ef_construction=64 are good starting values
CREATE INDEX ON documents USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

```python
# Python: psycopg2 + pgvector
import psycopg2
from pgvector.psycopg2 import register_vector

conn = psycopg2.connect("postgresql://user:pass@localhost/dbname")
register_vector(conn)

# Upsert
with conn.cursor() as cur:
    cur.execute(
        """
        INSERT INTO documents (id, content, embedding, doc_type, user_id)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE
          SET content = EXCLUDED.content,
              embedding = EXCLUDED.embedding
        """,
        (doc_id, text, vector.tolist(), doc_type, user_id),
    )
conn.commit()

# Search with filter
with conn.cursor() as cur:
    cur.execute(
        """
        SELECT id, content, 1 - (embedding <=> %s::vector) AS score
        FROM documents
        WHERE user_id = %s
        ORDER BY embedding <=> %s::vector
        LIMIT 5
        """,
        (query_vector.tolist(), user_id, query_vector.tolist()),
    )
    results = cur.fetchall()
```

---

## Production Readiness Checklist

Before going to production, verify:

**Data integrity:**
- [ ] Count parity: `store.count() == len(source_documents)`
- [ ] Spot-check 5 random documents: retrieve by ID and verify text matches source
- [ ] Verify metadata fields are indexed (for Qdrant: use `create_payload_index` on filtered fields)

**Index health:**
- [ ] HNSW index created (not using flat scan at scale)
- [ ] For pgvector: `EXPLAIN SELECT ...` shows Index Scan, not Seq Scan

**Update semantics:**
- [ ] Tested: update a document and verify the new version is retrieved, not the old one
- [ ] Tested: delete a document and verify it no longer appears in search results

**Filter correctness:**
- [ ] Test each filter field with a known-count check (see `check_filter_health` in code/main.py)
- [ ] Test filter with a value that has zero matches: verify empty list returned, no error

**Monitoring:**
- [ ] Alert on count parity drift (> 1% mismatch between source and index)
- [ ] Track p99 search latency; alert if above your SLA threshold
- [ ] Log and alert on zero-result queries (may indicate filter bug or empty index)

---

## Common Bugs and Fixes

**Bug: Stale documents in results after update**

Cause: upsert replaced the metadata/text but the old point ID is still in the index with the old vector.

Fix: Always upsert with the same ID AND the new vector in one operation. If your store requires delete + add, do them atomically (within a transaction for pgvector).

---

**Bug: Filter returns zero results for a field that clearly has data**

Causes and fixes:
1. Typo in field name → check exact spelling in stored metadata
2. Type mismatch (storing `"true"` as string, filtering for `True` as bool) → normalize types at insert time
3. For Qdrant: field not indexed → run `client.create_payload_index(collection, field_name, field_schema)`

---

**Bug: Wrong results after swapping embedding models**

Cause: Old vectors (from model A) and new vectors (from model B) are in the same collection. They live in incompatible coordinate spaces.

Fix: Never mix vectors from different models. Version your collections (e.g., `docs_v1`, `docs_v2`). Re-index everything when changing models. Use a blue/green strategy: build the new index while the old one serves traffic, swap when ready.

---

**Bug: HNSW returns worse results than expected**

Cause: HNSW `ef` (search breadth) parameter too low for the query.

Fix (Qdrant):
```python
client.search(
    collection_name="docs",
    query_vector=query_vec.tolist(),
    limit=10,
    search_params={"hnsw_ef": 128},  # default is 128; increase to 256 for better recall
)
```

Fix (pgvector):
```sql
SET hnsw.ef_search = 200;  -- run before your search query
```

---

## Migration Path (Dev → Production)

```
Phase 1: Local dev
  QdrantClient(":memory:")
  → Test all CRUD ops, verify filters, write unit tests

Phase 2: Persistent local
  QdrantClient(path="./qdrant_data")
  → Verify index survives restarts, test count parity after reload

Phase 3: Docker / Cloud
  QdrantClient(url="http://localhost:6333")   # Docker
  QdrantClient(url="https://...", api_key="...") # Cloud
  → Load test: verify latency under your expected QPS
  → Enable authentication and network isolation

Phase 4: Production hardening
  → Add payload indexes for all filtered fields
  → Set up backup schedule (Qdrant Cloud: automatic)
  → Configure monitoring: latency, error rate, collection size
  → Document embedding model version alongside collection name
```
