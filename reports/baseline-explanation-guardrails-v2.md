# Evidence Explanation Guardrail Baseline

Dataset: `eval/explanation_guardrails_v2.jsonl`
Data version: `v1.0.0-alpha.2`
Dataset SHA-256: `9761922cbda49d0eb1ca7ed1c2e825aa6bd43092863d500372d17d15f5ac08bd`
Guardrail version: `explanation-guardrails-v2`
Planner: `scripted_adversarial_fixtures`
Code commit: `1844277fcfff3d6185ee43b17c1ad4bee3085fcd`
Working tree dirty at run: `false`
Cases: 10

## Metrics

| Metric | Result |
|---|---:|
| Case pass rate | 1.000 |
| Mode accuracy | 1.000 |
| Fallback reason accuracy | 1.000 |
| Conclusion preservation | 1.000 |
| Fact reference coverage | 1.000 |
| Extractive claim rate | 1.000 |
| Source traceability rate | 1.000 |
| Unsupported claim rate | 0.000 |

## Failures

No failures in this scripted adversarial set.

## Interpretation Boundary

Scripted planner guardrail regression; not a real-model or clinical-quality result. V2 adds a severity-order violation case and preserves V1 as the historical pre-rule baseline.
