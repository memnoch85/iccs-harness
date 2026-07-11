#!/usr/bin/env python3

import argparse
import csv
import json
import statistics
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SHERPA_DIR = REPO_ROOT / "sherpa"
BENCH_DIR = REPO_ROOT / "test" / "benchmark"

sys.path.insert(0, str(SHERPA_DIR))
sys.path.insert(0, str(BENCH_DIR))

from config import LLM_MODEL  # noqa: E402
from bench_memory_hybrid import (  # noqa: E402
    STRATEGIES,
    QUERY_CASES,
    build_facts,
    build_store,
    build_context_items,
    format_memory_context,
    expected_rank,
    llm_call,
    llm_pass,
)


FIELDNAMES = [
    "repeat",
    "memory_count",
    "strategy",
    "case",
    "category",
    "query",
    "expected_labels",
    "expected_terms",
    "match_query",
    "context_hit",
    "rank",
    "quote_count",
    "context_chars",
    "retrieval_ms",
    "store_build_ms",
    "context_labels",
    "context_sources",
    "context_texts",
    "llm_enabled",
    "llm_pass",
    "llm_response",
    "llm_wall_ms",
    "llm_total_ms",
    "llm_load_ms",
    "llm_prompt_eval_ms",
    "llm_eval_ms",
    "llm_prompt_tokens",
    "llm_response_tokens",
]


def warm_ollama(model, timeout):
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are warming up for a benchmark.",
            },
            {
                "role": "user",
                "content": "Reply with ready.",
            },
        ],
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_predict": 8,
        },
    }

    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started = time.perf_counter()

    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))

    elapsed = time.perf_counter() - started
    content = body.get("message", {}).get("content", "").strip()

    print(f"[LLM WARMUP] elapsed={elapsed:.3f}s response={content!r}", flush=True)


def evaluate_prebuilt(
    repeat,
    memory_count,
    store_build_ms,
    strategy_name,
    strategy,
    query_case,
    facts,
    store,
    id_to_fact,
    context_max_chars,
    run_llm,
    llm_args,
):
    items, match_query, retrieval_ms = build_context_items(
        strategy_name=strategy_name,
        strategy=strategy,
        facts=facts,
        store=store,
        id_to_fact=id_to_fact,
        query=query_case.query,
    )

    rank = expected_rank(items, query_case.expected_labels)
    hit = rank is not None

    context = format_memory_context(
        items,
        max_chars=context_max_chars,
    )

    row = {
        "repeat": repeat,
        "memory_count": memory_count,
        "strategy": strategy_name,
        "case": query_case.name,
        "category": query_case.category,
        "query": query_case.query,
        "expected_labels": "|".join(query_case.expected_labels),
        "expected_terms": "|".join(query_case.expected_terms),
        "match_query": match_query,
        "context_hit": int(hit),
        "rank": rank if rank is not None else "",
        "quote_count": len(items),
        "context_chars": len(context),
        "retrieval_ms": retrieval_ms,
        "store_build_ms": store_build_ms,
        "context_labels": "|".join(item["label"] for item in items),
        "context_sources": "|".join(item["source"] for item in items),
        "context_texts": " || ".join(item["text"] for item in items),
        "llm_enabled": int(run_llm),
        "llm_pass": "",
        "llm_response": "",
        "llm_wall_ms": "",
        "llm_total_ms": "",
        "llm_prompt_eval_ms": "",
        "llm_prompt_tokens": "",
        "llm_response_tokens": "",
    }

    if run_llm:
        llm_result = llm_call(
            model=llm_args["model"],
            query=query_case.query,
            context=context,
            temperature=llm_args["temperature"],
            num_predict=llm_args["num_predict"],
            timeout=llm_args["timeout"],
        )

        row.update(llm_result)
        row["llm_pass"] = int(
            llm_pass(
                llm_result["llm_response"],
                query_case.expected_terms,
            )
        )

    return row


def summarize(rows):
    grouped = defaultdict(list)
    grouped_by_memory = defaultdict(list)

    for row in rows:
        grouped[row["strategy"]].append(row)
        grouped_by_memory[(row["strategy"], row["memory_count"])].append(row)

    def summarize_items(items):
        total = len(items)
        retrievals = [float(item["retrieval_ms"]) for item in items]
        context_chars = [int(item["context_chars"]) for item in items]
        quote_counts = [int(item["quote_count"]) for item in items]
        build_times = [float(item["store_build_ms"]) for item in items]

        ranks = [
            int(item["rank"])
            for item in items
            if str(item["rank"]).strip()
        ]

        output = {
            "total": total,
            "context_hit_rate": sum(int(item["context_hit"]) for item in items) / total,
            "avg_rank": statistics.mean(ranks) if ranks else None,
            "retrieval_p50_ms": statistics.median(retrievals),
            "retrieval_p95_ms": sorted(retrievals)[max(0, int(total * 0.95) - 1)],
            "retrieval_max_ms": max(retrievals),
            "store_build_p50_ms": statistics.median(build_times),
            "store_build_max_ms": max(build_times),
            "avg_context_chars": statistics.mean(context_chars),
            "avg_quote_count": statistics.mean(quote_counts),
        }

        llm_rows = [
            item for item in items
            if str(item["llm_enabled"]) == "1"
        ]

        if llm_rows:
            prompt_eval = [
                float(item["llm_prompt_eval_ms"])
                for item in llm_rows
                if str(item["llm_prompt_eval_ms"]).strip()
            ]

            output["llm_pass_rate"] = (
                sum(int(item["llm_pass"]) for item in llm_rows) / len(llm_rows)
            )
            output["llm_prompt_eval_p50_ms"] = (
                statistics.median(prompt_eval) if prompt_eval else None
            )
            output["llm_prompt_eval_max_ms"] = (
                max(prompt_eval) if prompt_eval else None
            )

        return output

    by_strategy = []
    for strategy, items in sorted(grouped.items()):
        item = summarize_items(items)
        item["strategy"] = strategy
        by_strategy.append(item)

    by_memory = []
    for (strategy, memory_count), items in sorted(grouped_by_memory.items()):
        item = summarize_items(items)
        item["strategy"] = strategy
        item["memory_count"] = memory_count
        by_memory.append(item)

    by_strategy = sorted(
        by_strategy,
        key=lambda x: (
            -x["context_hit_rate"],
            x["avg_context_chars"],
            x["retrieval_p50_ms"],
        ),
    )

    by_memory = sorted(
        by_memory,
        key=lambda x: (
            x["strategy"],
            x["memory_count"],
        ),
    )

    failures = [
        row for row in rows
        if int(row["context_hit"]) == 0
    ]

    return {
        "by_strategy": by_strategy,
        "by_strategy_memory": by_memory,
        "failures": failures[:300],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--memory-counts", default="16,24,48,96,192,384,768,1536")
    parser.add_argument("--strategies", default=",".join(STRATEGIES.keys()))
    parser.add_argument("--context-chars", type=int, default=650)
    parser.add_argument("--repeat", type=int, default=20)

    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--llm-max-rows", type=int, default=120)
    parser.add_argument("--llm-model", default=LLM_MODEL)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--num-predict", type=int, default=40)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--skip-llm-warmup", action="store_true")

    parser.add_argument("--progress-every", type=int, default=250)
    parser.add_argument("--flush-every", type=int, default=100)

    args = parser.parse_args()

    memory_counts = [int(x) for x in args.memory_counts.split(",") if x.strip()]
    strategy_names = [x.strip() for x in args.strategies.split(",") if x.strip()]

    unknown = [name for name in strategy_names if name not in STRATEGIES]
    if unknown:
        raise SystemExit(f"Unknown strategies: {unknown}")

    if args.llm and not args.skip_llm_warmup:
        warm_ollama(args.llm_model, args.timeout)

    out_dir = REPO_ROOT / "test" / "benchmark" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = out_dir / f"memory_hybrid_v2_bench_{timestamp}.csv"
    summary_path = out_dir / f"memory_hybrid_v2_bench_{timestamp}.summary.json"

    total_rows = (
        args.repeat
        * len(memory_counts)
        * len(strategy_names)
        * len(QUERY_CASES)
    )

    print()
    print("HYBRID MEMORY V2 BENCH START")
    print(f"rows={total_rows}")
    print(f"csv={csv_path}")
    print(f"summary={summary_path}")
    print()

    rows = []
    llm_rows_used = 0
    completed = 0
    started_all = time.perf_counter()

    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        fh.flush()

        for repeat in range(args.repeat):
            for memory_count in memory_counts:
                build_started = time.perf_counter()

                facts = build_facts(memory_count)
                store, label_to_id, id_to_fact = build_store(
                    facts=facts,
                    max_memories=memory_count,
                )

                store_build_ms = (time.perf_counter() - build_started) * 1000.0

                print(
                    f"[STORE BUILT] repeat={repeat} memory_count={memory_count} "
                    f"facts={len(facts)} build_ms={store_build_ms:.2f}",
                    flush=True,
                )

                for strategy_name in strategy_names:
                    strategy = STRATEGIES[strategy_name]

                    for query_case in QUERY_CASES:
                        run_llm = False

                        if args.llm and llm_rows_used < args.llm_max_rows:
                            run_llm = True
                            llm_rows_used += 1

                        row = evaluate_prebuilt(
                            repeat=repeat,
                            memory_count=memory_count,
                            store_build_ms=store_build_ms,
                            strategy_name=strategy_name,
                            strategy=strategy,
                            query_case=query_case,
                            facts=facts,
                            store=store,
                            id_to_fact=id_to_fact,
                            context_max_chars=args.context_chars,
                            run_llm=run_llm,
                            llm_args={
                                "model": args.llm_model,
                                "temperature": args.temperature,
                                "num_predict": args.num_predict,
                                "timeout": args.timeout,
                            },
                        )

                        writer.writerow(row)
                        rows.append(row)
                        completed += 1

                        if completed % args.flush_every == 0:
                            fh.flush()

                        if completed % args.progress_every == 0:
                            elapsed = time.perf_counter() - started_all
                            rate = completed / max(elapsed, 0.001)
                            remaining = total_rows - completed
                            eta = remaining / max(rate, 0.001)

                            print(
                                f"[PROGRESS] {completed}/{total_rows} "
                                f"elapsed={elapsed:.1f}s rate={rate:.1f}/s eta={eta:.1f}s",
                                flush=True,
                            )

        fh.flush()

    summary = summarize(rows)

    with summary_path.open("w") as fh:
        json.dump(summary, fh, indent=2)

    elapsed = time.perf_counter() - started_all

    print()
    print("HYBRID MEMORY V2 BENCH DONE")
    print(f"elapsed={elapsed:.2f}s")
    print(f"CSV: {csv_path}")
    print(f"SUMMARY: {summary_path}")
    print()
    print("Top strategy summary:")
    for item in summary["by_strategy"][:25]:
        print(
            f"{item['strategy']:>30} "
            f"hit={item['context_hit_rate']:.3f} "
            f"rank={item['avg_rank']} "
            f"ctx={item['avg_context_chars']:.1f} "
            f"quotes={item['avg_quote_count']:.1f} "
            f"p50={item['retrieval_p50_ms']:.4f}ms "
            f"p95={item['retrieval_p95_ms']:.4f}ms"
            + (
                f" llm_pass={item.get('llm_pass_rate'):.3f} "
                f"prompt_p50={item.get('llm_prompt_eval_p50_ms'):.1f}ms"
                if "llm_pass_rate" in item
                else ""
            )
        )

    print()
    print("First failures:")
    for row in summary["failures"][:30]:
        print()
        print(f"{row['strategy']} | mem={row['memory_count']} | {row['case']}")
        print(f"query: {row['query']}")
        print(f"expected: {row['expected_labels']}")
        print(f"context labels: {row['context_labels']}")
        print(f"context texts: {row['context_texts']}")


if __name__ == "__main__":
    main()
