#!/usr/bin/env python3

import csv
import json
import sqlite3
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SHERPA_DIR = REPO_ROOT / "sherpa"

sys.path.insert(0, str(SHERPA_DIR))

from session_memory_store import SessionMemoryStore, make_fts_query, normalize_for_search  # noqa: E402


@dataclass(frozen=True)
class Fact:
    label: str
    text: str


@dataclass(frozen=True)
class QueryCase:
    name: str
    query: str
    expected_labels: tuple[str, ...]
    category: str


BASE_FACTS = [
    Fact("name", "My name is Anders."),
    Fact("vehicle", "I drive a black Jeep."),
    Fact("hot_sauce_get", "I got hot sauce at Ocean Market."),
    Fact("hot_sauce_buy", "I bought hot sauce at Ocean Market."),
    Fact("japanese_candy", "I bought Japanese candy at Ocean Market."),
    Fact("obd_cable", "I keep the spare OBD cable in the glove box."),
    Fact("favorite_band", "My favorite band is Finch."),
    Fact("editor", "I use Zed for remote SSH editing."),
    Fact("garage_code", "My garage code is 8291."),
    Fact("lunch_place", "I ate lunch at Red Iguana."),
    Fact("coffee_order", "My coffee order is a black cold brew."),
    Fact("parking", "I parked on level three near the west elevator."),

    # ASR poison + correction cases
    Fact("vehicle_bad_asr", "I drive a black keeper."),
    Fact("vehicle_corrected", "I drive a black Jeep."),
    Fact("sauce_bad_asr", "I got horse exercise at Ocean Market."),
    Fact("sauce_corrected", "I got hot sauce at Ocean Market."),
]


QUERY_CASES = [
    QueryCase("name_exact", "What is my name?", ("name",), "identity"),
    QueryCase("name_who", "Who am I?", ("name",), "identity_bridge"),

    QueryCase("vehicle_drive", "What do I drive?", ("vehicle", "vehicle_corrected"), "vehicle"),
    QueryCase("vehicle_car", "What car do I drive?", ("vehicle", "vehicle_corrected"), "vehicle"),
    QueryCase("vehicle_have", "What vehicle do I have?", ("vehicle", "vehicle_corrected"), "vehicle_bridge"),

    QueryCase("hot_sauce_get", "Where did I get the hot sauce?", ("hot_sauce_get", "sauce_corrected"), "buy_get"),
    QueryCase("hot_sauce_buy", "Where did I buy hot sauce?", ("hot_sauce_buy",), "buy_get"),
    QueryCase("ocean_market_buy", "What did I buy at Ocean Market?", ("hot_sauce_buy", "japanese_candy"), "multi_memory"),

    QueryCase("obd_location", "Where is the OBD cable?", ("obd_cable",), "location"),
    QueryCase("favorite_band", "What is my favorite band?", ("favorite_band",), "preference"),
    QueryCase("editor", "What editor do I use?", ("editor",), "tooling"),
    QueryCase("garage_code", "What is my garage code?", ("garage_code",), "code"),
    QueryCase("lunch_place", "Where did I eat lunch?", ("lunch_place",), "location"),
    QueryCase("coffee_order", "What is my coffee order?", ("coffee_order",), "preference"),
    QueryCase("parking", "Where did I park?", ("parking",), "location"),
]


def make_distractors(target_count):
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

    facts = []
    i = 0

    while len(facts) < target_count:
        facts.append(
            Fact(
                f"distractor_buy_{i}",
                f"I bought {items[i % len(items)]} at {stores[i % len(stores)]}.",
            )
        )

        if len(facts) >= target_count:
            break

        facts.append(
            Fact(
                f"distractor_keep_{i}",
                f"I keep item {i} in the {places[i % len(places)]}.",
            )
        )

        if len(facts) >= target_count:
            break

        facts.append(
            Fact(
                f"distractor_like_{i}",
                f"My favorite test snack {i} is flavor {i}.",
            )
        )

        i += 1

    return facts


def build_facts(memory_count):
    facts = list(BASE_FACTS)

    if memory_count > len(facts):
        facts.extend(make_distractors(memory_count - len(facts)))

    return facts[:memory_count]


def build_store(memory_count):
    facts = build_facts(memory_count)
    store = SessionMemoryStore(max_memories=memory_count)

    label_to_ids = defaultdict(list)

    for fact in facts:
        memory_id = store.add_memory(fact.text)
        label_to_ids[fact.label].append(memory_id)

    return store, facts, label_to_ids


def fts_and_query(query):
    tokens = normalize_for_search(query).split()
    tokens = [token for token in tokens if token.strip()]
    return " ".join(tokens)


def search_sql(store, match_query, limit, newest):
    if not match_query:
        return []

    if newest:
        order_by = "bm25_score ASC, created_ts DESC, rowid DESC"
    else:
        order_by = "bm25_score ASC"

    sql = f"""
        SELECT rowid, raw_text, created_ts,
               bm25(memory_fts) AS bm25_score
        FROM memory_fts
        WHERE memory_fts MATCH ?
        ORDER BY {order_by}
        LIMIT ?
    """

    try:
        rows = store.conn.execute(sql, (match_query, int(limit))).fetchall()
    except sqlite3.OperationalError:
        return []

    return [
        {
            "id": int(row["rowid"]),
            "text": row["raw_text"],
            "score": float(row["bm25_score"]),
        }
        for row in rows
    ]


def pure_or(store, query, limit, newest):
    match_query = make_fts_query(query)
    hits = search_sql(store, match_query, limit, newest)

    for hit in hits:
        hit["source"] = "or"

    return hits, match_query, ""


def pure_and_then_or(store, query, limit, newest):
    and_query = fts_and_query(query)
    or_query = make_fts_query(query)

    hits = []
    seen = set()

    for source, match_query in [
        ("and", and_query),
        ("or", or_query),
    ]:
        for hit in search_sql(store, match_query, limit, newest):
            if hit["id"] in seen:
                continue

            seen.add(hit["id"])
            hit["source"] = source
            hits.append(hit)

            if len(hits) >= limit:
                return hits, and_query, or_query

    return hits, and_query, or_query


def evaluate(store, label_to_ids, memory_count, limit, mode, case):
    expected_ids = set()

    for label in case.expected_labels:
        expected_ids.update(label_to_ids.get(label, []))

    started = time.perf_counter_ns()

    if mode == "or_bm25":
        hits, primary_query, fallback_query = pure_or(
            store,
            case.query,
            limit,
            newest=False,
        )
    elif mode == "or_newest":
        hits, primary_query, fallback_query = pure_or(
            store,
            case.query,
            limit,
            newest=True,
        )
    elif mode == "and_then_or_newest":
        hits, primary_query, fallback_query = pure_and_then_or(
            store,
            case.query,
            limit,
            newest=True,
        )
    else:
        raise ValueError(mode)

    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0

    rank = None
    for index, hit in enumerate(hits, start=1):
        if hit["id"] in expected_ids:
            rank = index
            break

    return {
        "memory_count": memory_count,
        "limit": limit,
        "mode": mode,
        "case": case.name,
        "category": case.category,
        "query": case.query,
        "primary_query": primary_query,
        "fallback_query": fallback_query,
        "expected_labels": "|".join(case.expected_labels),
        "hit_texts": " || ".join(hit["text"] for hit in hits),
        "hit_sources": "|".join(hit["source"] for hit in hits),
        "rank": rank if rank is not None else "",
        "pass_top1": int(rank == 1),
        "pass_at_k": int(rank is not None),
        "latency_ms": elapsed_ms,
    }


def main():
    rows = []
    memory_counts = [16, 24, 48, 96, 192, 384, 768, 1536]
    limits = [1, 2, 3, 5]
    modes = [
        "or_bm25",
        "or_newest",
        "and_then_or_newest",
    ]

    started_all = time.perf_counter()

    for repeat in range(20):
        for memory_count in memory_counts:
            store, facts, label_to_ids = build_store(memory_count)

            for limit in limits:
                for mode in modes:
                    for case in QUERY_CASES:
                        row = evaluate(
                            store=store,
                            label_to_ids=label_to_ids,
                            memory_count=memory_count,
                            limit=limit,
                            mode=mode,
                            case=case,
                        )
                        row["repeat"] = repeat
                        rows.append(row)

    out_dir = REPO_ROOT / "test" / "benchmark" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = out_dir / f"fts5_pure_ranking_bench_{ts}.csv"
    summary_path = out_dir / f"fts5_pure_ranking_bench_{ts}.summary.json"

    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    groups = defaultdict(list)

    for row in rows:
        groups[(row["mode"], row["memory_count"], row["limit"])].append(row)

    summary = []

    for key, items in groups.items():
        total = len(items)
        latencies = [item["latency_ms"] for item in items]

        summary.append(
            {
                "mode": key[0],
                "memory_count": key[1],
                "limit": key[2],
                "top1": sum(item["pass_top1"] for item in items) / total,
                "at_k": sum(item["pass_at_k"] for item in items) / total,
                "p50_ms": statistics.median(latencies),
                "p95_ms": sorted(latencies)[max(0, int(total * 0.95) - 1)],
                "max_ms": max(latencies),
            }
        )

    summary = sorted(
        summary,
        key=lambda item: (
            -item["top1"],
            -item["at_k"],
            item["p50_ms"],
        ),
    )

    with summary_path.open("w") as fh:
        json.dump(summary, fh, indent=2)

    elapsed = time.perf_counter() - started_all

    print()
    print("PURE FTS5 RANKING BENCH DONE")
    print(f"elapsed={elapsed:.2f}s")
    print("CSV:", csv_path)
    print("SUMMARY:", summary_path)
    print()
    print("Best configs:")
    for item in summary[:30]:
        print(
            f"{item['mode']:>20} "
            f"mem={item['memory_count']:>4} "
            f"limit={item['limit']} "
            f"top1={item['top1']:.3f} "
            f"atk={item['at_k']:.3f} "
            f"p50={item['p50_ms']:.4f}ms "
            f"p95={item['p95_ms']:.4f}ms"
        )

    print()
    print("Interesting failures:")
    failures = [row for row in rows if row["pass_at_k"] == 0]
    seen = set()

    for row in failures[:120]:
        key = (
            row["mode"],
            row["memory_count"],
            row["limit"],
            row["case"],
            row["hit_texts"],
        )

        if key in seen:
            continue

        seen.add(key)

        print()
        print(
            f"{row['mode']} | mem={row['memory_count']} "
            f"limit={row['limit']} | {row['case']}"
        )
        print("query:", row["query"])
        print("expected:", row["expected_labels"])
        print("primary:", row["primary_query"])
        print("fallback:", row["fallback_query"])
        print("hits:", row["hit_texts"])
        print("sources:", row["hit_sources"])


if __name__ == "__main__":
    main()
