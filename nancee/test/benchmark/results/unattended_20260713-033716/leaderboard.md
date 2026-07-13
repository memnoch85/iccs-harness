# NANCEE Unattended Tunable Benchmark

Generated: 2026-07-13T05:24:57

Ranking is ordered by hard failures, hallucination flags, wrong-perspective output, quality score, length cutoffs, then p95 latency.

| Rank | Profile | Description | Turns | Score | Hard fails | Hallucination flags | Length cutoffs | Incomplete | Recall zero hits | Perspective repairs | Wrong perspective output | First-token avg | First-token p95 | LLM avg |
|---:|:---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | C | Balanced | 176 | 8.558 | 52 | 0 | 23 | 23 | 5 | 27 | 0 | 4.412 | 7.084 | 8.790 |
| 2 | B | Conservative and complete | 176 | 8.531 | 52 | 1 | 22 | 22 | 5 | 28 | 0 | 4.426 | 7.140 | 8.819 |
| 3 | D | Natural but completion-biased | 192 | 8.572 | 56 | 0 | 23 | 24 | 6 | 29 | 0 | 4.413 | 7.176 | 8.934 |
| 4 | A | Current baseline | 191 | 8.454 | 60 | 0 | 31 | 33 | 5 | 30 | 0 | 4.378 | 7.098 | 8.593 |

## Automatic winner: C

Do not accept a winner with hard failures. Review responses.md before adopting the tunables.

## Profile values

### Profile C — Balanced

- normal: temperature=0.25, num_predict=44
- detailed: temperature=0.25, num_predict=72
- recall: temperature=0.12, num_predict=18
- acknowledge: temperature=0.25, num_predict=18

### Profile B — Conservative and complete

- normal: temperature=0.20, num_predict=48
- detailed: temperature=0.20, num_predict=80
- recall: temperature=0.10, num_predict=18
- acknowledge: temperature=0.25, num_predict=18

### Profile D — Natural but completion-biased

- normal: temperature=0.28, num_predict=48
- detailed: temperature=0.25, num_predict=84
- recall: temperature=0.12, num_predict=20
- acknowledge: temperature=0.25, num_predict=18

### Profile A — Current baseline

- normal: temperature=0.30, num_predict=36
- detailed: temperature=0.30, num_predict=65
- recall: temperature=0.15, num_predict=18
- acknowledge: temperature=0.25, num_predict=18

## Flag counts

- perspective_required_repair: 114
- incomplete_response: 102
- token_limit_cutoff: 99
- policy_expected_acknowledge_got_normal: 56
- required_memory_not_stored: 56
- newest_correction_not_used: 34
- slow_first_token: 33
- weird_exact_fact_not_recalled: 31
- unnecessary_followup_question: 23
- memory_recall_zero_hits: 21
- response_too_long: 21
- correction_not_confirmed: 15
- policy_expected_normal_got_clarify: 12
- policy_expected_normal_got_detailed: 12
- policy_expected_detailed_got_normal: 10
- capital_answer_wrong: 8
- sauron_relationship_missing_or_vague: 4
- invented_shared_experience: 1
