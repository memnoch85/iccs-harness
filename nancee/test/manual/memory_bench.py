#!/usr/bin/env python3
import argparse
import contextlib
import csv
import io
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHERPA = ROOT / "sherpa"
sys.path.insert(0, str(SHERPA))
os.environ.setdefault("NANCEE_MEMORY_DEBUG", "false")

from nancee_chat import extract_recall_user_text, should_retrieve_recall
from session_archive import SessionArchive
from config import MEMORY_RECALL_CONTEXT_MAX_CHARACTERS
from ollama_runtime import stream_ollama_response


@dataclass(frozen=True)
class FactDef:
    fact_id: str
    category: str
    stores: list[str]
    queries: list[str]
    expected_terms: list[str]
    forbidden_patterns: list[str]


def build_fact_defs():
    return [
        FactDef(
            "name_anders",
            "identity",
            [
                "Nancy, my name is Anders.",
                "Hello Nancy. I'm Anders. It's a pleasure to meet you.",
                "This is Anders.",
                "Hey Nancy, remember my name is Anders.",
                "For the record, my name is Anders.",
            ],
            [
                "What is my name?",
                "Can you recall my name?",
                "Do you remember my name?",
            ],
            ["anders"],
            [r"\bmy name is\b", r"\bi am anders\b", r"\bi'm anders\b"],
        ),
        FactDef(
            "preferred_name_andy",
            "identity",
            [
                "Nancy, call me Andy.",
                "I go by Andy.",
                "My nickname is Andy.",
                "Remember that I go by Andy.",
            ],
            [
                "What should you call me?",
                "What name do I go by?",
                "Do you remember my nickname?",
            ],
            ["andy"],
            [r"\bmy nickname\b", r"\bi go by\b"],
        ),
        FactDef(
            "vehicle_black_jeep",
            "vehicle",
            [
                "Nancy, I drive a black Jeep.",
                "My car is a black Jeep.",
                "My vehicle is a black Jeep.",
                "I own a black Jeep.",
                "Remember that I drive a black Jeep.",
            ],
            [
                "What car do I drive?",
                "What do I drive?",
                "Do you remember my vehicle?",
            ],
            ["black", "jeep"],
            [r"\bi drive\b", r"\bmy car\b", r"\bmy vehicle\b"],
        ),
        FactDef(
            "vehicle_blue_toyota",
            "vehicle",
            [
                "I drive a blue Toyota.",
                "My car is a blue Toyota.",
                "My vehicle is a blue Toyota.",
                "I own a blue Toyota.",
            ],
            [
                "What car do I drive?",
                "What vehicle do I have?",
                "What do I own?",
            ],
            ["blue", "toyota"],
            [r"\bi drive\b", r"\bmy car\b", r"\bmy vehicle\b"],
        ),
        FactDef(
            "favorite_band_finch",
            "favorite",
            [
                "My favorite band is Finch.",
                "Nancy, remember my favorite band is Finch.",
                "The band I like most is Finch.",
                "I love Finch more than any other band.",
            ],
            [
                "What is my favorite band?",
                "Do you remember my favorite band?",
                "What band do I like most?",
            ],
            ["finch"],
            [r"\bmy favorite band\b", r"\bi love finch\b"],
        ),
        FactDef(
            "favorite_song_burn",
            "favorite",
            [
                "My favorite song is What It Is To Burn.",
                "Remember my favorite song is What It Is To Burn.",
                "The song I like most is What It Is To Burn.",
            ],
            [
                "What is my favorite song?",
                "Do you remember my favorite song?",
                "What song do I like most?",
            ],
            ["what", "burn"],
            [r"\bmy favorite song\b"],
        ),
        FactDef(
            "favorite_anime_chainsaw",
            "favorite",
            [
                "My favorite anime is Chainsaw Man.",
                "Remember my favorite anime is Chainsaw Man.",
                "The anime I like most is Chainsaw Man.",
            ],
            [
                "What is my favorite anime?",
                "Do you remember my favorite anime?",
                "What anime do I like most?",
            ],
            ["chainsaw", "man"],
            [r"\bmy favorite anime\b"],
        ),
        FactDef(
            "favorite_movie_bladerunner",
            "favorite",
            [
                "My favorite movie is Blade Runner.",
                "Remember my favorite movie is Blade Runner.",
                "The movie I like most is Blade Runner.",
            ],
            [
                "What is my favorite movie?",
                "Do you remember my favorite movie?",
                "What movie do I like most?",
            ],
            ["blade", "runner"],
            [r"\bmy favorite movie\b"],
        ),
        FactDef(
            "favorite_show_severance",
            "favorite",
            [
                "My favorite show is Severance.",
                "Remember my favorite show is Severance.",
                "The show I like most is Severance.",
            ],
            [
                "What is my favorite show?",
                "Do you remember my favorite show?",
                "What show do I like most?",
            ],
            ["severance"],
            [r"\bmy favorite show\b"],
        ),
        FactDef(
            "favorite_food_tacos",
            "favorite",
            [
                "My favorite food is tacos.",
                "Remember my favorite food is tacos.",
                "The food I like most is tacos.",
            ],
            [
                "What is my favorite food?",
                "Do you remember my favorite food?",
                "What food do I like most?",
            ],
            ["tacos"],
            [r"\bmy favorite food\b"],
        ),
        FactDef(
            "favorite_drink_coffee",
            "favorite",
            [
                "My favorite drink is coffee.",
                "Remember my favorite drink is coffee.",
                "The drink I like most is coffee.",
            ],
            [
                "What is my favorite drink?",
                "Do you remember my favorite drink?",
                "What drink do I like most?",
            ],
            ["coffee"],
            [r"\bmy favorite drink\b"],
        ),
        FactDef(
            "coffee_order_black",
            "preference",
            [
                "My coffee order is black coffee.",
                "I like black coffee.",
                "Remember that I drink black coffee.",
            ],
            [
                "What is my coffee order?",
                "How do I take my coffee?",
                "Do you remember how I like coffee?",
            ],
            ["black", "coffee"],
            [r"\bmy coffee\b", r"\bi like black coffee\b"],
        ),
        FactDef(
            "favorite_color_green",
            "favorite",
            [
                "My favorite color is green.",
                "Remember my favorite color is green.",
                "The color I like most is green.",
            ],
            [
                "What is my favorite color?",
                "Do you remember my favorite color?",
                "What color do I like most?",
            ],
            ["green"],
            [r"\bmy favorite color\b"],
        ),
        FactDef(
            "favorite_restaurant_red_iguana",
            "favorite",
            [
                "My favorite restaurant is Red Iguana.",
                "Remember my favorite restaurant is Red Iguana.",
                "The restaurant I like most is Red Iguana.",
            ],
            [
                "What is my favorite restaurant?",
                "Do you remember my favorite restaurant?",
                "Where do I like to eat?",
            ],
            ["red", "iguana"],
            [r"\bmy favorite restaurant\b"],
        ),
        FactDef(
            "favorite_game_elden_ring",
            "favorite",
            [
                "My favorite game is Elden Ring.",
                "Remember my favorite game is Elden Ring.",
                "The game I like most is Elden Ring.",
            ],
            [
                "What is my favorite game?",
                "Do you remember my favorite game?",
                "What game do I like most?",
            ],
            ["elden", "ring"],
            [r"\bmy favorite game\b"],
        ),
        FactDef(
            "favorite_book_dune",
            "favorite",
            [
                "My favorite book is Dune.",
                "Remember my favorite book is Dune.",
                "The book I like most is Dune.",
            ],
            [
                "What is my favorite book?",
                "Do you remember my favorite book?",
                "What book do I like most?",
            ],
            ["dune"],
            [r"\bmy favorite book\b"],
        ),
        FactDef(
            "favorite_podcast_darknet",
            "favorite",
            [
                "My favorite podcast is Darknet Diaries.",
                "Remember my favorite podcast is Darknet Diaries.",
                "The podcast I like most is Darknet Diaries.",
            ],
            [
                "What is my favorite podcast?",
                "Do you remember my favorite podcast?",
                "What podcast do I like most?",
            ],
            ["darknet", "diaries"],
            [r"\bmy favorite podcast\b"],
        ),
        FactDef(
            "mechanic_dave",
            "service",
            [
                "My mechanic is Dave.",
                "Remember my mechanic is Dave.",
                "Dave is my mechanic.",
            ],
            [
                "Who is my mechanic?",
                "Do you remember my mechanic?",
                "Who works on my car?",
            ],
            ["dave"],
            [r"\bmy mechanic\b"],
        ),
        FactDef(
            "dog_loki",
            "pet",
            [
                "My dog's name is Loki.",
                "Remember my dog is named Loki.",
                "I have a dog named Loki.",
            ],
            [
                "What is my dog's name?",
                "Do you remember my dog?",
                "What is my pet named?",
            ],
            ["loki"],
            [r"\bmy dog\b", r"\bi have a dog\b"],
        ),
        FactDef(
            "cat_luna",
            "pet",
            [
                "My cat's name is Luna.",
                "Remember my cat is named Luna.",
                "I have a cat named Luna.",
            ],
            [
                "What is my cat's name?",
                "Do you remember my cat?",
                "What is my pet named?",
            ],
            ["luna"],
            [r"\bmy cat\b", r"\bi have a cat\b"],
        ),
        FactDef(
            "home_city_af",
            "location",
            [
                "I live in American Fork.",
                "My home city is American Fork.",
                "Remember that I live in American Fork.",
            ],
            [
                "Where do I live?",
                "Do you remember my city?",
                "What is my home city?",
            ],
            ["american", "fork"],
            [r"\bi live\b", r"\bmy home city\b"],
        ),
        FactDef(
            "work_city_slc",
            "work",
            [
                "I work in Salt Lake City.",
                "My work city is Salt Lake City.",
                "Remember that I work in Salt Lake City.",
            ],
            [
                "Where do I work?",
                "Do you remember my work city?",
                "What city do I work in?",
            ],
            ["salt", "lake"],
            [r"\bi work\b", r"\bmy work city\b"],
        ),
        FactDef(
            "job_iam_engineer",
            "work",
            [
                "I work as an IAM engineer.",
                "My job is IAM engineer.",
                "Remember that my job is IAM engineer.",
            ],
            [
                "What is my job?",
                "Do you remember what I do for work?",
                "What kind of engineer am I?",
            ],
            ["iam", "engineer"],
            [r"\bi work as\b", r"\bmy job\b"],
        ),
        FactDef(
            "commute_i15",
            "routine",
            [
                "I take I-15 to work.",
                "My commute route is I-15.",
                "Remember that I take I-15 to work.",
            ],
            [
                "What route do I take to work?",
                "Do you remember my commute?",
                "How do I get to work?",
            ],
            ["i-15"],
            [r"\bi take\b", r"\bmy commute\b"],
        ),
        FactDef(
            "gym_vasa",
            "routine",
            [
                "My gym is Vasa.",
                "I go to Vasa for the gym.",
                "Remember my gym is Vasa.",
            ],
            [
                "What is my gym?",
                "Do you remember where I work out?",
                "Where do I go to the gym?",
            ],
            ["vasa"],
            [r"\bmy gym\b"],
        ),
        FactDef(
            "grocery_smiths",
            "routine",
            [
                "My grocery store is Smiths.",
                "I shop at Smiths.",
                "Remember my grocery store is Smiths.",
            ],
            [
                "What is my grocery store?",
                "Where do I buy groceries?",
                "Do you remember where I shop?",
            ],
            ["smiths"],
            [r"\bmy grocery\b", r"\bi shop\b"],
        ),
        FactDef(
            "pharmacy_walgreens",
            "routine",
            [
                "My pharmacy is Walgreens.",
                "I use Walgreens as my pharmacy.",
                "Remember my pharmacy is Walgreens.",
            ],
            [
                "What is my pharmacy?",
                "Do you remember my pharmacy?",
                "Where do I pick up prescriptions?",
            ],
            ["walgreens"],
            [r"\bmy pharmacy\b"],
        ),
        FactDef(
            "tire_size",
            "vehicle",
            [
                "My tire size is 225 slash 65 R17.",
                "Remember my tire size is 225 slash 65 R17.",
                "The Jeep tire size is 225 slash 65 R17.",
            ],
            [
                "What is my tire size?",
                "Do you remember my tire size?",
                "What tires does my Jeep use?",
            ],
            ["225", "65", "17"],
            [r"\bmy tire size\b"],
        ),
        FactDef(
            "oil_type",
            "vehicle",
            [
                "My Jeep takes 5W-20 oil.",
                "Remember my Jeep takes 5W-20 oil.",
                "The oil type for my Jeep is 5W-20.",
            ],
            [
                "What oil does my Jeep take?",
                "Do you remember my oil type?",
                "What oil should I use?",
            ],
            ["5w", "20"],
            [r"\bmy jeep takes\b", r"\bmy oil\b"],
        ),
        FactDef(
            "parking_garage",
            "routine",
            [
                "I park in the garage.",
                "My parking spot is the garage.",
                "Remember that I park in the garage.",
            ],
            [
                "Where do I park?",
                "Do you remember my parking spot?",
                "Where is my parking spot?",
            ],
            ["garage"],
            [r"\bi park\b", r"\bmy parking\b"],
        ),
    ]


def make_cases(limit):
    cases = []
    for fact in build_fact_defs():
        for store in fact.stores:
            for query in fact.queries:
                cases.append(
                    {
                        "case_id": f"{fact.fact_id}_{len(cases)+1}",
                        "fact_id": fact.fact_id,
                        "category": fact.category,
                        "store": store,
                        "query": query,
                        "expected_terms": fact.expected_terms,
                        "forbidden_patterns": fact.forbidden_patterns,
                    }
                )
    return cases[:limit]


def contains_expected(answer, expected_terms):
    lowered = answer.lower()
    return all(term.lower() in lowered for term in expected_terms)


def find_forbidden(answer, forbidden_patterns):
    lowered = answer.lower()
    for pattern in forbidden_patterns:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            return pattern
    return ""


def collect_llm_response(query, context):
    buf = io.StringIO()
    started = time.time()
    with contextlib.redirect_stdout(buf):
        chunks = stream_ollama_response(
            user_text=query,
            history=[] if context else [],
            memory_context="",
            retrieved_context=context,
        )
        answer = "".join(chunks)
    return answer.strip(), time.time() - started, buf.getvalue()


def run_case(case, run_number, args):
    archive = SessionArchive(max_turns=24)

    extracted = extract_recall_user_text(case["store"])
    store_ok = bool(extracted)
    if store_ok:
        archive.add_turn(extracted, "Okay.")

    retrieve_requested = should_retrieve_recall(case["query"])
    hits = []
    context = ""

    if retrieve_requested and store_ok:
        hits = archive.retrieve(
            case["query"],
            limit=args.recall_limit,
            min_score=args.min_score,
        )
        context = archive.format_related_context(
            hits,
            max_characters=MEMORY_RECALL_CONTEXT_MAX_CHARACTERS,
        )
        retrieve_ok = bool(context)

    base = {
        "case_id": case["case_id"],
        "fact_id": case["fact_id"],
        "category": case["category"],
        "run": run_number,
        "store": case["store"],
        "query": case["query"],
        "extracted": extracted,
        "retrieve_requested": retrieve_requested,
        "hit_count": len(hits),
        "scores": "|".join(str(hit.get("score", "")) for hit in hits),
        "context": context,
        "answer": "",
        "elapsed_sec": "",
        "expected_ok": False,
        "forbidden_hit": "",
        "status": "",
    }

    if not store_ok:
        base["status"] = "EXTRACT_FAIL"
        return base

    if not retrieve_requested:
        base["status"] = "ROUTER_FAIL"
        return base

    if not retrieve_ok:
        base["status"] = "RETRIEVE_FAIL"
        return base

    if args.router_only:
        base["status"] = "ROUTER_RETRIEVE_PASS"
        return base

    answer, elapsed, runtime_log = collect_llm_response(case["query"], context)
    expected_ok = contains_expected(answer, case["expected_terms"])
    forbidden_hit = find_forbidden(answer, case["forbidden_patterns"])

    base["answer"] = answer
    base["elapsed_sec"] = f"{elapsed:.3f}"
    base["expected_ok"] = expected_ok
    base["forbidden_hit"] = forbidden_hit

    if not expected_ok:
        base["status"] = "LLM_EXPECTED_FAIL"
    elif forbidden_hit:
        base["status"] = "LLM_PERSPECTIVE_FAIL"
    else:
        base["status"] = "PASS"

    if base["status"] != "PASS" and args.failure_log:
        with open(args.failure_log, "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 88 + "\n")
            f.write(f"case_id={case['case_id']} run={run_number} status={base['status']}\n")
            f.write(f"store={case['store']}\n")
            f.write(f"query={case['query']}\n")
            f.write(f"extracted={extracted}\n")
            f.write(f"context={context}\n")
            f.write(f"answer={answer}\n")
            f.write(f"forbidden_hit={forbidden_hit}\n")
            f.write("--- runtime log ---\n")
            f.write(runtime_log)

    return base


def write_summary(rows, path):
    grouped = {}
    for row in rows:
        key = (row["fact_id"], row["category"])
        grouped.setdefault(key, {})
        grouped[key][row["status"]] = grouped[key].get(row["status"], 0) + 1

    statuses = [
        "PASS",
        "ROUTER_RETRIEVE_PASS",
        "EXTRACT_FAIL",
        "ROUTER_FAIL",
        "RETRIEVE_FAIL",
        "LLM_EXPECTED_FAIL",
        "LLM_PERSPECTIVE_FAIL",
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["fact_id", "category", "total"] + statuses)
        for (fact_id, category), counts in sorted(grouped.items()):
            total = sum(counts.values())
            writer.writerow(
                [fact_id, category, total] + [counts.get(status, 0) for status in statuses]
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=150)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--router-only", action="store_true")
    parser.add_argument("--min-score", type=float, default=1.0)
    parser.add_argument("--recall-limit", type=int, default=3)
    parser.add_argument(
        "--out",
        default=str(ROOT / "test/manual/results/memory_bench_runs.csv"),
    )
    parser.add_argument(
        "--summary",
        default=str(ROOT / "test/manual/results/memory_bench_summary.csv"),
    )
    parser.add_argument(
        "--failure-log",
        default=str(ROOT / "test/manual/results/memory_bench_failures.txt"),
    )

    args = parser.parse_args()

    cases = make_cases(args.limit)
    rows = []

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    if args.failure_log:
        Path(args.failure_log).write_text("", encoding="utf-8")

    fields = [
        "case_id",
        "fact_id",
        "category",
        "run",
        "store",
        "query",
        "extracted",
        "retrieve_requested",
        "hit_count",
        "scores",
        "context",
        "answer",
        "elapsed_sec",
        "expected_ok",
        "forbidden_hit",
        "status",
    ]

    started = time.time()
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()

        total = len(cases) * args.runs
        for run_number in range(1, args.runs + 1):
            for index, case in enumerate(cases, start=1):
                row = run_case(case, run_number, args)
                rows.append(row)
                writer.writerow(row)
                f.flush()

                done = ((run_number - 1) * len(cases)) + index
                print(
                    f"[{done}/{total}] {row['status']} "
                    f"{case['case_id']} :: {case['query']}",
                    flush=True,
                )

    write_summary(rows, args.summary)

    elapsed = time.time() - started
    print()
    print(f"rows={len(rows)} elapsed={elapsed:.1f}s")
    print(f"runs_csv={args.out}")
    print(f"summary_csv={args.summary}")
    print(f"failure_log={args.failure_log}")


if __name__ == "__main__":
    main()
