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
            "✗pytest",
            "3F/11",
            "✗test_login@8",
            "✗test_query@42",
            "✗test_post@15",
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
        expect_contains=["✓pytest", "50p", "1.23s"],
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
        expect_contains=["✗pytest", "3F/11"],
        expect_not_contains=["FAIL tests/"],
    ),
    Case(
        name="pytest: max-failures=1",
        input_text=load_corpus("pytest_3fail"),
        tool_hint="pytest",
        flags=["--no-save", "--max-failures=1"],
        expect_contains=["✗test_login", "+2"],
    ),
    Case(
        name="vitest: 2 failures",
        input_text=load_corpus("vitest_2fail"),
        tool_hint="vitest",
        expect_contains=["✗vitest", "2F/16"],
    ),
    Case(
        name="ruff: classic format 6 errors",
        input_text=load_corpus("ruff_classic"),
        tool_hint="ruff_check",
        expect_contains=[
            "✗ruff",
            "F401",
            "E302",
            "E501",
            "fix",
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
        name="biome: pretty reporter 3 errors",
        input_text=load_corpus("biome_errors"),
        tool_hint="biome",
        expect_contains=[
            "✗biome",
            "3e",
            "3f",
            "10ms",
            "lint/suspicious/noExplicitAny",
            "lint/style/useConst",
            "lint/correctness/noUnusedVariables",
            "App.tsx:12",
            "utils.ts:8",
            "client.ts:45",
            "Unexpected any",
            "never reassigned",
            "variable is unused",
        ],
        expect_not_contains=["━━━", ":12:5:0", "failed"],
    ),
    Case(
        name="biome: github actions reporter",
        input_text=(
            "::error file=./src/App.tsx,line=12,col=5,title=lint/suspicious/noExplicitAny"
            "::Unexpected any. Specify a different type.\n"
            "::error file=./src/utils.ts,line=8,col=1,title=lint/style/useConst"
            "::let declares a variable that is never reassigned.\n"
            "Found 2 errors.\n"
        ),
        tool_hint="biome",
        expect_contains=[
            "✗biome",
            "2e",
            "lint/suspicious/noExplicitAny",
            "lint/style/useConst",
            "App.tsx:12",
            "utils.ts:8",
        ],
    ),
    Case(
        name="biome: summary reporter (one-line diagnostics)",
        input_text=(
            "./src/foo.ts:3:10 lint/style/useConst  × let is never reassigned.\n"
            "./src/bar.ts:1:1 lint/suspicious/noExplicitAny  × Unexpected any.\n"
            "Found 2 errors.\n"
        ),
        tool_hint="biome",
        expect_contains=[
            "✗biome",
            "2e",
            "foo.ts:3",
            "bar.ts:1",
            "let is never reassigned",
            "Unexpected any",
        ],
    ),
    Case(
        name="biome: clean run (0 errors, only Checked line)",
        input_text=load_corpus("biome_clean"),
        tool_hint="biome",
        expect_contains=["✓biome", "clean", "12f", "8ms"],
        expect_not_contains=[" error", " warning", "FAIL", "lint/"],
    ),
    Case(
        name="biome: warnings-only run",
        input_text=load_corpus("biome_warnings"),
        tool_hint="biome",
        expect_contains=[
            "✗biome",
            "2w",
            "2f",
            "5ms",
            "lint/style/useConst",
            "lint/correctness/noUnusedVariables",
            "[w]",
            "never reassigned",
            "variable is unused",
        ],
        expect_not_contains=[" error"],
    ),
    Case(
        name="biome: mixed errors + warnings + fixable",
        input_text=load_corpus("biome_mixed"),
        tool_hint="biome",
        expect_contains=[
            "✗biome",
            "2e",
            "1w",
            "3f",
            "15ms",
            "Unexpected any",
            "never reassigned",
            "variable is unused",
            "1fix",
            "[w]",
        ],
    ),
    Case(
        name="biome: parse category (syntax error)",
        input_text=load_corpus("biome_parse"),
        tool_hint="biome",
        expect_contains=[
            "✗biome",
            "1e",
            "parse",
            "broken.ts:5",
            "Expected a semicolon",
        ],
    ),
    Case(
        name="biome: format category (whole-file diagnostic)",
        input_text=load_corpus("biome_format"),
        tool_hint="biome",
        expect_contains=[
            "✗biome",
            "2e",
            "format×2",
            "foo.ts",
            "2fix",
        ],
    ),
    Case(
        name="biome: many diagnostics + max-failures cap",
        input_text=load_corpus("biome_many"),
        tool_hint="biome",
        flags=["--no-save", "--max-failures", "3"],
        expect_contains=[
            "✗biome",
            "8e",
            "7w",
            "42ms",
            "+4",
            "8fix",
        ],
    ),
    Case(
        name="biome: JSON reporter (--reporter=json)",
        input_text=load_corpus("biome_json"),
        tool_hint="biome",
        expect_contains=[
            "✗biome",
            "2e",
            "1w",
            "lint/suspicious/noExplicitAny",
            "App.tsx",
            "utils.ts",
            "[w]",
        ],
    ),
    Case(
        name="biome: summary reporter aggregated",
        input_text=load_corpus("biome_summary"),
        tool_hint="biome",
        expect_contains=["✗biome", "4e", "2w", "5f", "22ms"],
    ),
    Case(
        name="biome: fixable FIXABLE flag + Fixed count",
        input_text=load_corpus("biome_fixable"),
        tool_hint="biome",
        expect_contains=[
            "✗biome",
            "1e",
            "1w",
            "2f",
            "1fix",
            "lint/suspicious/noDebugger",
            "lint/style/useConst",
        ],
    ),
    Case(
        name="biome: quiet mode yields 1 line",
        input_text=load_corpus("biome_mixed"),
        tool_hint="biome",
        flags=["--no-save", "--quiet"],
        check=lambda o: None
        if o.stdout.count("\n") == 1
        else f"got {o.stdout.count(chr(10))} lines",
    ),
    Case(
        name="biome: --json emits biome_* extras",
        input_text=load_corpus("biome_mixed"),
        tool_hint="biome",
        flags=["--no-save", "--json"],
        expect_json_keys=[
            "biome_warnings",
            "biome_checked",
            "biome_fixable",
            "biome_reporter",
            "lint_issues_grouped",
        ],
    ),
    Case(
        name="biome: JSON reporter JSON passthrough",
        input_text=load_corpus("biome_json"),
        tool_hint="biome",
        flags=["--no-save", "--json"],
        expect_json_keys=["summary.errors", "biome_warnings", "biome_reporter"],
    ),
    Case(
        name="biome REAL 2.x: pretty single-file (3 err + 3 warn)",
        input_text=load_corpus("biome_real_single"),
        tool_hint="biome",
        expect_contains=[
            "✗biome",
            "3e",
            "3w",
            "1f",
            "3ms",
            "lint/suspicious/noExplicitAny",
            "lint/suspicious/noDebugger",
            "lint/correctness/noUnusedVariables",
            "lint/style/useConst",
            "[w]",
            "app.ts:1",
            "app.ts:2",
            "Unexpected any",
            "debugger statement",
            "fix",
        ],
        expect_not_contains=["━━━", "check ━", "failed"],
    ),
    Case(
        name="biome REAL 2.x: pretty multi-file (15 diagnostics)",
        input_text=load_corpus("biome_real_pretty"),
        tool_hint="biome",
        expect_contains=[
            "✗biome",
            "9e",
            "6w",
            "6f",
            "format×6",
            "lint/correctness/noUnusedVariables×4[w]",
            "assist/source/organizeImports",
            "6fix",
        ],
    ),
    Case(
        name="biome REAL 2.x: github reporter (title first)",
        input_text=load_corpus("biome_real_github"),
        tool_hint="biome",
        expect_contains=[
            "✗biome",
            "9e",
            "6w",
            "lint/suspicious/noExplicitAny",
            "assist/source/organizeImports",
            "format×6",
            "app.ts:1",
            "[w]",
        ],
    ),
    Case(
        name="biome REAL 2.x: summary reporter (aggregated)",
        input_text=load_corpus("biome_real_summary"),
        tool_hint="biome",
        expect_contains=[
            "✗biome",
            "9e",
            "6w",
            "6f",
            "2ms",
        ],
    ),
    Case(
        name="biome REAL 2.x: JSON reporter (nanoseconds duration)",
        input_text=load_corpus("biome_real_json"),
        tool_hint="biome",
        expect_contains=[
            "✗biome",
            "9e",
            "6w",
            "6f",
            "lint/suspicious/noExplicitAny",
            "lint/suspicious/noDebugger",
            "assist/source/organizeImports",
            "app.ts:1",
        ],
        expect_not_contains=["1.99s", "1990067"],
    ),
    Case(
        name="biome REAL 2.x: format-only (biome format command)",
        input_text=load_corpus("biome_real_format"),
        tool_hint="biome",
        expect_contains=[
            "✗biome",
            "1e",
            "format",
            "bad-format.ts",
        ],
        expect_not_contains=["lint/"],
    ),
    Case(
        name="biome REAL 2.x: assist/organizeImports category",
        input_text=load_corpus("biome_real_assist"),
        tool_hint="biome",
        expect_contains=[
            "✗biome",
            "2e",
            "assist/source/organizeImports",
            "utils.ts:6",
            "imports and exports are not sorted",
        ],
    ),
    Case(
        name="biome REAL 2.x: JSON via --json flag produces biome_* extras",
        input_text=load_corpus("biome_real_json"),
        tool_hint="biome",
        flags=["--no-save", "--json"],
        expect_json_keys=[
            "summary.errors",
            "biome_warnings",
            "biome_checked",
            "biome_reporter",
            "lint_issues_grouped",
        ],
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
        expect_contains=["✓git_diff", "2f", "+3 -1", "A src/b.py", "M src/a.py"],
    ),
    Case(
        name="git_diff: --name-only (bare paths, most common AI workflow)",
        input_text=(
            "api/app/api/routes/admin.py\n"
            "api/app/repositories/roles.py\n"
            "api/tests/test_admin_dashboard_stats.py\n"
            "front/src/pages/admin/DashboardPage.tsx\n"
        ),
        tool_hint="git_diff",
        expect_contains=[
            "exit:0",
            "api/app/api/routes/admin.py",
            "api/app/repositories/roles.py",
            "api/tests/test_admin_dashboard_stats.py",
            "front/src/pages/admin/DashboardPage.tsx",
        ],
        expect_not_contains=["no changes", "M api/app", "M front/", "4 files"],
    ),
    Case(
        name="git_diff: --name-status (status+path tab-separated)",
        input_text=(
            "M\tsrc/api/client.ts\n"
            "A\tsrc/new_feature.py\n"
            "D\tsrc/removed.py\n"
            "R100\tsrc/old.py\tsrc/renamed.py\n"
        ),
        tool_hint="git_diff",
        expect_contains=[
            "✓git_diff",
            "4f",
            "M src/api/client.ts",
            "A src/new_feature.py",
            "D src/removed.py",
            "R src/renamed.py",
        ],
        expect_not_contains=["no changes", "src/old.py"],
    ),
    Case(
        name="git_diff: --numstat (add/del/path tab-separated + binary marker)",
        input_text=(
            "5\t3\tsrc/api/client.ts\n0\t10\tsrc/removed.py\n-\t-\tdocs/logo.png\n"
        ),
        tool_hint="git_diff",
        expect_contains=[
            "✓git_diff",
            "3f",
            "+5 -13",
            "src/api/client.ts +5 -3",
            "src/removed.py +0 -10",
            "docs/logo.png",
        ],
        expect_not_contains=["no changes"],
    ),
    Case(
        name="git_diff: empty output stays 'no changes' (clean worktree)",
        input_text="",
        tool_hint="git_diff",
        expect_contains=["git_diff", "no changes"],
        expect_not_contains=["1 files", "M "],
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
            "✓docker_ps",
            "2↑",
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
        name="docker_ps: Paused and Removing states counted as stopped",
        input_text="""CONTAINER ID   IMAGE        COMMAND       CREATED       STATUS                  PORTS    NAMES
abc123def456   nginx:1.25   "nginx -g"    2 hours ago   Up 2 hours (healthy)             web
def789ghi012   postgres:15  "postgres"    1 day ago     Paused                           db
xyz345lmn678   redis:7      "redis"       3 hours ago   Removing                         cache
""",
        tool_hint="docker_ps",
        check=lambda o: (
            "missing stopped count"
            if "2↓" not in o.stdout and "1↑" not in o.stdout
            else None
        ),
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
        expect_contains=["✓ls", "README.md", "src"],
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
        expect_contains=["pytest", "1p"],
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
        check=lambda o: None if o.stdout.strip() else "empty output",
    ),
    Case(
        name="real: grep self",
        command=["grep", "-Hn", "def ", str(HERE.parent / "wrun")],
        expect_contains=["wrun", "def "],
    ),
    Case(
        name="docker_logs: error surfacing + tail",
        input_text="""2024-01-15T10:00:00.000Z Starting server
2024-01-15T10:00:01.000Z Listening on :8080
2024-01-15T10:00:02.000Z Error: connection refused to redis:6379
2024-01-15T10:00:03.000Z Retrying...
2024-01-15T10:00:04.000Z Fatal: cannot connect to database
""",
        tool_hint="docker_logs",
        expect_contains=["docker_logs", "err 2:", "connection refused", "Fatal"],
        expect_not_contains=["2024-01-15T10:00:00"],
    ),
    Case(
        name="docker_logs: detection via docker logs command",
        command=["sh", "-c", "echo '2024-01-01T00:00:00Z app started'"],
        flags=["--no-save"],
        check=lambda o: None if o.stdout.strip() else "empty output",
    ),
    Case(
        name="make: error extraction",
        input_text="""make[1]: Entering directory '/app'
gcc -o main main.c
main.c:42:5: error: 'foo' undeclared (first use in this function)
main.c:43:3: warning: implicit declaration of function 'bar'
make[1]: *** [main] Error 1
make[1]: Leaving directory '/app'
""",
        tool_hint="make",
        expect_contains=["make", "1e", "1w", "ERR", "undeclared"],
        expect_not_contains=["gcc -o main"],
    ),
    Case(
        name="make: clean build",
        input_text="""make[1]: Entering directory '/app'
gcc -O2 -o main main.c
make[1]: Leaving directory '/app'
""",
        tool_hint="make",
        expect_contains=["make", "0e"],
    ),
    Case(
        name="cargo: error with location",
        input_text="""error[E0308]: mismatched types
  --> src/main.rs:10:5
   |
10 |     let x: i32 = "hello";
   |                  ^^^^^^^ expected `i32`, found `&str`

warning[W0001]: unused variable `y`
  --> src/main.rs:15:9

error: aborting due to 1 previous error
""",
        tool_hint="cargo",
        expect_contains=[
            "cargo",
            "2e",
            "E0308",
            "mismatched types",
            "src/main.rs:10",
        ],
    ),
    Case(
        name="cargo: clean build",
        input_text="warning[unused]: unused import `std::fmt`\n  --> src/lib.rs:1:5\n\nFinished dev [unoptimized] target(s)\n",
        tool_hint="cargo",
        expect_contains=["cargo", "0e", "1w"],
        expect_not_contains=["ERR"],
    ),
    Case(
        name="kubectl: table mode",
        input_text="""NAME         READY   STATUS    RESTARTS   AGE
nginx-pod    1/1     Running   0          2d
broken-pod   0/1     Error     5          1h
""",
        tool_hint="kubectl",
        expect_contains=["kubectl", "table", "nginx-pod", "broken-pod"],
    ),
    Case(
        name="kubectl: apply mode",
        input_text="""deployment.apps/nginx configured
service/nginx-svc unchanged
configmap/app-config created
""",
        tool_hint="kubectl",
        expect_contains=["kubectl", "apply", "configured", "created"],
    ),
    Case(
        name="generic: summarize fallback for large benign output",
        input_text="\n".join([f"Downloading package-{i}" for i in range(600)]),
        tool_hint="generic",
        expect_contains=["exit:0", "lines hidden"],
        expect_not_contains=["Downloading package-100", "Downloading package-300"],
    ),
    Case(
        name="detect_tool: make -> make parser",
        command=["sh", "-c", "echo 'make[1]: Nothing to be done'"],
        flags=["--no-save"],
        check=lambda o: None if "make" in o.stdout else "no make in output",
    ),
    Case(
        name="docker_logs: quiet returns 1 line",
        input_text="2024-01-01T00:00:00Z ERROR: crashed\n",
        tool_hint="docker_logs",
        flags=["--no-save", "--quiet"],
        check=lambda o: None
        if o.stdout.count("\n") == 1
        else f"got {o.stdout.count(chr(10))} lines",
    ),
    Case(
        name="make: quiet returns 1 line",
        input_text="main.c:5:3: error: X\n",
        tool_hint="make",
        flags=["--no-save", "--quiet"],
        check=lambda o: None
        if o.stdout.count("\n") == 1
        else f"got {o.stdout.count(chr(10))} lines",
    ),
    Case(
        name="cargo: quiet returns 1 line",
        input_text="error[E0308]: mismatched\n  --> a.rs:1:1\n",
        tool_hint="cargo",
        flags=["--no-save", "--quiet"],
        check=lambda o: None
        if o.stdout.count("\n") == 1
        else f"got {o.stdout.count(chr(10))} lines",
    ),
    Case(
        name="kubectl: quiet returns 1 line",
        input_text="NAME   STATUS\nnginx  Running\n",
        tool_hint="kubectl",
        flags=["--no-save", "--quiet"],
        check=lambda o: None
        if o.stdout.count("\n") == 1
        else f"got {o.stdout.count(chr(10))} lines",
    ),
    Case(
        name="make: --max-failures respected with '+N more'",
        input_text="\n".join([f"main.c:{i}:1: error: bug-{i}" for i in range(1, 21)]),
        tool_hint="make",
        flags=["--no-save", "--max-failures", "3"],
        expect_contains=["20e", "bug-1", "bug-2", "bug-3", "+17"],
        expect_not_contains=["bug-10", "bug-20"],
    ),
    Case(
        name="cargo: --max-failures with '+N more'",
        input_text="\n".join([f"error[E00{i}]: bug-{i}" for i in range(1, 8)]),
        tool_hint="cargo",
        flags=["--no-save", "--max-failures", "2"],
        expect_contains=["7e", "+5"],
    ),
    Case(
        name="cargo: test panic detected",
        input_text="test panics ... FAILED\nthread 'panics' panicked at 'boom', src/lib.rs:10:9\n",
        tool_hint="cargo",
        expect_contains=["2e", "TEST", "PANIC", "src/lib.rs:10"],
    ),
    Case(
        name="make: unicode prefix before error",
        input_text="🚀 error: malformed\n",
        tool_hint="make",
        expect_contains=["make", "1e", "malformed"],
    ),
    Case(
        name="make: ninja target detection",
        input_text="ninja: Entering directory `build`\nninja: error: loading 'build.ninja'\n",
        tool_hint="make",
        expect_contains=["make", "1e"],
    ),
    Case(
        name="json: cargo extras in JSON",
        input_text="error[E0308]: mismatched types\n  --> src/main.rs:1:1\n",
        tool_hint="cargo",
        flags=["--no-save", "--json"],
        expect_json_keys=["cargo_errors", "cargo_warnings", "cargo_total_lines"],
    ),
    Case(
        name="json: docker_logs extras in JSON",
        input_text="2024-01-01T00:00:00Z ERROR: boom\n",
        tool_hint="docker_logs",
        flags=["--no-save", "--json"],
        expect_json_keys=[
            "docker_logs_errors",
            "docker_logs_tail",
            "docker_logs_total",
        ],
    ),
    Case(
        name="perf: 1MB single line does not hang",
        input_text="x" * 1_000_000,
        tool_hint="generic",
        check=lambda o: None if o.exit_code == 0 else f"exit {o.exit_code}",
    ),
]


def _regression_sigpipe_no_traceback() -> tuple[bool, str]:
    """wrun cmd | head must not leak BrokenPipeError tracebacks to stderr."""
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        # 3000 lines to guarantee we exceed any pipe buffer
        for i in range(3000):
            f.write(f"line {i} with some padding content to fill buffer\n")
        big_path = f.name

    try:
        # Spawn wrun producing full output, read 1 byte then close — forces
        # downstream write failures on every subsequent chunk.
        proc = subprocess.Popen(
            WRUN + ["--no-save", "--full", "cat", big_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "WRUN_AUTO": ""},
        )
        assert proc.stdout is not None
        assert proc.stderr is not None
        proc.stdout.read(1)
        proc.stdout.close()
        stderr = proc.stderr.read().decode()
        exit_code = proc.wait()
    finally:
        Path(big_path).unlink(missing_ok=True)

    if "Traceback" in stderr or "BrokenPipeError" in stderr:
        return False, f"leaked traceback to stderr: {stderr[:200]!r}"
    # 0 = clean exit, 141 = 128+SIGPIPE (shell convention),
    # -13 = subprocess negative-signal convention (died from SIGPIPE)
    if exit_code not in (0, 141, -13):
        return False, f"unexpected exit_code={exit_code}"
    return True, ""


def _regression_no_dedup() -> tuple[bool, str]:
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("stable content for dedup regression\n")
        tmp_path = f.name

    cache = Path.home() / ".local" / "share" / "wrun" / "session_cache.json"
    cache.unlink(missing_ok=True)

    try:
        cmd = WRUN + ["cat", tmp_path]
        env = {**os.environ, "WRUN_AUTO": ""}
        r1 = subprocess.run(cmd, capture_output=True, text=True, env=env)
        r2 = subprocess.run(cmd, capture_output=True, text=True, env=env)
        r3 = subprocess.run(cmd, capture_output=True, text=True, env=env)

        for i, r in enumerate((r1, r2, r3), 1):
            if "duplicate" in r.stdout.lower():
                return False, f"call #{i} returned '(duplicate)' marker: {r.stdout!r}"
            if r.returncode != 0:
                return (
                    False,
                    f"call #{i} failed: exit={r.returncode}, stdout={r.stdout!r}",
                )

        if not (r1.stdout == r2.stdout == r3.stdout):
            return False, "repeated calls produced different output"

        if cache.exists():
            return False, f"cache file recreated at {cache}"

        return True, "3 identical calls, no '(duplicate)' marker, no cache file"
    finally:
        os.unlink(tmp_path)


def main() -> int:
    print("━" * 90)
    print(f"wrun harness — {len(CASES)} cases + 1 regression")
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

    ok, msg = _regression_no_dedup()
    status = "PASS" if ok else "FAIL"
    if ok:
        passed += 1
    else:
        failed += 1
    print(f"  [{status}]   regression   | no-dedup: {msg}")

    ok, msg = _regression_sigpipe_no_traceback()
    status = "PASS" if ok else "FAIL"
    if ok:
        passed += 1
    else:
        failed += 1
    print(
        f"  [{status}]   regression   | sigpipe: downstream close leaks no traceback {msg}"
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
