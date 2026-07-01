import json
import urllib.error
import urllib.request

from config import (
    LLM_MODEL,
    LLM_NUM_THREADS,
    OLLAMA_RESPONSE_TIMEOUT,
    OLLAMA_URL,
)

CONSOLIDATION_SYSTEM_PROMPT = """
You are a memory consolidation component for Nancee.

Rewrite the existing session summary and the supplied older conversation
turns into one compact plain-text memory summary.

Preserve:
- explicit user-provided names and relationships
- plans, destinations, preferences, and corrections
- shared stories that may matter later in the same session
- unresolved questions or promised follow-up
- explicit vehicle observations, DTCs, and diagnostic outcomes

Rules:
- Do not treat assistant guesses, jokes, or suggestions as user facts.
- Do not invent information.
- Omit greetings, filler, repetition, and completed small talk.
- Preserve exact names, codes, and important values verbatim.
- Keep the result under 140 words.
- Return only the summary text.
- Do not add a heading, bullets, JSON, or markdown fences.
""".strip()


def _format_turns(turns):
    lines = []

    for number, turn in enumerate(turns, start=1):
        lines.append(f"Turn {number} user: {turn['user']}")
        lines.append(f"Turn {number} assistant: {turn['assistant']}")

    return "\n".join(lines)


def _clean_summary(summary):
    clean_summary = summary.strip()

    if clean_summary.startswith("```"):
        clean_summary = clean_summary.strip("`").strip()

    for prefix in (
        "MEMORY SUMMARY:",
        "Memory summary:",
        "SUMMARY:",
        "Summary:",
    ):
        if clean_summary.startswith(prefix):
            clean_summary = clean_summary[len(prefix) :].strip()
            break

    return clean_summary


def consolidate_memory(
    *,
    existing_summary,
    turns,
):
    if not turns:
        return str(existing_summary).strip()

    existing_summary = str(existing_summary).strip()

    user_content = (
        "EXISTING SESSION SUMMARY:\n"
        + (existing_summary or "(none)")
        + "\n\nOLDER TURNS TO MERGE:\n"
        + _format_turns(turns)
    )

    payload = {
        "model": LLM_MODEL,
        "stream": True,
        "messages": [
            {
                "role": "system",
                "content": CONSOLIDATION_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_content,
            },
        ],
        "options": {
            "temperature": 0.1,
            "num_thread": LLM_NUM_THREADS,
            "num_predict": 180,
        },
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    response_parts = []
    final_data = None

    try:
        with urllib.request.urlopen(
            request,
            timeout=OLLAMA_RESPONSE_TIMEOUT,
        ) as response:
            for raw_line in response:
                line = raw_line.decode(
                    "utf-8",
                    errors="replace",
                ).strip()

                if not line:
                    continue

                data = json.loads(line)

                if data.get("error"):
                    raise RuntimeError(f"Ollama returned an error: {data['error']}")

                token = data.get(
                    "message",
                    {},
                ).get(
                    "content",
                    "",
                )

                if token:
                    response_parts.append(token)

                if data.get("done"):
                    final_data = data
                    break

    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
    ) as error:
        raise RuntimeError(f"Memory consolidation request failed: {error}") from error

    if final_data is None:
        raise RuntimeError("Memory consolidation did not complete.")

    summary = _clean_summary("".join(response_parts))

    if not summary:
        raise RuntimeError("Memory consolidation returned an empty summary.")

    if len(summary) > 2000:
        raise RuntimeError("Memory consolidation returned an implausibly long summary.")

    return summary
