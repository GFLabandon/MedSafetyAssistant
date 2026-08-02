# Real Ollama Typed-Tool Shadow Dev Baseline v2

- Date: 2026-08-02
- Code commit: `96f952497d275e4601547ddd98d844daf29b3468`
- Working tree before run: clean
- Dataset: `eval/tool_shadow_v1.jsonl`, dev split only
- Dataset SHA-256:
  `e037caf4a9aa3e2db33c2fb1fbc3cca6ca854a1e47bd16cc5a008cf25f8a3229`
- Prompt: `typed-tool-shadow-v2`
- Model: `qwen3:1.7b`
- Model digest:
  `8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7`
- Quantization: `Q4_K_M`
- Repetitions: 1

## Result

| Metric | Result |
|---|---:|
| Proposal rate | 1.000 |
| Tool-name accuracy | 0.950 |
| Argument exact match | 0.900 |
| Whole-call exact match | 0.900 |
| Illegal-tool rate | 0.000 |
| Invalid-argument rate | 0.000 |
| P50 latency | 691.877 ms |
| P95 latency | 862.020 ms |
| Executed tool calls | **0** |

Status counts: 36 `valid`, 2 `wrong_tool`, 2 `wrong_arguments`.

## Failure analysis

The explicit, mutually exclusive stage mapping fixed the systemic v1 routing failure:

| Expected tool | Valid / total |
|---|---:|
| `resolve_medications` | 12 / 14 |
| `query_safety_graph` | 5 / 5 |
| `request_clarification` | 6 / 8 |
| `render_evidence_explanation` | 13 / 13 |

The two argument failures removed the final Chinese full stop from adversarial questions, even though
the expected contract requires exact copying after whitespace trim. The two routing failures occurred
only for `after_resolution` states with `resolution_status=unknown`; the model incorrectly selected
`render_evidence_explanation`. All resolved, ambiguous, and rejected dev states selected the expected
tool.

The next dev iteration should explicitly enumerate `ambiguous`, `unknown`, and `rejected` as
clarification states and require punctuation-preserving question copying. Tool schemas and validators
must not be relaxed. The locked test remains untouched.

## Boundary

This is a prompt-development result, not an independent test result or permission to enable model
execution. No proposal was dispatched. The machine-readable summary and all per-case records are
preserved in [`baseline-ollama-tool-shadow-dev-v2.json`](baseline-ollama-tool-shadow-dev-v2.json) and
[`raw/ollama-tool-shadow-dev-v2-records.json`](raw/ollama-tool-shadow-dev-v2-records.json).
