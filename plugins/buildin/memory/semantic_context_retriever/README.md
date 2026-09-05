# Semantic Context Retriever

BM25 context-selection provider for CorvinOS (ADR-0599 `context_retriever`).

Narrows/reorders already-gated CEL memory and TDE step candidates by relevance to the
query — **never adds content**. Torch-free, local, no network egress. Registers via the
`context_retriever` provider seam on load.

- **Type:** `context_retriever` provider (ADR-0598/0599)
- **Category:** memory · **Tier:** buildin
- **Security:** adversarial-reviewed, 0 critical/high/medium findings
- **Source:** `src/semantic_context_retriever.py`

See CorvinOS ADR-0598 for the design and the narrows-only / fail-open contract.
