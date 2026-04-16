# wrun

Token-optimized command wrapper for AI coding agents. Wraps test runners, linters, and type checkers to produce minimal, actionable output — reducing token consumption by 77-90%.

## Problem

AI coding agents (Claude Code, OpenCode, Cursor, etc.) waste context window on verbose test/lint output:

```
============================= test session starts ==============================
platform linux -- Python 3.12.12, pytest-9.0.2, pluggy-1.6.0
rootdir: /home/user/project
plugins: anyio-4.12.1, cov-7.0.0
collecting ... collected 5 items

tests/test_auth.py::test_ok PASSED                              [ 20%]
tests/test_auth.py::test_ok2 PASSED                             [ 40%]
tests/test_auth.py::test_fail FAILED                            [ 60%]
... (30+ more lines of decorative output, stack traces, framework internals)
```

## Solution

wrun produces exactly what the AI needs to act:

```
exit:1 | pytest | 2 passed, 1 failed | 0.2s
FAIL tests/test_auth.py:8 :: test_fail — AssertionError: Expected 200, got 401 | assert 401 == 200
full: ~/.local/share/wrun/20260416-084655-pytest.log
```

Passing runs = 1 line:
```
exit:0 | pytest | 5 passed | 0.3s
```

## Install

```bash
git clone https://github.com/RobertWsp/wrun.git
cd wrun
./install.sh
```

### Shell integration (auto-wrap)

Add to `~/.zshenv` for automatic activation in AI agent sessions:

```zsh
if [[ ! -o interactive ]]; then
    export WRUN_AUTO=1
    [[ -f ~/.local/share/wrun/integration.zsh ]] && source ~/.local/share/wrun/integration.zsh
fi
```

For interactive shells, add to `~/.zshrc`:

```zsh
[[ -f ~/.local/share/wrun/integration.zsh ]] && source ~/.local/share/wrun/integration.zsh
# export WRUN_AUTO=1  # uncomment to enable in terminal too
```

## Usage

### Manual

```bash
wrun uv run pytest tests/ -v
wrun ruff check .
wrun tsc --noEmit
wrun make build
```

### Automatic (with shell integration)

When `WRUN_AUTO=1`, these commands are transparently intercepted:

| Command | Intercepted via |
|---------|----------------|
| `uv run pytest/ruff/mypy/ty` | `uv()` wrapper |
| `bun test`, `bun run lint/test/typecheck` | `bun()` wrapper |
| `npx/bunx tsc/vitest/jest/biome` | `npx()`/`bunx()` |
| `pytest`, `vitest`, `jest`, `mypy` | direct wrapper |
| `ruff check/format`, `biome check/lint`, `tsc` | direct wrapper |

Non-test/lint subcommands (`uv pip`, `bun install`, etc.) pass through untouched.

### Pipe mode

```bash
pytest tests/ 2>&1 | wrun --stdin
pytest tests/ 2>&1 | wrun --stdin --tool pytest
```

### Options

```
--full              Bypass optimization, show full output (still strips ANSI + relativizes paths)
--json              Structured JSON output
-q, --quiet         Summary line only
--max-failures N    Max failures to display (default: 10)
--max-lines N       Max error lines per failure (default: 15)
--no-save           Don't save full output to disk
--stdin             Read from stdin instead of executing
--tool TOOL         Hint tool type for stdin mode
```

## Supported tools

| Tool | Parser | Features |
|------|--------|----------|
| **pytest** | `PytestParser` | Line numbers, assertion details, multi-line messages |
| **vitest/jest/bun test** | `VitestBunParser` | Failure blocks, duration, summary |
| **ruff** | `RuffParser` | Classic + modern (Rust-style) format, grouped by rule |
| **biome** | `BiomeParser` | Diagnostic parsing, grouped |
| **tsc/mypy/ty** | `TscParser` | Error code + location + message |
| **generic** | `GenericParser` | Smart head(5)+tail(15) truncation |

## Output format

### Test failures

```
exit:1 | pytest | 3 passed, 2 failed, 1 skipped | 0.3s
FAIL tests/test_auth.py:8 :: test_login — AssertionError: Expected 200 | assert 401 == 200
FAIL tests/test_db.py:42 :: test_query — TypeError: NoneType has no len()
full: ~/.local/share/wrun/20260416-093000-pytest.log
```

### Lint errors (grouped by rule)

```
exit:1 | ruff | 6 errors
F401 x3: `os` imported but unused [src/api.py:1, src/db.py:1, src/util.py:1]
E302 x2: Expected 2 blank lines [src/api.py:15, src/db.py:22]
E501 x1: Line too long [src/util.py:88]
3 fixable with --fix
full: ~/.local/share/wrun/20260416-093000-ruff_check.log
```

### Passing run

```
exit:0 | pytest | 50 passed | 1.2s
```

## Optimization techniques

1. **ANSI stripping** — remove color codes
2. **Path normalization** — relative to git root, worktree-aware, resolves `../../` traversals
3. **Failures only** — skip passing tests entirely
4. **Line numbers** — extracted from stack traces for direct file navigation
5. **Assertion details** — `assert X == Y` included for immediate context
6. **Stack trace filtering** — hide framework internals (site-packages, node_modules, _pytest, pluggy)
7. **Rule grouping** — lint errors grouped by code with compact locations
8. **Smart truncation** — generic output: 5-line head + 15-line tail (errors at bottom)
9. **1-line pass** — passing runs produce exactly 1 line
10. **Full output saved** — always available at `~/.local/share/wrun/*.log` (auto-cleanup, keeps 20)

## Token reduction

| Scenario | Raw | Optimized | Reduction |
|----------|-----|-----------|-----------|
| pytest 11 tests, 3 failures | 53 lines / 2.7KB | 5 lines | **90%** |
| pytest all passing | 10+ lines | 1 line | **90%+** |
| ruff 6 issues | 67 lines / 1.1KB | 4 lines | **94%** |
| generic build 200 lines | 200 lines / 6.3KB | 21 lines | **89%** |

## How it works

```
AI agent runs "uv run pytest tests/"
    ↓
.zshenv detects non-interactive shell → sets WRUN_AUTO=1 + sources integration.zsh
    ↓
uv() shell function intercepts → prepends "wrun"
    ↓
wrun executes command via subprocess (calls binary directly, no recursion)
    ↓
captures stdout+stderr → strips ANSI → relativizes paths
    ↓
detects tool (command name → fallback: output patterns)
    ↓
parser extracts: summary, failures/errors, line numbers, assertions
    ↓
formatter produces compact output → saves full log to disk
    ↓
AI receives minimal, actionable output with file:line locations
```

## Requirements

- Python 3.9+
- zsh (for shell integration)

## License

MIT
