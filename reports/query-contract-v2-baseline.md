# Query API contract V2 baseline

- Scope: deterministic engineering regression of the public V1 query and session APIs.
- Result: 15/15 cases passed. The JSON report records the dataset checksum, catalog version, exact implementation commit, and per-case results.
- Added boundary cases: unknown Chinese dosage-form name before a known name, after a known name, and mixed into a known risk pair. Each returns `out_of_scope` with no risk claim.
- Limits: the pattern covers identifiable Chinese dosage-form names only. This is not independent medical or clinical accuracy evidence; unknown English or suffix-free names may still bypass the mixed-name check.
