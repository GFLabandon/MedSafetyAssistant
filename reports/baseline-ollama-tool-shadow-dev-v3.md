# Real Ollama Typed-Tool Shadow Dev Baseline v3

- Date: 2026-08-02
- Code commit: `f95fa0dba22b47f21711808e199aec38a38d138c`
- Working tree before run: clean
- Dataset: `eval/tool_shadow_v1.jsonl`, dev split only
- Dataset SHA-256:
  `e037caf4a9aa3e2db33c2fb1fbc3cca6ca854a1e47bd16cc5a008cf25f8a3229`
- Prompt: `typed-tool-shadow-v3`
- Model: `qwen3:1.7b`
- Model digest:
  `8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7`
- Quantization: `Q4_K_M`
- Repetitions: 1

## Result

| Metric | Result |
|---|---:|
| Proposal rate | 1.000 |
| Tool-name accuracy | 1.000 |
| Argument exact match | 0.950 |
| Whole-call exact match | 0.950 |
| Illegal-tool rate | 0.000 |
| Invalid-argument rate | 0.000 |
| P50 latency | 685.394 ms |
| P95 latency | 860.257 ms |
| Executed tool calls | **0** |

Status counts: 38 `valid`, 2 `wrong_arguments`.

## Residual failures and stop decision

All 40 cases selected the expected registered tool. Two adversarial `start` questions lost only their
final Chinese full stop in the proposed `question` argument. Strict exact comparison rejected both;
neither proposal was dispatched.

The failure persisted after v3 explicitly required punctuation-preserving copying. Further prompt
tuning against the dev set is stopped. This result supports a stronger future design: if a model is
ever allowed to influence routing, the server should derive final arguments from trusted workflow
state after accepting a tool name, rather than trusting the model to copy question or artifact values.
Until that separate design is implemented and tested, wrong arguments must trigger deterministic
fallback.

The v3 prompt and adapter are now frozen for the first locked-test run. No code or prompt change may
be made in response to the locked result; a changed design requires a new prompt and dataset version.

## Boundary

This remains a development result, not an independent test result or permission to enable model
execution. No proposal was dispatched. The machine-readable summary and all per-case records are
preserved in [`baseline-ollama-tool-shadow-dev-v3.json`](baseline-ollama-tool-shadow-dev-v3.json) and
[`raw/ollama-tool-shadow-dev-v3-records.json`](raw/ollama-tool-shadow-dev-v3-records.json).
