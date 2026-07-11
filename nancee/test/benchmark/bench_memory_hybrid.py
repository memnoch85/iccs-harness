#!/usr/bin/env python3

import argparse
import csv
import json
import re
import sqlite3
import statistics
import sys
import time
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SHERPA_DIR = REPO_ROOT / "sherpa"
BENCH_DIR = REPO_ROOT / "test" / "benchmark"

sys.path.insert(0, str(SHERPA_DIR))
sys.path.insert(0, str(BENCH_DIR))

from config import LLM_MODEL  # noqa: E402
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
    expected_terms: tuple[str, ...]
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

    # Correction / poison cases.
    Fact("vehicle_bad_asr", "I drive a black keeper."),
    Fact("vehicle_corrected", "I drive a black Jeep."),
    Fact("sauce_bad_asr", "I got horse exercise at Ocean Market."),
    Fact("sauce_corrected", "I got hot sauce at Ocean Market."),
]


QUERY_CASES = [
    QueryCase("name_exact", "What is my name?", ("name",), ("anders",), "identity"),
    QueryCase("name_who", "Who am I?", ("name",), ("anders",), "identity_bridge"),

    QueryCase("vehicle_drive", "What do I drive?", ("vehicle", "vehicle_corrected"), ("black", "jeep"), "vehicle"),
    QueryCase("vehicle_car", "What car do I drive?", ("vehicle", "vehicle_corrected"), ("black", "jeep"), "vehicle"),
    QueryCase("vehicle_have", "What vehicle do I have?", ("vehicle", "vehicle_corrected"), ("black", "jeep"), "vehicle_bridge"),

    QueryCase("hot_sauce_get", "Where did I get the hot sauce?", ("hot_sauce_get", "sauce_corrected"), ("ocean", "market"), "buy_get"),
    QueryCase("hot_sauce_buy", "Where did I buy hot sauce?", ("hot_sauce_buy",), ("ocean", "market"), "buy_get"),
    QueryCase("ocean_market_buy", "What did I buy at Ocean Market?", ("hot_sauce_buy", "japanese_candy"), ("japanese", "candy"), "multi_memory"),

    QueryCase("obd_location", "Where is the OBD cable?", ("obd_cable",), ("glove", "box"), "location"),
    QueryCase("favorite_band", "What is my favorite band?", ("favorite_band",), ("finch",), "preference"),
    QueryCase("editor", "What editor do I use?", ("editor",), ("zed",), "tooling"),
    QueryCase("garage_code", "What is my garage code?", ("garage_code",), ("8291",), "code"),
    QueryCase("lunch_place", "Where did I eat lunch?", ("lunch_place",), ("red", "iguana"), "location"),
    QueryCase("coffee_order", "What is my coffee order?", ("coffee_order",), ("black", "cold", "brew"), "preference"),
    QueryCase("parking", "Where did I park?", ("parking",), ("level", "three"), "location"),
]


QUERY_EXPANSIONS = {
    "who": ["name"],
    "called": ["name", "call"],
    "call": ["name", "called"],

    "drive": ["drive", "car", "vehicle"],
    "driving": ["drive", "car", "vehicle"],
    "car": ["car", "vehicle", "drive"],
    "vehicle": ["vehicle", "car", "drive"],
    "jeep": ["jeep", "vehicle", "car"],
    "own": ["own", "drive", "vehicle", "car"],
    "have": ["have", "own", "drive", "vehicle", "car"],

    "buy": ["buy", "bought", "get", "got"],
    "bought": ["bought", "buy", "get", "got"],
    "get": ["get", "got", "buy", "bought"],
    "got": ["got", "get", "buy", "bought"],

    "park": ["park", "parked", "parking"],
    "parked": ["parked", "park", "parking"],
    "eat": ["eat", "ate", "lunch"],
    "ate": ["ate", "eat", "lunch"],

    "favorite": ["favorite", "prefer", "preference"],
    "prefer": ["prefer", "favorite", "preference"],
}


STRATEGIES = {
    # Pure FTS5.
    "fts_current_k1": {
        "fts_mode": "current",
        "fts_limit": 1,
    },
    "fts_current_k3": {
        "fts_mode": "current",
        "fts_limit": 3,
    },
    "fts_expanded_k3": {
        "fts_mode": "expanded_newest",
        "fts_limit": 3,
    },
    "fts_expanded_k5": {
        "fts_mode": "expanded_newest",
        "fts_limit": 5,
    },

    # Recent Python vars only.
    "vars_last5": {
        "vars_last": 5,
    },
    "vars_last8": {
        "vars_last": 8,
    },

    # Background prime only.
    "prime5_keep12_stale": {
        "prime_every": 5,
        "prime_keep": 12,
        "prime_flush": False,
    },
    "prime5_keep24_stale": {
        "prime_every": 5,
        "prime_keep": 24,
        "prime_flush": False,
    },
    "prime5_keep24_flush": {
        "prime_every": 5,
        "prime_keep": 24,
        "prime_flush": True,
    },
    "prime8_keep24_stale": {
        "prime_every": 8,
        "prime_keep": 24,
        "prime_flush": False,
    },

    # Hybrids.
    "hybrid_vars5_fts3": {
        "vars_last": 5,
        "fts_mode": "expanded_newest",
        "fts_limit": 3,
    },
    "hybrid_vars8_fts3": {
        "vars_last": 8,
        "fts_mode": "expanded_newest",
        "fts_limit": 3,
    },
    "hybrid_prime5_12_fts3": {
        "prime_every": 5,
        "prime_keep": 12,
        "prime_flush": False,
        "fts_mode": "expanded_newest",
        "fts_limit": 3,
    },
    "hybrid_prime5_24_fts3": {
        "prime_every": 5,
        "prime_keep": 24,
        "prime_flush": False,
        "fts_mode": "expanded_newest",
        "fts_limit": 3,
    },
    "hybrid_prime5_24_flush_fts3": {
        "prime_every": 5,
        "prime_keep": 24,
        "prime_flush": True,
        "fts_mode": "expanded_newest",
        "fts_limit": 3,
    },
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


def build_store(facts, max_memories):
    store = SessionMemoryStore(max_memories=max_memories)
    label_to_id = {}
    id_to_fact = {}

    for fact in facts:
        memory_id = store.add_memory(fact.text)
        label_to_id.setdefault(fact.label, []).append(memory_id)
        id_to_fact[memory_id] = fact

    return store, label_to_id, id_to_fact


def search_fts(store, query, mode, limit):
    if not mode or not limit:
        return [], "", 0.0

    if mode == "current":
        started = time.perf_counter_ns()
        hits = store.search_memory(query, limit=limit)
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0

        return [
            {
                "id": hit.id,
                "text": hit.raw_text,
                "score": hit.bm25_score,
                "source": "fts_current",
            }
            for hit in hits
        ], make_fts_query(query), elapsed_ms

    if mode == "expanded_newest":
        match_query = fts_or(expanded_tokens(query))

        if not match_query:
            return [], "", 0.0

        sql = """
            SELECT rowid, raw_text, search_text, created_ts,
                   bm25(memory_fts) AS bm25_score
            FROM memory_fts
            WHERE memory_fts MATCH ?
            ORDER BY bm25_score ASC, created_ts DESC, rowid DESC
            LIMIT ?
        """

        started = time.perf_counter_ns()

        try:
            rows = store.conn.execute(
                sql,
                (match_query, int(limit)),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []

        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0

        return [
            {
                "id": int(row["rowid"]),
                "text": row["raw_text"],
                "score": float(row["bm25_score"]),
                "source": "fts_expanded_newest",
            }
            for row in rows
        ], match_query, elapsed_ms

    raise ValueError(f"Unknown FTS mode: {mode}")


def simulate_prime(facts, every, keep, flush):
    if not every or not keep:
        return []

    prime = []

    for index in range(1, len(facts) + 1):
        if index % every == 0:
            prime = facts[max(0, index - keep):index]

    if flush:
        prime = facts[max(0, len(facts) - keep):]

    return prime


def add_context_item(items, seen, source, fact):
    key = fact.text.strip().lower()

    if key in seen:
        return

    seen.add(key)

    items.append(
        {
            "source": source,
            "label": fact.label,
            "id": "",
            "text": fact.text,
            "score": "",
        }
    )


def build_context_items(strategy_name, strategy, facts, store, id_to_fact, query):
    items = []
    seen = set()
    retrieval_ms = 0.0
    match_query = ""

    if strategy.get("prime_every"):
        prime_facts = simulate_prime(
            facts=facts,
            every=strategy["prime_every"],
            keep=strategy["prime_keep"],
            flush=strategy.get("prime_flush", False),
        )

        for fact in prime_facts:
            add_context_item(items, seen, "prime", fact)

    if strategy.get("vars_last"):
        for fact in facts[-strategy["vars_last"]:]:
            add_context_item(items, seen, "vars", fact)

    if strategy.get("fts_mode"):
        fts_hits, match_query, retrieval_ms = search_fts(
            store=store,
            query=query,
            mode=strategy["fts_mode"],
            limit=strategy["fts_limit"],
        )

        for hit in fts_hits:
            fact = id_to_fact.get(hit["id"])

            if fact is None:
                continue

            key = fact.text.strip().lower()

            if key in seen:
                continue

            seen.add(key)

            items.append(
                {
                    "source": hit["source"],
                    "label": fact.label,
                    "id": hit["id"],
                    "text": fact.text,
                    "score": hit["score"],
                }
            )

    return items, match_query, retrieval_ms


def format_memory_context(items, max_chars):
    if not items:
        return ""

    lines = [
        "RELEVANT USER MEMORY:",
        "The lines below are direct quotes from the human user, not from Nancee.",
        "Inside those quotes, I/me/my means the human user.",
        "When answering, convert quoted I/me/my into you/your.",
        "Never answer user-memory questions with I/my.",
        "Only say I/my when talking about Nancee.",
        "USER MEMORY QUOTES:",
    ]

    for item in items:
        lines.append(f'- Human user said: "{item["text"]}"')

    context = "\n".join(lines)

    if len(context) <= max_chars:
        return context

    return context[:max_chars].rstrip()


def expected_hit(items, expected_labels):
    labels = [item["label"] for item in items]
    return any(label in labels for label in expected_labels)


def expected_rank(items, expected_labels):
    for index, item in enumerate(items, start=1):
        if item["label"] in expected_labels:
            return index

    return None


def llm_call(model, query, context, temperature, num_predict, timeout):
    system = (
        "You are Nancee. Answer only the user's question. "
        "Use relevant user memory when provided. "
        "Memory lines are things the human user said earlier. "
        "In memory lines, I/me/my means the human user. "
        "Answer with you/your for user facts. Do not guess."
    )

    messages = [
        {
            "role": "system",
            "content": system,
        }
    ]

    if context.strip():
        messages.append(
            {
                "role": "system",
                "content": "Use this memory to answer:\n\n" + context,
            }
        )

    messages.append(
        {
            "role": "user",
            "content": query,
        }
    )

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
        },
    }

    data = json.dumps(payload).encode("utf-8")

    started = time.perf_counter()

    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))

    elapsed_ms = (time.perf_counter() - started) * 1000.0

    content = body.get("message", {}).get("content", "").strip()

    return {
        "llm_response": content,
        "llm_wall_ms": elapsed_ms,
        "llm_total_ms": body.get("total_duration", 0) / 1_000_000.0,
        "llm_load_ms": body.get("load_duration", 0) / 1_000_000.0,
        "llm_prompt_eval_ms": body.get("prompt_eval_duration", 0) / 1_000_000.0,
        "llm_eval_ms": body.get("eval_duration", 0) / 1_000_000.0,
        "llm_prompt_tokens": body.get("prompt_eval_count", 0),
        "llm_response_tokens": body.get("eval_count", 0),
    }


def llm_pass(response, expected_terms):
    lowered = response.lower()
    return all(term.lower() in lowered for term in expected_terms)


def evaluate_one(
    memory_count,
    strategy_name,
    strategy,
    query_case,
    context_max_chars,
    run_llm,
    llm_args,
):
    facts = build_facts(memory_count)
    store, label_to_id, id_to_fact = build_store(
        facts=facts,
        max_memories=memory_count,
    )

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

    for row in rows:
        grouped[row["strategy"]].append(row)

    summary = []

    for strategy, items in sorted(grouped.items()):
        total = len(items)
        retrievals = [float(item["retrieval_ms"]) for item in items]
        context_chars = [int(item["context_chars"]) for item in items]
        quote_counts = [int(item["quote_count"]) for item in items]

        llm_rows = [
            item for item in items
            if str(item["llm_enabled"]) == "1"
        ]

        output = {
            "strategy": strategy,
            "total": total,
            "context_hit_rate": sum(int(item["context_hit"]) for item in items) / total,
            "avg_rank": statistics.mean(
                [
                    int(item["rank"])
                    for item in items
                    if str(item["rank"]).strip()
                ]
            ) if any(str(item["rank"]).strip() for item in items) else None,
            "retrieval_p50_ms": statistics.median(retrievals),
            "retrieval_p95_ms": sorted(retrievals)[max(0, int(total * 0.95) - 1)],
            "retrieval_max_ms": max(retrievals),
            "avg_context_chars": statistics.mean(context_chars),
            "avg_quote_count": statistics.mean(quote_counts),
        }

        if llm_rows:
            prompt_eval = [
                float(item["llm_prompt_eval_ms"])
                for item in llm_rows
                if str(item["llm_prompt_eval_ms"]).strip()
            ]
            output["llm_pass_rate"] = sum(int(item["llm_pass"]) for item in llm_rows) / len(llm_rows)
            output["llm_prompt_eval_p50_ms"] = statistics.median(prompt_eval) if prompt_eval else None
            output["llm_prompt_eval_max_ms"] = max(prompt_eval) if prompt_eval else None

        summary.append(output)

    summary = sorted(
        summary,
        key=lambda x: (
            -x["context_hit_rate"],
            x["avg_context_chars"],
            x["retrieval_p50_ms"],
        ),
    )

    failures = [
        row for row in rows
        if int(row["context_hit"]) == 0
    ]

    return {
        "summary": summary,
        "failures": failures[:200],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--memory-counts", default="16,24,48,96,192,384")
    parser.add_argument("--strategies", default=",".join(STRATEGIES.keys()))
    parser.add_argument("--context-chars", type=int, default=650)
    parser.add_argument("--repeat", type=int, default=10)

    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--llm-max-rows", type=int, default=120)
    parser.add_argument("--llm-model", default=LLM_MODEL)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--num-predict", type=int, default=40)
    parser.add_argument("--timeout", type=float, default=120.0)

    args = parser.parse_args()

    memory_counts = [int(x) for x in args.memory_counts.split(",") if x.strip()]
    strategy_names = [x.strip() for x in args.strategies.split(",") if x.strip()]

    unknown = [name for name in strategy_names if name not in STRATEGIES]
    if unknown:
        raise SystemExit(f"Unknown strategies: {unknown}")

    rows = []
    llm_rows_used = 0

    for repeat in range(args.repeat):
        for memory_count in memory_counts:
            for strategy_name in strategy_names:
                strategy = STRATEGIES[strategy_name]

                for query_case in QUERY_CASES:
                    run_llm = False

                    if args.llm and llm_rows_used < args.llm_max_rows:
                        run_llm = True
                        llm_rows_used += 1

                    row = evaluate_one(
                        memory_count=memory_count,
                        strategy_name=strategy_name,
                        strategy=strategy,
                        query_case=query_case,
                        context_max_chars=args.context_chars,
                        run_llm=run_llm,
                        llm_args={
                            "model": args.llm_model,
                            "temperature": args.temperature,
                            "num_predict": args.num_predict,
                            "timeout": args.timeout,
                        },
                    )
                    row["repeat"] = repeat
                    rows.append(row)

    out_dir = REPO_ROOT / "test" / "benchmark" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = out_dir / f"memory_hybrid_bench_{timestamp}.csv"
    summary_path = out_dir / f"memory_hybrid_bench_{timestamp}.summary.json"

    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    summary = summarize(rows)

    with summary_path.open("w") as fh:
        json.dump(summary, fh, indent=2)

    print()
    print("HYBRID MEMORY BENCH DONE")
    print(f"CSV: {csv_path}")
    print(f"SUMMARY: {summary_path}")
    print()
    print("Top strategy summary:")
    for item in summary["summary"][:20]:
        print(
            f"{item['strategy']:>30} "
            f"hit={item['context_hit_rate']:.3f} "
            f"avg_rank={item['avg_rank']} "
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
