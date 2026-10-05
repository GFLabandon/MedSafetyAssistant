# Full-stack live smoke, 2026-09-24

Command: `conda run -n medsafety npm run test:e2e:live` from `frontend/`.

Result: **1/1 passed**. Playwright started real Vite and FastAPI servers, submitted a known risk pair, observed a 200 response with the allowed `127.0.0.1:4173` origin, and rendered its fact ID and FDA source link. A second question with an unmatched pair operand returned a clarification; the old risk claim disappeared and the page showed that session context was not saved.

The smoke deliberately points Redis and Ollama to an unavailable local port and leaves Neo4j disabled. It verifies the JSON-catalog fallback and browser/API wiring. It does not verify Redis persistence, Neo4j projection, model quality, clinical accuracy, or a deployed environment. The browser contract suite remains separate and uses simulated API responses.
