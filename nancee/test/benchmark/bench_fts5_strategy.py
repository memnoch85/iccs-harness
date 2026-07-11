#!/usr/bin/env python3

import argparse
import csv
import json
import re
import sqlite3
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SHERPA_DIR = REPO_ROOT / "sherpa"
BENCH_DIR = REPO_ROOT / "test" / "benchmark"

sys.path.insert(0, str(SHERPA_DIR))
sys.path.insert(0, str(BENCH_DIR))

from session_memory_store import SessionMemoryStore, normalize_for_search, make_fts_query  # noqa: E402
from bench_fts5_memory import BASE_FACTS, QUERY_CASES, make_distractors  # noqa: E402


STRATEGIES = [
    "current",
    "current_newest",
    "strict_and",
    "expanded_or",
    "expanded_newest",
]


QUERY_EXPANSIONS = {
    # identity
    "who": ["name"],
    "called": ["name", "call"],
    "call": ["name", "called"],

    # vehicle
    "drive": ["drive", "car", "vehicle"],
    "driving": ["drive", "car", "vehicle"],
    "car": ["car", "vehicle", "drive"],
    "vehicle": ["vehicle", "car", "drive"],
    "jeep": ["jeep", "vehicle", "car"],
    "own": ["own", "drive", "vehicle", "car"],
    "have": ["have", "own", "drive", "vehicle", "car"],

    # buy/get
    "buy": ["buy", "bought", "get", "got"],
    "bought": ["bought", "buy", "get", "got"],
    "get": ["get", "got", "buy", "bought"],
    "got": ["got", "get", "buy", "bought"],

    # places/actions
    "park": ["park", "parked", "parking"],
    "parked": ["parked", "park", "parking"],
    "eat": ["eat", "ate", "lunch"],
    "ate": ["ate", "eat", "lunch"],

    # preference-ish
    "favorite": ["favorite", "prefer", "preference"],
    "prefer": ["prefer", "favorite", "preference"],
}


def raw_tokens(text):
    return [
        token.lower()
        for token in re.findall(r"[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*", str(text))
    ]


def unique_preserve_order(items):
    seen = set()
    out = []

    for item in items:
        item = str(item).strip().lower()

        if not item:
            continue

        if item in seen:
            continue

        seen.add(item)
        out.append(item)

    return out


def normalized_tokens(text):
    return unique_preserve_order(normalize_for_search(text).split())


def expanded_tokens(text):
    tokens = normalized_tokens(text)
    raw = raw_tokens(text)

    expanded = list(tokens)

    for token in raw:
        expanded.extend(QUERY_EXPANSIONS.get(token, []))

    return unique_preserve_order(expanded)


def fts_or(tokens):
    tokens = unique_preserve_order(tokens)
    return " OR ".join(tokens)


def fts_and(tokens):
    tokens = unique_preserve_order(tokens)
    return " ".join(tokens)


def make_strategy_query(query, strategy):
    if strategy in {"current", "current_newest"}:
        return make_fts_query(query)

    if strategy == "strict_and":
        return fts_and(normalized_tokens(query))

    if strategy in {"expanded_or", "expanded_newest"}:
        return fts_or(expanded_tokens(query))

    raise ValueError(f"unknown strategy: {strategy}")


def build_store(memory_count):
    store = SessionMemoryStore(max_memories=memory_count)

    facts = list(BASE_FACTS)

    if memory_count > len(facts):
        facts.extend(make_distractors(memory_count - len(facts)))

    facts = facts[:memory_count]

    label_to_id = {}

    for fact in facts:
        memory_id = store.add_memory(fact.text)
        label_to_id[fact.label] = memory_id

    return store, facts, label_to_id


def search_strategy(store, query, strategy, limit):
    match_query = make_strategy_query(query, strategy)

    if not match_query:
        return [], match_query, ""

    if strategy.endswith("_newest"):
        order_by = "bm25_score ASC, created_ts DESC, rowid DESC"
    else:
        order_by = "bm25_score ASC"

    sql = f"""
        SELECT rowid, raw_text, search_text, created_ts,
               bm25(memory_fts) AS bm25_score
        FROM memory_fts
        WHERE memory_fts MATCH ?
        ORDER BY {order_by}
        LIMIT ?
    """

    try:
        rows = store.conn.execute(
            sql,
            (match_query, int(limit)),
        ).fetchall()
    except sqlite3.OperationalError as error:
        return [], match_query, f"sqlite_error={error}"

    hits = [
        {
            "id": int(row["rowid"]),
            "raw_text": row["raw_text"],
            "search_text": row["search_text"],
            "created_ts": float(row["created_ts"]),
            "bm25_score": float(row["bm25_score"]),
        }
        for row in rows
    ]

    return hits, match_query, ""


def evaluate_one(memory_count, limit, strategy, query_case):
    store, facts, label_to_id = build_store(memory_count)

    expected_ids = {
        label_to_id[label]
        for label in query_case.expected_labels
        if label in label_to_id and label_to_id[label] is not None
    }

    started = time.perf_counter_ns()
    hits, match_query, error = search_strategy(
        store=store,
        query=query_case.query,
        strategy=strategy,
        limit=limit,
    )
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0

    hit_ids = [hit["id"] for hit in hits]
    hit_texts = [hit["raw_text"] for hit in hits]
    hit_scores = [hit["bm25_score"] for hit in hits]

    rank = None
    for index, hit_id in enumerate(hit_ids, start=1):
        if hit_id in expected_ids:
            rank = index
            break

    pass_at_k = rank is not None
    pass_top1 = rank == 1

    expected_texts = [
        fact.text
        for fact in facts
        if fact.label in query_case.expected_labels
    ]

    return {
        "memory_count": memory_count,
        "limit": limit,
        "strategy": strategy,
        "case": query_case.name,
        "category": query_case.category,
        "query": query_case.query,
        "match_query": match_query,
        "expected_labels": "|".join(query_case.expected_labels),
        "expected_ids": "|".join(str(x) for x in sorted(expected_ids)),
        "expected_texts": " || ".join(expected_texts),
        "hit_ids": "|".join(str(x) for x in hit_ids),
        "hit_scores": "|".join(str(x) for x in hit_scores),
        "hit_texts": " || ".join(hit_texts),
        "rank": rank if rank is not None else "",
        "pass_top1": int(pass_top1),
        "pass_at_k": int(pass_at_k),
        "latency_ms": elapsed_ms,
        "error": error,
        "note": query_case.note,
    }


def summarize(rows):
    by_strategy = defaultdict(list)
    by_config = defaultdict(list)
    by_case = defaultdict(list)

    for row in rows:
        by_strategy[row["strategy"]].append(row)
        by_config[(row["strategy"], row["memory_count"], row["limit"])].append(row)
        by_case[(row["strategy"], row["case"])].append(row)

    def rates(items):
        total = len(items)
        latencies = [float(item["latency_ms"]) for item in items]

        return {
            "total": total,
            "top1": sum(int(item["pass_top1"]) for item in items) / total,
            "at_k": sum(int(item["pass_at_k"]) for item in items) / total,
            "p50_ms": statistics.median(latencies),
            "p95_ms": sorted(latencies)[max(0, int(total * 0.95) - 1)],
            "max_ms": max(latencies),
        }

    strategy_summary = {
        strategy: rates(items)
        for strategy, items in sorted(by_strategy.items())
    }

    config_summary = []
    for (strategy, memory_count, limit), items in sorted(by_config.items()):
        item = rates(items)
        item.update(
            {
                "strategy": strategy,
                "memory_count": memory_count,
                "limit": limit,
            }
        )
        config_summary.append(item)

    case_summary = []
    for (strategy, case), items in sorted(by_case.items()):
        item = rates(items)
        item.update(
            {
                "strategy": strategy,
                "case": case,
            }
        )
        case_summary.append(item)

    failures = [
        row
        for row in rows
        if int(row["pass_at_k"]) == 0
    ]

    weak_top1 = [
        row
        for row in rows
        if int(row["pass_at_k"]) == 1 and int(row["pass_top1"]) == 0
    ]

    return {
        "strategy_summary": strategy_summary,
        "config_summary": sorted(
            config_summary,
            key=lambda x: (-x["top1"], -x["at_k"], x["p50_ms"], x["limit"]),
        ),
        "case_summary": case_summary,
        "failures": failures[:100],
        "weak_top1": weak_top1[:100],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--memory-counts", default="12,24,48,96,192,384")
    parser.add_argument("--limits", default="1,2,3,5")
    parser.add_argument("--repeat", type=int, default=10)
    args = parser.parse_args()

    memory_counts = [int(x) for x in args.memory_counts.split(",") if x.strip()]
    limits = [int(x) for x in args.limits.split(",") if x.strip()]

    rows = []

    for repeat in range(args.repeat):
        for memory_count in memory_counts:
            for limit in limits:
                for strategy in STRATEGIES:
                    for query_case in QUERY_CASES:
                        row = evaluate_one(
                            memory_count=memory_count,
                            limit=limit,
                            strategy=strategy,
                            query_case=query_case,
                        )
                        row["repeat"] = repeat
                        rows.append(row)

    out_dir = REPO_ROOT / "test" / "benchmark" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = out_dir / f"fts5_strategy_bench_{timestamp}.csv"
    summary_path = out_dir / f"fts5_strategy_bench_{timestamp}.summary.json"

    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    summary = summarize(rows)

    with summary_path.open("w") as fh:
        json.dump(summary, fh, indent=2)

    print()
    print("FTS5 STRATEGY BENCH DONE")
    print(f"CSV: {csv_path}")
    print(f"SUMMARY: {summary_path}")
    print()
    print("Strategy summary:")
    print(json.dumps(summary["strategy_summary"], indent=2))
    print()
    print("Best configs:")
    for item in summary["config_summary"][:20]:
        print(
            f"{item['strategy']:>16} "
            f"mem={item['memory_count']:>4} "
            f"limit={item['limit']} "
            f"top1={item['top1']:.3f} "
            f"atk={item['at_k']:.3f} "
            f"p50={item['p50_ms']:.4f}ms "
            f"p95={item['p95_ms']:.4f}ms"
        )

    print()
    print("First failures:")
    for row in summary["failures"][:20]:
        print()
        print(f"{row['strategy']} | {row['case']} | mem={row['memory_count']} limit={row['limit']}")
        print(f"query: {row['query']}")
        print(f"match: {row['match_query']}")
        print(f"expected: {row['expected_texts']}")
        print(f"hits: {row['hit_texts']}")


if __name__ == "__main__":
    main()
