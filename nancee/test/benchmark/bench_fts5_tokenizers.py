#!/usr/bin/env python3

import csv
import json
import sqlite3
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Fact:
    label: str
    text: str


@dataclass(frozen=True)
class QueryCase:
    name: str
    query: str
    expected_labels: tuple[str, ...]


FACTS = [
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
    Fact("vehicle_bad_asr", "I drive a black keeper."),
    Fact("vehicle_corrected", "I drive a black Jeep."),
    Fact("sauce_bad_asr", "I got horse exercise at Ocean Market."),
    Fact("sauce_corrected", "I got hot sauce at Ocean Market."),
]


QUERIES = [
    QueryCase("name_exact", "What is my name?", ("name",)),
    QueryCase("name_who", "Who am I?", ("name",)),
    QueryCase("vehicle_drive", "What do I drive?", ("vehicle", "vehicle_corrected")),
    QueryCase("vehicle_car", "What car do I drive?", ("vehicle", "vehicle_corrected")),
    QueryCase("vehicle_have", "What vehicle do I have?", ("vehicle", "vehicle_corrected")),
    QueryCase("hot_sauce_get", "Where did I get the hot sauce?", ("hot_sauce_get", "sauce_corrected")),
    QueryCase("hot_sauce_buy", "Where did I buy hot sauce?", ("hot_sauce_buy",)),
    QueryCase("ocean_market_buy", "What did I buy at Ocean Market?", ("hot_sauce_buy", "japanese_candy")),
    QueryCase("obd_location", "Where is the OBD cable?", ("obd_cable",)),
    QueryCase("favorite_band", "What is my favorite band?", ("favorite_band",)),
    QueryCase("editor", "What editor do I use?", ("editor",)),
    QueryCase("garage_code", "What is my garage code?", ("garage_code",)),
    QueryCase("lunch_place", "Where did I eat lunch?", ("lunch_place",)),
    QueryCase("coffee_order", "What is my coffee order?", ("coffee_order",)),
    QueryCase("parking", "Where did I park?", ("parking",)),
]


STOPWORDS = {
    "what", "where", "who", "is", "am", "i", "my", "me", "do", "did",
    "the", "a", "an", "at", "in", "on", "of", "to", "for",
}


def tokens(text):
    cleaned = []
    current = []

    for ch in text.lower():
        if ch.isalnum():
            current.append(ch)
        else:
            if current:
                cleaned.append("".join(current))
                current = []

    if current:
        cleaned.append("".join(current))

    return [t for t in cleaned if t not in STOPWORDS]


def or_query(text):
    ts = tokens(text)
    return " OR ".join(ts)


def and_query(text):
    ts = tokens(text)
    return " ".join(ts)


def build_conn(tokenizer):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    conn.execute(f"""
        CREATE VIRTUAL TABLE memory_fts
        USING fts5(
            raw_text,
            label UNINDEXED,
            tokenize = '{tokenizer}'
        )
    """)

    for fact in FACTS:
        conn.execute(
            "INSERT INTO memory_fts(raw_text, label) VALUES (?, ?)",
            (fact.text, fact.label),
        )

    conn.commit()
    return conn


def search(conn, query, limit, query_mode):
    if query_mode == "or":
        match = or_query(query)
    elif query_mode == "and_then_or":
        match = and_query(query)
    else:
        raise ValueError(query_mode)

    if not match:
        return [], match

    sql = """
        SELECT rowid, raw_text, label, bm25(memory_fts) AS score
        FROM memory_fts
        WHERE memory_fts MATCH ?
        ORDER BY score ASC, rowid DESC
        LIMIT ?
    """

    try:
        rows = conn.execute(sql, (match, limit)).fetchall()
    except sqlite3.OperationalError:
        rows = []

    if query_mode == "and_then_or" and not rows:
        match = or_query(query)
        try:
            rows = conn.execute(sql, (match, limit)).fetchall()
        except sqlite3.OperationalError:
            rows = []

    return rows, match


def evaluate(tokenizer, query_mode, limit, case):
    conn = build_conn(tokenizer)

    started = time.perf_counter_ns()
    rows, match = search(conn, case.query, limit, query_mode)
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0

    labels = [row["label"] for row in rows]
    rank = None

    for idx, label in enumerate(labels, start=1):
        if label in case.expected_labels:
            rank = idx
            break

    return {
        "tokenizer": tokenizer,
        "query_mode": query_mode,
        "limit": limit,
        "case": case.name,
        "query": case.query,
        "match": match,
        "expected": "|".join(case.expected_labels),
        "labels": "|".join(labels),
        "texts": " || ".join(row["raw_text"] for row in rows),
        "rank": rank if rank is not None else "",
        "top1": int(rank == 1),
        "at_k": int(rank is not None),
        "latency_ms": elapsed_ms,
    }


def main():
    tokenizers = [
        "unicode61",
        "porter unicode61",
    ]

    query_modes = [
        "or",
        "and_then_or",
    ]

    rows = []

    for tokenizer in tokenizers:
        for query_mode in query_modes:
            for limit in [1, 2, 3, 5]:
                for case in QUERIES:
                    for _ in range(50):
                        rows.append(
                            evaluate(
                                tokenizer=tokenizer,
                                query_mode=query_mode,
                                limit=limit,
                                case=case,
                            )
                        )

    out_dir = REPO_ROOT / "test" / "benchmark" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = out_dir / f"fts5_tokenizer_bench_{ts}.csv"
    summary_path = out_dir / f"fts5_tokenizer_bench_{ts}.summary.json"

    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    groups = defaultdict(list)

    for row in rows:
        groups[(row["tokenizer"], row["query_mode"], row["limit"])].append(row)

    summary = []

    for key, items in groups.items():
        total = len(items)
        latencies = [r["latency_ms"] for r in items]

        summary.append({
            "tokenizer": key[0],
            "query_mode": key[1],
            "limit": key[2],
            "top1": sum(r["top1"] for r in items) / total,
            "at_k": sum(r["at_k"] for r in items) / total,
            "p50_ms": statistics.median(latencies),
            "p95_ms": sorted(latencies)[max(0, int(total * 0.95) - 1)],
        })

    summary = sorted(
        summary,
        key=lambda x: (-x["top1"], -x["at_k"], x["p50_ms"]),
    )

    with summary_path.open("w") as fh:
        json.dump(summary, fh, indent=2)

    print()
    print("FTS5 TOKENIZER BENCH DONE")
    print("CSV:", csv_path)
    print("SUMMARY:", summary_path)
    print()
    for item in summary:
        print(
            f"{item['tokenizer']:>16} "
            f"{item['query_mode']:>12} "
            f"limit={item['limit']} "
            f"top1={item['top1']:.3f} "
            f"atk={item['at_k']:.3f} "
            f"p50={item['p50_ms']:.4f}ms "
            f"p95={item['p95_ms']:.4f}ms"
        )

    print()
    print("Failures for best config:")
    best = summary[0]
    failures = [
        r for r in rows
        if r["tokenizer"] == best["tokenizer"]
        and r["query_mode"] == best["query_mode"]
        and r["limit"] == best["limit"]
        and r["at_k"] == 0
    ]

    seen = set()
    for r in failures:
        key = (r["case"], r["query"], r["texts"])
        if key in seen:
            continue
        seen.add(key)

        print()
        print(r["case"], "|", r["query"])
        print("expected:", r["expected"])
        print("match:", r["match"])
        print("labels:", r["labels"])
        print("texts:", r["texts"])


if __name__ == "__main__":
    main()
