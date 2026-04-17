#!/usr/bin/env python3
"""Render a reduction table annotated with tiktoken (cl100k_base) token counts.

Reuses the harness CASES list, runs each case, and reports bytes + tokens
(raw vs wrun) plus per-case deltas. `cl100k_base` is GPT-4's encoding — a
widely-used proxy for token accounting across modern LLMs (Claude, Gemini,
etc. use similar BPE granularities, so absolute numbers are approximate but
the deltas between raw/wrun are robust).
"""

from __future__ import annotations

import sys
from pathlib import Path

import tiktoken

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import CASES, run_case  # type: ignore

ENCODING = tiktoken.get_encoding("cl100k_base")


def tokens(text: str) -> int:
    return len(ENCODING.encode(text))


def main() -> int:
    print("━" * 110)
    print(
        f"{'CASE':<52} {'RAW BYTES':>10} {'WRUN BYTES':>10} {'RAW TOK':>8} {'WRUN TOK':>8} {'Δ TOK':>7}"
    )
    print("━" * 110)

    sum_raw_b = sum_wrun_b = sum_raw_t = sum_wrun_t = 0

    for case in CASES:
        out = run_case(case)
        raw_text = case.input_text or ""
        if case.command:
            raw_text = out.stderr + out.stdout
        raw_t = tokens(raw_text)
        wrun_t = tokens(out.stdout)
        sum_raw_b += out.raw_bytes
        sum_wrun_b += out.wrun_bytes
        sum_raw_t += raw_t
        sum_wrun_t += wrun_t

        if raw_t > 0:
            delta = f"{100 - int(wrun_t * 100 / raw_t):+d}%"
        else:
            delta = "   -"

        name = case.name if len(case.name) <= 50 else case.name[:47] + "..."
        print(
            f"{name:<52} {out.raw_bytes:>10} {out.wrun_bytes:>10} {raw_t:>8} {wrun_t:>8} {delta:>7}"
        )

    print("━" * 110)
    pct_b = 100 - int(sum_wrun_b * 100 / sum_raw_b) if sum_raw_b else 0
    pct_t = 100 - int(sum_wrun_t * 100 / sum_raw_t) if sum_raw_t else 0
    print(
        f"{'AGGREGATED':<52} {sum_raw_b:>10} {sum_wrun_b:>10} {sum_raw_t:>8} {sum_wrun_t:>8} "
        f"bytes={pct_b:+d}%  tokens={pct_t:+d}%"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
