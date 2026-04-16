#!/usr/bin/env python3
"""wrun test harness: run all parsers against synthetic + real corpora, report."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
WRUN = ["python3", str(HERE.parent / "wrun")]
CORPUS = HERE / "corpus"


@dataclass
class Case:
    name: str
    input_text: str | None = None
    command: list[str] | None = None
    tool_hint: str = ""
    flags: list[str] = field(default_factory=lambda: ["--no-save"])
    expect_contains: list[str] = field(default_factory=list)
    expect_not_contains: list[str] = field(default_factory=list)
    expect_exit: int | None = None
    expect_json_keys: list[str] = field(default_factory=list)
    min_reduction: int | None = None
    check: Any = None


@dataclass
class Outcome:
    case: Case
    exit_code: int
    stdout: str
    stderr: str
    raw_bytes: int
    wrun_bytes: int
    errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors

    @property
    def reduction(self) -> int:
        if self.raw_bytes == 0:
            return 0
        return 100 - int(self.wrun_bytes * 100 / self.raw_bytes)


def run_case(case: Case) -> Outcome:
    raw = case.input_text or ""
    if case.command:
        raw = ""
        try:
            proc = subprocess.run(
                case.command,
                capture_output=True,
                text=True,
                env={**os.environ, "CI": "1"},
            )
            raw = (proc.stdout or "") + (proc.stderr or "")
        except FileNotFoundError:
            pass
        cmd = WRUN + case.flags + case.command
        wrun_proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env={**os.environ, "CI": "1", "WRUN_AUTO": ""},
        )
    else:
        cmd = WRUN + case.flags + ["--stdin"]
        if case.tool_hint:
            cmd += ["--tool", case.tool_hint]
        wrun_proc = subprocess.run(
            cmd,
            input=raw,
            capture_output=True,
            text=True,
            env={**os.environ, "WRUN_AUTO": ""},
        )

    stdout = wrun_proc.stdout or ""
    stderr = wrun_proc.stderr or ""
    out = Outcome(
        case=case,
        exit_code=wrun_proc.returncode,
        stdout=stdout,
        stderr=stderr,
        raw_bytes=len(raw.encode("utf-8")),
        wrun_bytes=len(stdout.encode("utf-8")),
    )

    if case.expect_exit is not None and out.exit_code != case.expect_exit:
        out.errors.append(f"exit_code={out.exit_code} expected {case.expect_exit}")

    for needle in case.expect_contains:
        if needle not in stdout:
            out.errors.append(f"missing: {needle!r}")

    for needle in case.expect_not_contains:
        if needle in stdout:
            out.errors.append(f"unexpected: {needle!r}")

    if case.expect_json_keys:
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as e:
            out.errors.append(f"invalid JSON: {e}")
        else:
            for key in case.expect_json_keys:
                cur: Any = data
                for part in key.split("."):
                    if isinstance(cur, dict) and part in cur:
                        cur = cur[part]
                    else:
                        out.errors.append(f"JSON missing: {key}")
                        break

    if case.min_reduction is not None and out.reduction < case.min_reduction:
        out.errors.append(f"reduction {out.reduction}% < min {case.min_reduction}%")

    if case.check:
        msg = case.check(out)
        if msg:
            out.errors.append(msg)

    return out


def load_corpus(name: str) -> str:
    return (CORPUS / f"{name}.txt").read_text()


CASES: list[Case] = [
    Case(
        name="pytest: 3 failures from corpus",
        input_text=load_corpus("pytest_3fail"),
        tool_hint="pytest",
        expect_contains=[
            "exit:1",
            "pytest",
            "3 failed",
            "8 passed",
            "FAIL tests/test_auth.py:8",
            "FAIL tests/test_db.py:42",
            "FAIL tests/test_api.py:15",
            "test_login",
            "test_query",
            "test_post",
        ],
        expect_not_contains=["PASSED", "test session starts"],
        min_reduction=70,
    ),
    Case(
        name="pytest: all passing synthetic",
        input_text="""============================= test session starts ==============================
platform linux
collecting ... collected 50 items

tests/test_a.py::test_1 PASSED
tests/test_a.py::test_2 PASSED
...
============================== 50 passed in 1.23s ==============================
""",
        tool_hint="pytest",
        expect_contains=["exit:0", "pytest", "50 passed", "1.23s"],
        expect_not_contains=["PASSED", "FAIL"],
    ),
    Case(
        name="pytest: JSON output",
        input_text=load_corpus("pytest_3fail"),
        tool_hint="pytest",
        flags=["--no-save", "--json"],
        expect_json_keys=[
            "tool",
            "exit_code",
            "summary.failed",
            "summary.passed",
            "failures",
        ],
    ),
    Case(
        name="pytest: quiet mode",
        input_text=load_corpus("pytest_3fail"),
        tool_hint="pytest",
        flags=["--no-save", "--quiet"],
        expect_contains=["exit:1", "pytest", "3 failed"],
        expect_not_contains=["FAIL tests/"],
    ),
    Case(
        name="pytest: max-failures=1",
        input_text=load_corpus("pytest_3fail"),
        tool_hint="pytest",
        flags=["--no-save", "--max-failures=1"],
        expect_contains=["FAIL", "+2 more failures"],
    ),
    Case(
        name="vitest: 2 failures",
        input_text=load_corpus("vitest_2fail"),
        tool_hint="vitest",
        expect_contains=["exit:1", "2 failed", "14 passed"],
    ),
    Case(
        name="ruff: classic format 6 errors",
        input_text=load_corpus("ruff_classic"),
        tool_hint="ruff_check",
        expect_contains=[
            "exit:1",
            "ruff",
            "F401",
            "E302",
            "E501",
            "fixable",
        ],
    ),
    Case(
        name="ruff: modern (Rust-style) diagnostics",
        input_text=load_corpus("ruff_modern"),
        tool_hint="ruff_check",
        expect_contains=["F401", "E302"],
    ),
    Case(
        name="tsc: 4 errors across 3 files",
        input_text=load_corpus("tsc_errors"),
        tool_hint="tsc",
        expect_contains=["TS2322", "TS2339", "TS2769", "TS1005"],
    ),
    Case(
        name="generic: error pattern extraction",
        input_text="""Starting build
Compiling foo...
Compiling bar...
ERROR: cannot find module 'missing-dep'
  at require (internal/modules)
Continuing...
Warning: deprecated API used
Build failed with 1 error
""",
        expect_contains=["generic", "ERROR", "Warning", "Build failed"],
    ),
    Case(
        name="edge: empty input (stdin)",
        input_text="",
        expect_contains=["exit:0"],
    ),
    Case(
        name="edge: heavy ANSI codes",
        input_text="\x1b[31mERROR\x1b[0m: \x1b[1mfoo\x1b[0m failed\n",
        expect_contains=["ERROR", "foo failed"],
        expect_not_contains=["\x1b[", "\\x1b"],
    ),
    Case(
        name="edge: OSC 8 hyperlinks",
        input_text=(
            "src/a.py:1:1: F401 [*] `os` imported but unused\n"
            "\x1b]8;;https://docs.astral.sh/ruff/rules/unused-import\x1b\\F401\x1b]8;;\x1b\\ hint\n"
            "Found 1 error.\n"
        ),
        tool_hint="ruff_check",
        expect_contains=["F401"],
        expect_not_contains=["]8;;", "docs.astral.sh"],
    ),
    Case(
        name="edge: unicode + emoji",
        input_text="ERROR 💥: ação failed\n测试 FAILED\n",
        expect_contains=["ERROR", "ação", "测试"],
    ),
    Case(
        name="edge: very long single line",
        input_text="ERROR: " + "x" * 10000 + "\n",
        expect_contains=["ERROR"],
    ),
    Case(
        name="git_status: porcelain via stdin",
        input_text=" M src/a.py\n?? new.py\nA  src/b.py\n",
        tool_hint="git_status",
        expect_contains=["git_status", "src/a.py", "new.py", "src/b.py"],
    ),
    Case(
        name="git_status: conflict markers",
        input_text="UU src/conflict.py\nAA both_added.py\n M normal.py\n",
        tool_hint="git_status",
        expect_contains=["conflict", "UU src/conflict.py", "AA both_added.py"],
    ),
    Case(
        name="git_diff: real diff via stdin",
        input_text="""diff --git a/src/a.py b/src/a.py
index 0000001..0000002 100644
--- a/src/a.py
+++ b/src/a.py
@@ -1,3 +1,3 @@
-old line
+new line
 context
diff --git a/src/b.py b/src/b.py
new file mode 100644
index 0000000..0000003
--- /dev/null
+++ b/src/b.py
@@ -0,0 +1,2 @@
+line1
+line2
""",
        tool_hint="git_diff",
        expect_contains=["git_diff", "2 files", "+3 -1", "A src/b.py", "M src/a.py"],
    ),
    Case(
        name="git_log: graph format via stdin",
        input_text="""* abc1234 feat: add feature
* def5678 fix: bug
|\\
| * eeeaaaa merge branch
* 0123456 initial
""",
        tool_hint="git_log",
        expect_contains=["git_log", "abc1234", "def5678", "0123456"],
    ),
    Case(
        name="grep: multi-file output via stdin",
        input_text="""src/a.py:10:def foo():
src/a.py:20:    foo()
src/b.py:5: foo = 1
""",
        tool_hint="grep",
        expect_contains=["3 matches", "2 files", "src/a.py", "src/b.py"],
    ),
    Case(
        name="grep: no matches",
        input_text="",
        tool_hint="grep",
        expect_contains=["no matches"],
    ),
    Case(
        name="docker_ps: 2 containers via stdin",
        input_text="""CONTAINER ID   IMAGE        COMMAND       CREATED       STATUS         PORTS                                        NAMES
abc123def456   nginx:1.25   "nginx -g"    2 hours ago   Up 2 hours    0.0.0.0:80->80/tcp, [::]:80->80/tcp          web
def789ghi012   postgres:15  "postgres"    1 day ago     Up 1 day      0.0.0.0:5432->5432/tcp, [::]:5432->5432/tcp  db
""",
        tool_hint="docker_ps",
        expect_contains=[
            "docker_ps",
            "2 running",
            "abc123def456",
            "web",
            ":80",
            ":5432",
        ],
        expect_not_contains=["[::]"],
    ),
    Case(
        name="docker_ps: empty (only header)",
        input_text="CONTAINER ID   IMAGE   COMMAND   CREATED   STATUS   PORTS   NAMES\n",
        tool_hint="docker_ps",
        expect_contains=["docker_ps"],
    ),
    Case(
        name="ls_tree: ls -la with noise",
        input_text="""total 40
drwxr-xr-x  8 u u  4096 Apr 16 12:00 .
drwxr-xr-x  3 u u  4096 Apr 16 12:00 ..
drwxr-xr-x  9 u u  4096 Apr 16 12:00 .git
drwxr-xr-x  2 u u  4096 Apr 16 12:00 node_modules
-rw-r--r--  1 u u   100 Apr 16 12:00 README.md
drwxr-xr-x  5 u u  4096 Apr 16 12:00 src
""",
        tool_hint="ls_tree",
        expect_contains=["noise hidden", "README.md", "src"],
        expect_not_contains=["node_modules", ".git", "4096 ."],
    ),
    Case(
        name="ls_tree: tree with deep noise",
        input_text=""".
├── node_modules
│   ├── a
│   │   └── x.js
│   └── b.js
├── src
│   ├── api.py
│   └── db.py
└── README.md

4 directories, 5 files
""",
        tool_hint="ls_tree",
        expect_contains=["tree", "src", "README.md", "api.py"],
        expect_not_contains=["node_modules", "x.js", "4 directories"],
    ),
    Case(
        name="flag: --full bypasses parsing",
        command=["echo", "-e", "line1\nline2\nline3"],
        flags=["--no-save", "--full"],
        expect_contains=["line1", "line2", "line3"],
        expect_not_contains=["exit:", "|"],
    ),
    Case(
        name="flag: --stdin with piped pytest",
        input_text="= 1 passed in 0.1s =",
        tool_hint="pytest",
        expect_contains=["pytest", "1 passed"],
    ),
    Case(
        name="real: command not found",
        command=["__this_command_does_not_exist__"],
        expect_exit=127,
    ),
    Case(
        name="real: git status in wrun-repo",
        command=["git", "status", "-sb"],
        check=lambda o: None
        if o.exit_code in (0, 128)
        else f"unexpected exit {o.exit_code}",
    ),
    Case(
        name="real: pytest summary synthesis",
        command=["sh", "-c", "echo '1 passed in 0.01s'"],
        check=lambda o: None if "exit:" in o.stdout else "no exit line",
    ),
    Case(
        name="real: grep self",
        command=["grep", "-Hn", "def ", str(HERE.parent / "wrun")],
        expect_contains=["wrun", "def "],
    ),
]


def main() -> int:
    print("━" * 90)
    print(f"wrun harness — {len(CASES)} cases")
    print("━" * 90)
    passed = failed = 0
    sum_raw = sum_wrun = 0
    failing: list[Outcome] = []

    for case in CASES:
        out = run_case(case)
        sum_raw += out.raw_bytes
        sum_wrun += out.wrun_bytes
        if out.passed:
            passed += 1
            status = "PASS"
        else:
            failed += 1
            failing.append(out)
            status = "FAIL"
        reduction = f"{out.reduction:+d}%" if out.raw_bytes > 0 else "   -"
        print(
            f"  [{status}] {out.raw_bytes:>6}B→{out.wrun_bytes:>4}B {reduction:>5} | {case.name}"
        )

    print("━" * 90)
    print(f"Total: {len(CASES)} | PASS: {passed} | FAIL: {failed}")
    if sum_raw > 0:
        overall = 100 - int(sum_wrun * 100 / sum_raw)
        print(f"Aggregated: {sum_raw:,}B → {sum_wrun:,}B ({overall:+d}%)")

    if failing:
        print()
        print("━" * 90)
        print(f"FAILING CASES DETAILS ({len(failing)})")
        print("━" * 90)
        for out in failing:
            print(f"\n■ {out.case.name}")
            print(f"  exit: {out.exit_code}")
            print(f"  errors: {out.errors}")
            print(f"  stdout ({out.wrun_bytes}B):")
            for line in out.stdout.splitlines()[:10]:
                print(f"    | {line}")
            if out.stderr:
                print(f"  stderr:")
                for line in out.stderr.splitlines()[:3]:
                    print(f"    ! {line}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
