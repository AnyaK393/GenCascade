"""Queueing simulator used when LLM_BACKEND=mock. It sleeps as long as the real model would
(prompt_tokens * 0.002 + output_tokens / per-request rate) and returns Ollama-shaped fields, so the
llm_inference service's semaphore and metrics behave the same.

Calibration (docs/calibration.md) showed the M1 delivers a fixed aggregate rate (~41 tok/s) no
matter how many requests run at once, so the per-request rate is that total divided by the
number of active generations."""

import asyncio
import random

REPLIES = [
    "Good question. What do you already know about how this structure stores its items? "
    "Hint: start from the definition and check what must stay true after every operation.",
    "Let's slow down. Can you trace the first two steps on a tiny example? "
    "Hint: draw it with three elements before generalising.",
    "Think about the worst case. Which input would make this slowest? "
    "Hint: consider what happens when the input is already sorted.",
]
active = {"n": 0}


def count_tokens(text: str) -> int:
    return int(len(text.split()) * 1.3) + 1


async def generate(prompt: str, max_tokens: int, tokens_per_s: float) -> dict:
    """tokens_per_s is the aggregate rate shared by all active generations."""
    prompt_tokens = count_tokens(prompt)
    target = random.randint(max(1, int(0.6 * max_tokens)), max_tokens)
    active["n"] += 1
    try:
        await asyncio.sleep(prompt_tokens * 0.002)
        produced, gen_s, step = 0.0, 0.0, 0.1
        while produced < target:
            await asyncio.sleep(step)
            gen_s += step
            produced += tokens_per_s / active["n"] * step
    finally:
        active["n"] -= 1
    return {"response": random.choice(REPLIES), "eval_count": target,
            "eval_duration": int(gen_s * 1e9), "prompt_eval_count": prompt_tokens}
