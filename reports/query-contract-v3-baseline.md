# Query API contract V3 baseline

- Scope: deterministic engineering regression of `/api/v1/query` and `/api/v1/query/session`.
- Result: 19/19 cases passed. The JSON report records the dataset checksum, catalog version, implementation commit, and per-case results.
- Added cases: suffix-free Chinese and unknown English operands in explicit medication pair questions. The API returns `ambiguous` / `insufficient_information` with no risk claim, including when a known risk pair also appears.
- Other validation: 237 non-integration tests passed; the changed input-boundary document's corpus checksum was updated.
- Limits: only recognizable pair syntax is covered. This does not establish general drug-name recognition or clinical accuracy.
