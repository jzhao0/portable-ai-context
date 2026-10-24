"""Synthetic checkpoint benchmark: compare the character fast path with full counting.

No private transcripts, network calls or model providers are required.
From repository root:
    PYTHONPATH=src python tools/benchmark_extractive_checkpoint.py
"""
from __future__ import annotations

import argparse
import statistics
import time

from portable_ai_context.checkpoint import build_extractive_checkpoint
from portable_ai_context.compiler import CallableTokenCounter
from portable_ai_context.compiler.budget import CharacterTokenCounter
from portable_ai_context.models import Conversation, Message, SourceInfo


def conversation_fixture(size: int) -> Conversation:
    messages = [
        Message(
            index=i,
            role="user" if i % 2 == 0 else "assistant",
            text=(
                f"Synthetic state message {i}, pending verification of a next step. "
                + "The execution receipt is not a production approval. " * 3
            ),
        )
        for i in range(size)
    ]
    return Conversation(title="Synthetic checkpoint benchmark",
                        source=SourceInfo(kind="synthetic"), messages=messages)


def median_seconds(conversation: Conversation, counter, budget: int, repetitions: int) -> float:
    samples = []
    for _ in range(repetitions):
        start = time.perf_counter()
        build_extractive_checkpoint(
            conversation, budget_tokens=budget, token_counter=counter,
        )
        samples.append(time.perf_counter() - start)
    return statistics.median(samples)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--messages", nargs="+", type=int, default=[100, 300])
    parser.add_argument("--budget", type=int, default=4000)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if any(n < 1 for n in args.messages) or args.repeats < 1:
        parser.error("message counts and repeats must be positive")
    estimator = CharacterTokenCounter()
    reference = CallableTokenCounter(
        fn=estimator.count, name=estimator.name, exact=estimator.exact,
    )
    print("messages,baseline_seconds,optimized_seconds,speedup,output_equal")
    for size in args.messages:
        conversation = conversation_fixture(size)
        old = build_extractive_checkpoint(
            conversation, budget_tokens=args.budget, token_counter=reference,
        )
        new = build_extractive_checkpoint(
            conversation, budget_tokens=args.budget, token_counter=estimator,
        )
        assert old.markdown == new.markdown
        assert old.report.to_dict() == new.report.to_dict()
        baseline = median_seconds(conversation, reference, args.budget, args.repeats)
        optimized = median_seconds(conversation, estimator, args.budget, args.repeats)
        print(f"{size},{baseline:.6f},{optimized:.6f},{baseline / optimized:.2f},true")


if __name__ == "__main__":
    main()
