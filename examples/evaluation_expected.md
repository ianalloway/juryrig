# Synthetic judge evaluation lab

Controlled MockJudge configurations; no real models or human labels.
These measurements describe the configured fixtures, not model quality.

Dataset SHA-256: `9a5af4707456b05e71b4e0a1ad2605523dca7735dd376e54a5c6df3aa285ff5c`
Package version: `0.3.0`; atlas requested: `False`.
Seed 0; five consistency runs; serial execution; ε=0.05; κ buckets rounded to one decimal.

Configuration overrides (all other MockJudge defaults unchanged):

- `baseline`: `{}`
- `slot_first`: `{"position_bias": 2.0}`
- `length_bonus`: `{"verbosity_bias": 0.8}`
- `injection`: `{"injection_bias": 0.6}`
- `unstable`: `{"instability": 0.9}`

## support

Mock rubric: `receipt window original escalation`

Four A/B cases for audits; 16 response variants for agreement.

| Judge | Flip rate | Padding lift | Injection lift | Worst spread | Flagged audits |
| --- | --- | --- | --- | --- | --- |
| baseline | 0% | 0.000 | 0.000 | 0.000 | none |
| slot_first | 100% | 0.000 | 0.000 | 0.000 | position |
| length_bonus | 0% | 0.217 | 0.030 | 0.000 | verbosity |
| injection | 0% | 0.000 | 0.600 | 0.000 | injection |
| unstable | 0% | 0.120 | 0.011 | 0.651 | verbosity, injection, consistency |

Pairwise agreement over all response variants:

| Pair | Within ε | κ | Mean absolute delta |
| --- | --- | --- | --- |
| baseline / slot_first | 100% | 1.000 | 0.000 |
| baseline / length_bonus | 100% | 1.000 | 0.020 |
| baseline / injection | 75% | 0.667 | 0.150 |
| baseline / unstable | 44% | 0.265 | 0.128 |
| slot_first / length_bonus | 100% | 1.000 | 0.020 |
| slot_first / injection | 75% | 0.667 | 0.150 |
| slot_first / unstable | 44% | 0.265 | 0.128 |
| length_bonus / injection | 75% | 0.667 | 0.152 |
| length_bonus / unstable | 44% | 0.265 | 0.131 |
| injection / unstable | 25% | 0.094 | 0.249 |

Baseline keyword-stuffing scores: `[1.0, 1.0, 1.0, 1.0]`.
A clean bias audit does not establish semantic correctness.

## incident

Mock rubric: `timeline impact mitigation evidence`

Four A/B cases for audits; 16 response variants for agreement.

| Judge | Flip rate | Padding lift | Injection lift | Worst spread | Flagged audits |
| --- | --- | --- | --- | --- | --- |
| baseline | 0% | 0.000 | 0.000 | 0.000 | none |
| slot_first | 100% | 0.000 | 0.000 | 0.000 | position |
| length_bonus | 0% | 0.216 | 0.030 | 0.000 | verbosity |
| injection | 0% | 0.000 | 0.600 | 0.000 | injection |
| unstable | 0% | 0.120 | 0.011 | 0.651 | verbosity, injection, consistency |

Pairwise agreement over all response variants:

| Pair | Within ε | κ | Mean absolute delta |
| --- | --- | --- | --- |
| baseline / slot_first | 100% | 1.000 | 0.000 |
| baseline / length_bonus | 100% | 1.000 | 0.021 |
| baseline / injection | 75% | 0.667 | 0.150 |
| baseline / unstable | 44% | 0.265 | 0.128 |
| slot_first / length_bonus | 100% | 1.000 | 0.021 |
| slot_first / injection | 75% | 0.667 | 0.150 |
| slot_first / unstable | 44% | 0.265 | 0.128 |
| length_bonus / injection | 75% | 0.667 | 0.152 |
| length_bonus / unstable | 44% | 0.265 | 0.132 |
| injection / unstable | 25% | 0.094 | 0.249 |

Baseline keyword-stuffing scores: `[1.0, 1.0, 1.0, 1.0]`.
A clean bias audit does not establish semantic correctness.

## research

Mock rubric: `source sample uncertainty limitations`

Four A/B cases for audits; 16 response variants for agreement.

| Judge | Flip rate | Padding lift | Injection lift | Worst spread | Flagged audits |
| --- | --- | --- | --- | --- | --- |
| baseline | 0% | 0.000 | 0.000 | 0.000 | none |
| slot_first | 100% | 0.000 | 0.000 | 0.000 | position |
| length_bonus | 0% | 0.214 | 0.030 | 0.000 | verbosity |
| injection | 0% | 0.000 | 0.600 | 0.000 | injection |
| unstable | 0% | 0.120 | 0.011 | 0.651 | verbosity, injection, consistency |

Pairwise agreement over all response variants:

| Pair | Within ε | κ | Mean absolute delta |
| --- | --- | --- | --- |
| baseline / slot_first | 100% | 1.000 | 0.000 |
| baseline / length_bonus | 100% | 1.000 | 0.024 |
| baseline / injection | 75% | 0.667 | 0.150 |
| baseline / unstable | 44% | 0.265 | 0.128 |
| slot_first / length_bonus | 100% | 1.000 | 0.024 |
| slot_first / injection | 75% | 0.667 | 0.150 |
| slot_first / unstable | 44% | 0.265 | 0.128 |
| length_bonus / injection | 75% | 0.667 | 0.153 |
| length_bonus / unstable | 44% | 0.265 | 0.132 |
| injection / unstable | 25% | 0.094 | 0.249 |

Baseline keyword-stuffing scores: `[1.0, 1.0, 1.0, 1.0]`.
A clean bias audit does not establish semantic correctness.

## Interpretation limits

Synthetic construction roles are not independent human labels. Keyword coverage ignores meaning, negation, and factual correctness.
The judges share one scoring implementation; agreement is not independent corroboration. Configured defects are demonstrations, not estimates of real-model failure rates.
Scores clip at 0 and 1, which can hide padding effects at the ceiling. Call-counter instability depends on execution order; keep this run serial.
No accuracy, calibration, or human-agreement claim is made.
