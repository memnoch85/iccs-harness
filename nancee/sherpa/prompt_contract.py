from __future__ import annotations

from copy import deepcopy


def build_prompt_prefix(
    *,
    system_prompt: str,
    history=None,
    memory_context: str = "",
) -> list[dict[str, str]]:
    """Build the canonical application-level prefix exactly once.

    This function is deliberately free of Ollama I/O. Startup warmup, ICCS
    priming, fingerprinting, and real requests must all use this builder so
    prompt shape cannot drift between paths.
    """
    messages = [
        {
            "role": "system",
            "content": str(system_prompt).strip(),
        }
    ]

    clean_memory_context = str(memory_context).strip()

    if clean_memory_context:
        messages.append(
            {
                "role": "system",
                "content": clean_memory_context,
            }
        )

    messages.extend(
        deepcopy(
            list(history or [])
        )
    )

    return messages


def build_prompt_messages_from_prefix(
    *,
    prefix_messages,
    user_text: str,
    retrieved_context: str = "",
    response_instruction: str = "",
) -> list[dict[str, str]]:
    """Append turn-specific material without mutating the prepared prefix."""
    messages = deepcopy(
        list(prefix_messages or [])
    )

    clean_retrieved_context = str(retrieved_context).strip()

    if clean_retrieved_context:
        messages.append(
            {
                "role": "system",
                "content": (
                    "Use the relevant user memory below to answer the user's question. "
                    "In memory lines, I, me, and my refer to the human user, not Nancee. "
                    "Do not guess.\n\n"
                    f"{clean_retrieved_context}"
                ),
            }
        )

    clean_response_instruction = str(response_instruction).strip()
    clean_user_text = str(user_text).strip()

    if clean_response_instruction:
        clean_user_text = (
            "TURN RESPONSE CONSTRAINT:\n"
            f"{clean_response_instruction}\n\n"
            "USER MESSAGE:\n"
            f"{clean_user_text}"
        )

    messages.append(
        {
            "role": "user",
            "content": clean_user_text,
        }
    )

    return messages
