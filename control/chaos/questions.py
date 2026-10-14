"""Question bank: 300 phrasings built from templates x topics, deterministic for a given seed."""

import itertools

TOPICS = {
    "DSA101": ["arrays", "linked lists", "stacks", "queues", "binary search trees", "heaps",
               "hash tables", "graphs", "sorting", "recursion"],
}

SHORT = [
    "What is a {t}?",
    "How do {t} work?",
    "When should I use {t}?",
    "Why is my {t} code slow?",
    "Can you explain {t} simply?",
    "What is the time complexity of {t}?",
    "How do I debug {t}?",
    "What are common mistakes with {t}?",
    "Give me a hint about {t}.",
    "How are {t} different from arrays?",
    "Where are {t} used in practice?",
    "How do I implement {t} in Python?",
    "What should I revise about {t} before the exam?",
    "Is my understanding of {t} correct?",
    "What is the key idea behind {t}?",
]

LONG_PREFIX = (
    "I'm working through this week's problem set and I've been stuck for a while. "
    "I tried tracing it by hand and re-reading the lecture notes but I still get the wrong "
    "answer on the third test case, and I'm not sure if my approach is even right. "
)
LONG = [
    LONG_PREFIX + "Can you walk me through how {t} behave when the input is empty or very large?",
    LONG_PREFIX + "My solution uses {t} but times out. What part of my reasoning should I question?",
    LONG_PREFIX + "How would an expert decide whether {t} are the right structure here?",
    LONG_PREFIX + "What invariant should I keep in mind while modifying {t} step by step?",
    LONG_PREFIX + "Could you give me a guiding question about {t} instead of the answer?",
]


def bank(course: str = "DSA101", length: str = "short") -> list[tuple[str, str]]:
    """Return [(topic, question)]. 15 short templates x 10 topics x 2 phrasings = 300."""
    topics = TOPICS[course]
    if length == "long":
        return [(t, q.format(t=t)) for q, t in itertools.product(LONG, topics)]
    out = []
    for q, t in itertools.product(SHORT, topics):
        out.append((t, q.format(t=t)))
        out.append((t, q.format(t=t).replace("?", ", please?").replace(".", ", please.")))
    return out
