# NANCEE runtime config benchmark summary

## Stage 1: temperature / num_predict / recent turns

- temp=0.4 num_predict=32 recent_turns=1 avg_score=90.714 length_rate=0.0 avg_wall_s=4.957 avg_prompt_eval_s=1.916 avg_generation_s=2.561
- temp=0.3 num_predict=20 recent_turns=1 avg_score=90.714 length_rate=0.0 avg_wall_s=4.995 avg_prompt_eval_s=1.925 avg_generation_s=2.587
- temp=0.2 num_predict=24 recent_turns=1 avg_score=90.714 length_rate=0.0 avg_wall_s=5.185 avg_prompt_eval_s=1.913 avg_generation_s=2.791
- temp=0.4 num_predict=24 recent_turns=1 avg_score=90.714 length_rate=0.0 avg_wall_s=5.527 avg_prompt_eval_s=1.926 avg_generation_s=3.118
- temp=0.2 num_predict=28 recent_turns=1 avg_score=89.286 length_rate=0.0 avg_wall_s=4.95 avg_prompt_eval_s=1.92 avg_generation_s=2.546
- temp=0.1 num_predict=28 recent_turns=1 avg_score=89.0 length_rate=0.0 avg_wall_s=5.287 avg_prompt_eval_s=1.92 avg_generation_s=2.885
- temp=0.2 num_predict=40 recent_turns=1 avg_score=89.0 length_rate=0.0 avg_wall_s=5.287 avg_prompt_eval_s=1.926 avg_generation_s=2.878
- temp=0.3 num_predict=32 recent_turns=1 avg_score=86.857 length_rate=0.0 avg_wall_s=5.415 avg_prompt_eval_s=1.922 avg_generation_s=3.012
- temp=0.0 num_predict=28 recent_turns=1 avg_score=85.714 length_rate=0.0 avg_wall_s=4.823 avg_prompt_eval_s=1.894 avg_generation_s=2.455
- temp=0.0 num_predict=32 recent_turns=1 avg_score=85.714 length_rate=0.0 avg_wall_s=4.827 avg_prompt_eval_s=1.897 avg_generation_s=2.454

## Stage 2: memory/profile shape

- recall_limit=1 recall_chars=650 profile_chars=0 avg_score=100.0 length_rate=0.0 avg_wall_s=5.195 avg_prompt_eval_s=2.567 avg_generation_s=2.144
- recall_limit=2 recall_chars=650 profile_chars=0 avg_score=100.0 length_rate=0.0 avg_wall_s=5.503 avg_prompt_eval_s=2.556 avg_generation_s=2.471
- recall_limit=3 recall_chars=650 profile_chars=650 avg_score=100.0 length_rate=0.0 avg_wall_s=5.744 avg_prompt_eval_s=2.612 avg_generation_s=2.651
- recall_limit=2 recall_chars=650 profile_chars=650 avg_score=91.25 length_rate=0.0 avg_wall_s=5.675 avg_prompt_eval_s=2.609 avg_generation_s=2.584
- recall_limit=3 recall_chars=650 profile_chars=1000 avg_score=90.0 length_rate=0.0 avg_wall_s=5.161 avg_prompt_eval_s=2.618 avg_generation_s=2.063
- recall_limit=2 recall_chars=650 profile_chars=1000 avg_score=90.0 length_rate=0.0 avg_wall_s=5.201 avg_prompt_eval_s=2.604 avg_generation_s=2.115
- recall_limit=1 recall_chars=500 profile_chars=650 avg_score=90.0 length_rate=0.0 avg_wall_s=5.214 avg_prompt_eval_s=2.612 avg_generation_s=2.12
- recall_limit=1 recall_chars=650 profile_chars=1000 avg_score=90.0 length_rate=0.0 avg_wall_s=5.217 avg_prompt_eval_s=2.616 avg_generation_s=2.12
- recall_limit=1 recall_chars=500 profile_chars=1000 avg_score=90.0 length_rate=0.0 avg_wall_s=5.219 avg_prompt_eval_s=2.616 avg_generation_s=2.121
- recall_limit=2 recall_chars=500 profile_chars=650 avg_score=90.0 length_rate=0.0 avg_wall_s=5.252 avg_prompt_eval_s=2.599 avg_generation_s=2.173

## Case-level weak spots

- fts_buy_recall: avg_score=90.788 min_score=0.0 length_rate=0.008 avg_wall_s=8.9
- normal_park_statement: avg_score=86.964 min_score=32.0 length_rate=0.286 avg_wall_s=4.683
- unknown_favorite_color: avg_score=83.803 min_score=0.0 length_rate=0.227 avg_wall_s=4.605
- fts_park_recall: avg_score=83.023 min_score=15.0 length_rate=0.098 avg_wall_s=4.668
- junk_statement_in_my_name: avg_score=59.155 min_score=0.0 length_rate=0.369 avg_wall_s=5.13
- normal_buy_statement: avg_score=52.024 min_score=0.0 length_rate=0.155 avg_wall_s=4.995
- unknown_passport: avg_score=37.788 min_score=0.0 length_rate=0.348 avg_wall_s=5.175
