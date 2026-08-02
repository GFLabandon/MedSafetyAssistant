# Real Ollama Typed-Tool Shadow Dev Baseline v1

- Date: 2026-08-02
- Code commit: `415f7b4a555e6189a8421281c21f779921b59018`
- Working tree before run: clean
- Dataset: `eval/tool_shadow_v1.jsonl`, dev split only
- Dataset SHA-256:
  `e037caf4a9aa3e2db33c2fb1fbc3cca6ca854a1e47bd16cc5a008cf25f8a3229`
- Prompt: `typed-tool-shadow-v1`
- Model: `qwen3:1.7b`
- Model digest:
  `8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7`
- Quantization: `Q4_K_M`
- Repetitions: 1

## Result

| Metric | Result |
|---|---:|
| Proposal rate | 1.000 |
| Tool-name accuracy | 0.275 |
| Argument exact match | 0.275 |
| Whole-call exact match | 0.275 |
| Illegal-tool rate | 0.000 |
| Invalid-argument rate | 0.025 |
| P50 latency | 696.470 ms |
| P95 latency | 903.095 ms |
| Executed tool calls | **0** |

Status counts: 11 `valid`, 28 `wrong_tool`, 1 `invalid_arguments`.

## Failure analysis

The dominant failure was stage selection, not hallucinated tool names:

| Expected tool | Valid / total |
|---|---:|
| `resolve_medications` | 1 / 14 |
| `query_safety_graph` | 0 / 5 |
| `request_clarification` | 8 / 8 |
| `render_evidence_explanation` | 2 / 13 |

The model proposed `request_clarification` in 32 of 40 cases and never proposed
`query_safety_graph`. One adversarial start case added an undeclared
`packet_call_id`, which strict argument validation rejected. No unknown tool was proposed and no
proposal was dispatched.

This pattern indicates that the small model did not reliably apply the prose stage mapping. The next
dev iteration should make the stage-to-tool mapping explicit and tell the model that emitting a tool
call is a shadow proposal, not a real execution. The locked test remains untouched.

## Boundary

This is a development result used to revise the prompt. It is not an independent test result, medical
accuracy result, or evidence that a model can control tools safely. The complete machine-readable
summary and all per-case records are preserved in
[`baseline-ollama-tool-shadow-dev-v1.json`](baseline-ollama-tool-shadow-dev-v1.json) and
[`raw/ollama-tool-shadow-dev-v1-records.json`](raw/ollama-tool-shadow-dev-v1-records.json).
