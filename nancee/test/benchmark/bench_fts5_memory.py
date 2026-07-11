#!/usr/bin/env python3

import argparse
import csv
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SHERPA_DIR = REPO_ROOT / "sherpa"

sys.path.insert(0, str(SHERPA_DIR))

from session_archive import SessionArchive  # noqa: E402


@dataclass(frozen=True)
class MemoryFact:
    label: str
    text: str


@dataclass(frozen=True)
class QueryCase:
    name: str
    query: str
    expected_labels: tuple[str, ...]
    category: str
    note: str = ""


BASE_FACTS = [
    MemoryFact("name", "My name is Anders."),
    MemoryFact("vehicle", "I drive a black Jeep."),
    MemoryFact("hot_sauce_get", "I got hot sauce at Ocean Market."),
    MemoryFact("hot_sauce_buy", "I bought hot sauce at Ocean Market."),
    MemoryFact("japanese_candy", "I bought Japanese candy at Ocean Market."),
    MemoryFact("obd_cable", "I keep the spare OBD cable in the glove box."),
    MemoryFact("favorite_band", "My favorite band is Finch."),
    MemoryFact("editor", "I use Zed for remote SSH editing."),
    MemoryFact("garage_code", "My garage code is 8291."),
    MemoryFact("lunch_place", "I ate lunch at Red Iguana."),
    MemoryFact("coffee_order", "My coffee order is a black cold brew."),
    MemoryFact("parking", "I parked on level three near the west elevator."),
]


QUERY_CASES = [
    QueryCase(
        "name_exact",
        "What is my name?",
        ("name",),
        "identity",
    ),
    QueryCase(
        "name_who",
        "Who am I?",
        ("name",),
        "identity_boundary",
        "Expected weak case for FTS5-only because query shares no strong token with 'My name is Anders.'",
    ),
    QueryCase(
        "vehicle_drive",
        "What do I drive?",
        ("vehicle",),
        "vehicle",
    ),
    QueryCase(
        "vehicle_car",
        "What car do I drive?",
        ("vehicle",),
        "vehicle",
    ),
    QueryCase(
        "vehicle_have",
        "What vehicle do I have?",
        ("vehicle",),
        "vehicle_boundary",
        "Expected weak case unless query expansion/aliases are added later.",
    ),
    QueryCase(
        "hot_sauce_get_where",
        "Where did I get the hot sauce?",
        ("hot_sauce_get",),
        "location",
    ),
    QueryCase(
        "hot_sauce_buy_where",
        "Where did I buy hot sauce?",
        ("hot_sauce_buy",),
        "location",
    ),
    QueryCase(
        "ocean_market_buy",
        "What did I buy at Ocean Market?",
        ("hot_sauce_buy", "japanese_candy"),
        "multi_possible",
        "Multiple memories may be valid. Recall limit matters.",
    ),
    QueryCase(
        "obd_location",
        "Where is the OBD cable?",
        ("obd_cable",),
        "location",
    ),
    QueryCase(
        "favorite_band",
        "What is my favorite band?",
        ("favorite_band",),
        "preference",
    ),
    QueryCase(
        "editor",
        "What editor do I use?",
        ("editor",),
        "tooling",
    ),
    QueryCase(
        "garage_code",
        "What is my garage code?",
        ("garage_code",),
        "code",
    ),
    QueryCase(
        "lunch_place",
        "Where did I eat lunch?",
        ("lunch_place",),
        "location",
    ),
    QueryCase(
        "coffee_order",
        "What is my coffee order?",
        ("coffee_order",),
        "preference",
    ),
    QueryCase(
        "parking",
        "Where did I park?",
        ("parking",),
        "location",
    ),
]


LOW_SIGNAL_STORE_CASES = [
    "",
    ".",
    "Okay.",
    "Yeah.",
    "Cool.",
    "That is cool.",
    "In my name.",
    "What is my name?",
    "Where did I park?",
    "Can you remember this?",
]


def make_distractors(target_count: int) -> list[MemoryFact]:
    stores = [
        "AutoZone",
        "Smiths",
        "Walmart",
        "Costco",
        "H Mart",
        "Ocean Market",
        "Maverik",
        "Home Depot",
    ]
    items = [
        "engine oil",
        "ramen",
        "wiper blades",
        "spark plugs",
        "paper towels",
        "salsa",
        "rice",
        "USB cable",
        "socks",
        "soda",
        "brake cleaner",
        "trail mix",
    ]
    places = [
        "garage shelf",
        "glove box",
        "center console",
        "rear cargo bin",
        "kitchen drawer",
        "tool bag",
        "desk drawer",
        "back seat",
    ]

    distractors = []

    i = 0
    while len(distractors) < target_count:
        store = stores[i % len(stores)]
        item = items[i % len(items)]
        place = places[i % len(places)]

        distractors.append(
            MemoryFact(
                f"distractor_buy_{i}",
                f"I bought {item} at {store}.",
            )
        )

        if len(distractors) >= target_count:
            break

        distractors.append(
            MemoryFact(
                f"distractor_keep_{i}",
                f"I keep item {i} in the {place}.",
            )
        )

        if len(distractors) >= target_count:
            break

        distractors.append(
            MemoryFact(
                f"distractor_like_{i}",
                f"My favorite test snack {i} is flavor {i}.",
            )
        )

        i += 1

    return distractors


def get_hit_id(hit: dict):
    return hit.get("archive_id", hit.get("id"))


def get_hit_text(hit: dict) -> str:
    return str(
        hit.get(
            "user_text",
            hit.get(
                "user",
                hit.get("raw_text", ""),
            ),
        )
    )


def get_hit_score(hit: dict):
    return hit.get("score", hit.get("bm25_score"))


def build_archive(memory_count: int):
    archive = SessionArchive(max_turns=memory_count)

    facts = list(BASE_FACTS)

    if memory_count > len(facts):
        facts.extend(make_distractors(memory_count - len(facts)))

    facts = facts[:memory_count]

    label_to_id = {}

    for fact in facts:
        memory_id = archive.add_turn(
            user_text=fact.text,
            assistant_text="Okay.",
        )
        label_to_id[fact.label] = memory_id

    return archive, facts, label_to_id


def evaluate_one(
    memory_count: int,
    recall_limit: int,
    context_max_chars: int,
    query_case: QueryCase,
):
    archive, facts, label_to_id = build_archive(memory_count)

    expected_ids = {
        label_to_id[label]
        for label in query_case.expected_labels
        if label in label_to_id and label_to_id[label] is not None
    }

    started = time.perf_counter_ns()

    hits = archive.retrieve(
        query_case.query,
        limit=recall_limit,
        min_score=None,
        snippet_words=None,
    )

    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0

    hit_ids = [get_hit_id(hit) for hit in hits]
    hit_texts = [get_hit_text(hit) for hit in hits]
    hit_scores = [get_hit_score(hit) for hit in hits]

    rank = None
    for index, hit_id in enumerate(hit_ids, start=1):
        if hit_id in expected_ids:
            rank = index
            break

    pass_at_k = rank is not None
    pass_top1 = rank == 1

    context = archive.format_related_context(
        hits,
        max_characters=context_max_chars,
    )

    expected_texts = [
        fact.text
        for fact in facts
        if fact.label in query_case.expected_labels
    ]

    return {
        "memory_count": memory_count,
        "recall_limit": recall_limit,
        "context_max_chars": context_max_chars,
        "case": query_case.name,
        "category": query_case.category,
        "query": query_case.query,
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
        "context_chars": len(context),
        "note": query_case.note,
    }


def evaluate_store_filter():
    archive = SessionArchive(max_turns=64)
    rows = []

    for text in LOW_SIGNAL_STORE_CASES:
        before = archive.get_stats()
        before_count = before.get("turn_count", before.get("count", 0))

        memory_id = archive.add_turn(text, "Okay.")

        after = archive.get_stats()
        after_count = after.get("turn_count", after.get("count", 0))

        stored = after_count > before_count

        rows.append(
            {
                "input": text,
                "memory_id": memory_id,
                "stored": int(stored),
                "before_count": before_count,
                "after_count": after_count,
            }
        )

    return rows


def summarize(rows):
    by_config = {}
    by_category = {}
    latencies = []

    for row in rows:
        key = (
            row["memory_count"],
            row["recall_limit"],
            row["context_max_chars"],
        )
        by_config.setdefault(key, []).append(row)
        by_category.setdefault(row["category"], []).append(row)
        latencies.append(row["latency_ms"])

    config_summary = []
    for key, items in sorted(by_config.items()):
        top1 = sum(item["pass_top1"] for item in items)
        atk = sum(item["pass_at_k"] for item in items)
        total = len(items)

        config_summary.append(
            {
                "memory_count": key[0],
                "recall_limit": key[1],
                "context_max_chars": key[2],
                "total": total,
                "top1_pass_rate": top1 / total if total else 0,
                "at_k_pass_rate": atk / total if total else 0,
                "latency_p50_ms": statistics.median(
                    [item["latency_ms"] for item in items]
                ),
                "latency_max_ms": max(item["latency_ms"] for item in items),
                "avg_context_chars": statistics.mean(
                    [item["context_chars"] for item in items]
                ),
            }
        )

    category_summary = []
    for category, items in sorted(by_category.items()):
        total = len(items)
        category_summary.append(
            {
                "category": category,
                "total": total,
                "top1_pass_rate": sum(item["pass_top1"] for item in items) / total,
                "at_k_pass_rate": sum(item["pass_at_k"] for item in items) / total,
            }
        )

    failures = [
        row
        for row in rows
        if not row["pass_at_k"]
    ]

    weak_top1 = [
        row
        for row in rows
        if row["pass_at_k"] and not row["pass_top1"]
    ]

    return {
        "overall": {
            "rows": len(rows),
            "top1_pass_rate": sum(row["pass_top1"] for row in rows) / len(rows),
            "at_k_pass_rate": sum(row["pass_at_k"] for row in rows) / len(rows),
            "latency_p50_ms": statistics.median(latencies),
            "latency_p95_ms": sorted(latencies)[int(len(latencies) * 0.95) - 1],
            "latency_max_ms": max(latencies),
        },
        "by_config": config_summary,
        "by_category": category_summary,
        "failures": failures[:50],
        "weak_top1": weak_top1[:50],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--memory-counts",
        default="12,24,48,96,192",
        help="Comma-separated memory counts.",
    )
    parser.add_argument(
        "--limits",
        default="1,2,3,5",
        help="Comma-separated recall limits.",
    )
    parser.add_argument(
        "--context-chars",
        default="350,650,1000",
        help="Comma-separated max context character sizes.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=5,
        help="Repeat each test N times.",
    )
    args = parser.parse_args()

    memory_counts = [int(x) for x in args.memory_counts.split(",") if x.strip()]
    limits = [int(x) for x in args.limits.split(",") if x.strip()]
    context_chars = [int(x) for x in args.context_chars.split(",") if x.strip()]

    rows = []

    for repeat_index in range(args.repeat):
        for memory_count in memory_counts:
            for recall_limit in limits:
                for context_max_chars in context_chars:
                    for query_case in QUERY_CASES:
                        row = evaluate_one(
                            memory_count=memory_count,
                            recall_limit=recall_limit,
                            context_max_chars=context_max_chars,
                            query_case=query_case,
                        )
                        row["repeat"] = repeat_index
                        rows.append(row)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = REPO_ROOT / "test" / "benchmark" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / f"fts5_memory_bench_{timestamp}.csv"
    json_path = out_dir / f"fts5_memory_bench_{timestamp}.summary.json"
    store_filter_path = out_dir / f"fts5_store_filter_{timestamp}.csv"

    fieldnames = list(rows[0].keys())

    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    summary = summarize(rows)

    with json_path.open("w") as fh:
        json.dump(summary, fh, indent=2)

    store_rows = evaluate_store_filter()
    with store_filter_path.open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=list(store_rows[0].keys()),
        )
        writer.writeheader()
        writer.writerows(store_rows)

    print()
    print("FTS5 MEMORY BENCH DONE")
    print(f"CSV: {csv_path}")
    print(f"SUMMARY: {json_path}")
    print(f"STORE FILTER CSV: {store_filter_path}")
    print()
    print(json.dumps(summary["overall"], indent=2))
    print()
    print("Worst failures, first 10:")
    for row in summary["failures"][:10]:
        print(
            f"- {row['case']} | mem={row['memory_count']} "
            f"limit={row['recall_limit']} ctx={row['context_max_chars']} "
            f"query={row['query']!r} hits={row['hit_texts']!r}"
        )
    print()
    print("Store filter results:")
    for row in store_rows:
        print(f"- stored={row['stored']} id={row['memory_id']} input={row['input']!r}")


if __name__ == "__main__":
    main()
