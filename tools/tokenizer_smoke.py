from __future__ import annotations

import importlib.metadata
import json

import tiktoken

from portable_ai_context.compiler import TiktokenTokenCounter


def main() -> int:
    sample = "<|im_start|> Portable AI Context 你好"

    direct_encoding = tiktoken.get_encoding("o200k_base")
    explicit = TiktokenTokenCounter(encoding_name="o200k_base")
    expected = len(direct_encoding.encode_ordinary(sample))
    actual = explicit.count(sample)
    if actual != expected:
        raise SystemExit(
            f"tiktoken explicit-encoding count mismatch: actual={actual} expected={expected}"
        )
    if explicit.name != "tiktoken:o200k_base" or not explicit.exact:
        raise SystemExit("tiktoken explicit counter metadata is invalid")

    model_counter = TiktokenTokenCounter(model="gpt-5")
    if not model_counter.name.startswith("tiktoken:") or not model_counter.exact:
        raise SystemExit("tiktoken model counter metadata is invalid")
    if model_counter.count(sample) <= 0:
        raise SystemExit("tiktoken model counter returned a non-positive count")

    print(
        json.dumps(
            {
                "ok": True,
                "tiktoken_version": importlib.metadata.version("tiktoken"),
                "explicit_counter": explicit.name,
                "model_counter": model_counter.name,
                "sample_tokens": actual,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
