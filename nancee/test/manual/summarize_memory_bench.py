#!/usr/bin/env python3

import csv
from collections import Counter, defaultdict
from pathlib import Path

runs = Path("test/manual/results/memory_bench_runs.csv")
out = Path("test/manual/results/memory_bench_digest.txt")

rows = list(csv.DictReader(runs.open(newline="", encoding="utf-8")))

def write_section(f, title):
    f.write("\n" + "=" * 88 + "\n")
    f.write(title + "\n")
    f.write("=" * 88 + "\n")

with out.open("w", encoding="utf-8") as f:
    f.write(f"rows={len(rows)}\n")

    write_section(f, "STATUS TOTALS")
    for status, count in Counter(r["status"] for r in rows).most_common():
        f.write(f"{count:6} {status}\n")

    write_section(f, "FACT_ID BY STATUS")
    counts = Counter((r["fact_id"], r["category"], r["status"]) for r in rows)
    for (fact_id, category, status), count in counts.most_common(80):
        f.write(f"{count:6} {status:22} {category:12} {fact_id}\n")

    write_section(f, "EXTRACT FAILS BY STORE PHRASE")
    counts = Counter(r["store"] for r in rows if r["status"] == "EXTRACT_FAIL")
    for store, count in counts.most_common(80):
        f.write(f"{count:6} {store}\n")

    write_section(f, "ROUTER FAILS BY QUERY")
    counts = Counter(r["query"] for r in rows if r["status"] == "ROUTER_FAIL")
    for query, count in counts.most_common(80):
        f.write(f"{count:6} {query}\n")

    write_section(f, "RETRIEVE FAILS BY FACT / QUERY / EXTRACTED")
    for r in [x for x in rows if x["status"] == "RETRIEVE_FAIL"][:120]:
        f.write(
            f"{r['fact_id']} | query={r['query']} | extracted={r['extracted']} | scores={r['scores']}\n"
        )

    write_section(f, "LLM FAILS BY FACT / QUERY")
    counts = Counter(
        (r["fact_id"], r["query"], r["status"])
        for r in rows
        if r["status"].startswith("LLM_")
    )
    for (fact_id, query, status), count in counts.most_common(120):
        f.write(f"{count:6} {status:22} {fact_id:28} {query}\n")

    write_section(f, "SAMPLE LLM FAILURES")
    sample_count = 0
    for r in rows:
        if not r["status"].startswith("LLM_"):
            continue

        sample_count += 1
        f.write("\n" + "-" * 88 + "\n")
        f.write(f"status={r['status']} case_id={r['case_id']} run={r['run']}\n")
        f.write(f"fact_id={r['fact_id']} category={r['category']}\n")
        f.write(f"store={r['store']}\n")
        f.write(f"query={r['query']}\n")
        f.write(f"extracted={r['extracted']}\n")
        f.write(f"context={r['context']}\n")
        f.write(f"answer={r['answer']}\n")
        f.write(f"forbidden_hit={r['forbidden_hit']}\n")

        if sample_count >= 120:
            break

print(out)
