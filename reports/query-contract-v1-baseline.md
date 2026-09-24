# Query API contract V1 baseline

- Scope: deterministic engineering regression of `/api/v1/query` and `/api/v1/query/session`.
- Result: 12/12 cases passed. The JSON report records the dataset SHA-256, catalog version, exact Git commit, and per-case results.
- Execution: `conda run -n medsafety python -m evaluation.query_contract --output reports/query-contract-v1-baseline.json`.
- Environment: FastAPI `TestClient`, in-memory session store, LLM planning disabled; no Redis, Neo4j, or Ollama service required.
- Limits: all four source-aligned facts occur in development data. This result is not independent clinical accuracy or unseen-fact generalization.
- Known gap: when a question mixes an unrecognized named product with a recognized product, the deterministic resolver may retain only the recognized product and return `no_known_risk_in_scope`. This input-boundary problem needs a separate resolver change and negative regression cases.
