# wrun

Token-optimized command wrapper for AI coding agents. Wraps test runners, linters, VCS tools, and filesystem commands to produce minimal, actionable output — reducing token consumption up to 89% on verbose commands.

## Why

AI coding agents (Claude Code, OpenCode, Cursor, etc.) waste context window on verbose tool output. A `docker ps` with 33 containers emits 11 KB of tabular data that AI has to parse to answer "is the API up?". A pytest run with 3 failures produces 50+ lines of framework noise hiding the 3 line:column pairs the agent needs. A `git diff` emits thousands of `+`/`-` lines when `file +N -M` is enough to decide the next action.

wrun sits between the agent and the tool: it runs the command, parses the output with a tool-specific parser, and emits a canonical one-line-summary + compact details format the agent can act on without rereading the whole blob.

Nothing is lost — the full output is always saved to `~/.local/share/wrun/*.log`. A `full: <path>` pointer is appended only when it adds value: when output was truncated, when the raw log has materially more lines than what was rendered, or when a non-zero exit produced substantial output. Compact, complete responses (e.g. `exit:0 | git_status | clean`) stay clean — no noisy pointer.

## Install

```bash
git clone https://github.com/RobertWsp/wrun.git
cd wrun
./install.sh
```

## Shell integration — automatic activation

For AI-agent shells (non-interactive), add to `~/.zshenv`:

```zsh
if [[ ! -o interactive ]]; then
    export WRUN_AUTO=1
    [[ -f ~/.local/share/wrun/integration.zsh ]] && source ~/.local/share/wrun/integration.zsh
fi
```

For your interactive shell (`~/.zshrc`):

```zsh
[[ -f ~/.local/share/wrun/integration.zsh ]] && source ~/.local/share/wrun/integration.zsh
# export WRUN_AUTO=1  # uncomment to enable in the terminal too
```

When `WRUN_AUTO=1`, these commands are transparently intercepted. Subcommands not listed pass through untouched:

| Command family | Intercepted subcommands |
|---|---|
| `git` | `status`, `diff`, `log`, `show`, `add`, `commit`, `push`, `pull`, `fetch`, `rm`, `mv`, `checkout`, `switch`, `merge`, `rebase`, `stash` |
| `docker` | `ps`, `images` |
| `uv run` | `pytest`, `py.test`, `ruff`, `mypy`, `ty` |
| `bun` | `test`, `run test`, `run lint`, `run typecheck`, `run check` |
| `npx` / `bunx` | `tsc`, `vitest`, `jest`, `biome` |
| direct | `pytest`, `vitest`, `jest`, `mypy`, `ruff`, `biome`, `tsc`, `grep`, `rg`, `ls`, `tree` |

Pass-through examples that stay out of wrun: `git rev-parse`, `git worktree list`, `docker run`, `docker exec`, `uv pip install`, `bun install`, `npx create-next-app`.

## Manual usage

```bash
wrun uv run pytest tests/
wrun ruff check .
wrun tsc --noEmit
wrun docker ps
wrun git log --oneline -20
wrun --full docker ps           # bypass optimization, just strip ANSI + relativize paths
pytest tests/ 2>&1 | wrun --stdin --tool pytest   # pipe mode
```

### Options

```
--full              Bypass optimization (still strips ANSI + relativizes paths)
--json              Structured JSON output
-q, --quiet         Summary line only
--max-failures N    Max failures/entries to display (default: 10)
--max-lines N       Max error lines per failure (default: 15)
--no-save           Don't save full output to disk
--stdin             Read from stdin instead of executing
--tool TOOL         Hint parser for --stdin mode
```

## Supported tools

### Test runners & linters
| Tool | Parser | Extracts |
|---|---|---|
| **pytest** | `PytestParser` | file:line per failure, assertion diff, multi-line messages |
| **vitest / jest / bun test** | `VitestBunParser` | failure block per test, duration, summary counts |
| **ruff** | `RuffParser` | classic + Rust-style diagnostics, grouped by rule code |
| **biome** | `BiomeParser` | diagnostic parsing, grouped |
| **tsc / mypy / ty** | `TscParser` | error code + file:line + message |

### VCS & filesystem tools
| Tool | Parser | Output shape |
|---|---|---|
| **git status** | `GitStatusParser` | porcelain codes (`M`/`A`/`D`/`R`/`??`) + branch + count rollup |
| **git diff** | `GitDiffParser` | per-file `status path +N -M`; handles default / `--stat` / `--name-only` / `--name-status` / `--numstat` |
| **git log / show** | `GitLogParser` | `hash subject` one per line, handles `--graph`/`--oneline` |
| **git add/commit/push/pull/…** | `GitWriteParser` | 1-line summary (commit SHA, refspec update, etc.) |
| **docker ps / images** | `DockerPsParser` | ID, name, image, status, compact ports (IPv4+IPv6 dedup) |
| **grep / rg / ag** | `GrepRgParser` | grouped by file, capped 50 total / 10 per file, line-number optional |
| **ls / tree** | `LsTreeParser` | compact listing, filters `.`, `..`, and noise dirs recursively |

### Fallback
| Tool | Parser | Features |
|---|---|---|
| **anything else** | `GenericParser` | Error-pattern extraction with ±1 line context (not blind head+tail) |

Noise directories auto-hidden by `ls`/`tree`: `node_modules`, `.git`, `__pycache__`, `.venv`, `venv`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `dist`, `build`, `.next`, `.nuxt`, `target`, `.idea`, `.vscode`.

## Real output examples

All examples below are captured from actual command runs in a fresh test repo, no hand-editing.

### pytest

```
exit:0 | pytest | 1 passed | 0.20s
```

3 failures out of 11 tests:
```
exit:1 | pytest | 8 passed, 3 failed | 0.3s
FAIL tests/test_auth.py:8 :: test_login — AssertionError: Expected 200, got 401 | assert 401 == 200
FAIL tests/test_db.py:42 :: test_query — TypeError: NoneType has no len()
FAIL tests/test_api.py:15 :: test_post — ConnectionError: connection refused
```

### git status (multi-state repo — modified, added, deleted, renamed, untracked)

Raw: 11 lines / 302 B → wrun: 6 lines / 176 B
```
exit:0 | git_status | on main | 1 modified, 1 added, 1 deleted, 1 renamed, 1 untracked
A  src/added.py
 M src/b.py
 D src/c.py
R  src/a.py -> src/renamed.py
?? src/untracked.py
```

### git diff HEAD

Raw: 25 lines / 513 B → wrun: 5 lines / 107 B (**79% reduction**)
```
exit:0 | git_diff | 4 files | +2 -2
A src/added.py +1 -0
M src/b.py +1 -1
D src/c.py +0 -1
M src/renamed.py
```

### git diff --name-only origin/master...HEAD

`--name-only`, `--name-status`, and `--numstat` are the fastest diff shapes AI agents reach for. They all get parsed into the same canonical table — no more silent "no changes" when the raw output was a list of 10+ bare paths.

```
exit:0 | git_diff | 10 files
M api/app/api/routes/admin.py
M api/app/repositories/users.py
M api/tests/test_admin_dashboard_stats.py
A front/src/stores/__tests__/admin-dashboard-stats.test.ts
M front/src/pages/admin/DashboardPage.tsx
…
```

### git log

Raw: 29 lines / 623 B → wrun: 6 lines / 148 B (**77% reduction**)
```
exit:0 | git_log | 4 commits
c04d2dc test commit body
a068946 feat: add src layout
7c0f71f feat: add readme
fa72488 initial
```

### git commit

Raw: 6 lines / 192 B → wrun: 1 line / 71 B (**82% reduction**)
```
exit:0 | git_write | commit c04d2dc on main: test commit body (4 files)
```

### docker ps (33 running containers)

Raw: 37 lines / 11 792 B → wrun: 17 lines / 1 351 B (**89% reduction**)
```
exit:0 | docker_ps | 33 running
3200e45dfde8 crm-api-bt-868j96khh-ca crm-bt-868j96khh-ca-api Up 3 minutes (healthy) :8121
ba8a8e68279d crm-realtime-bt-868j96khh-ca crm-bt-868j96khh-ca-realtime Up 3 minutes 8000/tcp,:8171
9b43fe0835e4 crm-meilisearch-branch-test getmeili/meilisearch:v1.12 Up 3 minutes (healthy) :7710
…
+21 more
```

### grep / rg (grouped by file)

```
exit:0 | grep | 3 matches in 2 files
./sample.py (2):
  1: def foo():
  3: def bar():
./tests/t.py (1):
  1: def t(): pass
```

### ls -la (with noise dirs + `.` and `..` filtered)

Raw: 11 lines / 529 B → wrun: 5 lines / 119 B (**78% reduction**)
```
exit:0 | ls | 2 dirs, 2 files, 6 noise hidden
F       10 README.md
F       60 sample.py
D     4096 src
D     4096 tests
```

### tree -L 2 (noise subtrees pruned recursively)

Raw: 17 lines / 343 B → wrun: 12 lines / 269 B (**22% reduction**)
```
exit:0 | tree | 11 entries, 4 noise hidden
.
├── README.md
├── sample.py
├── src
│   ├── added.py
│   ├── b.py
│   ├── renamed.py
│   ├── skip.py
│   └── untracked.py
└── tests
    └── t.py
```

### ruff (lint errors grouped by rule)

```
exit:1 | ruff | 6 errors
F401 x3: `os` imported but unused [src/api.py:1, src/db.py:1, src/util.py:1]
E302 x2: Expected 2 blank lines [src/api.py:15, src/db.py:22]
E501 x1: Line too long [src/util.py:88]
3 fixable with --fix
```

## Measured reduction — 35-case harness

`tests/harness.py` runs every parser against synthetic + real commands and asserts structural expectations (field presence, counts, line numbers, flags). Run it with:

```bash
python3 tests/harness.py
```

Current result:

```
Total: 35 | PASS: 35 | FAIL: 0
Aggregated: 29 373 B → 5 313 B  (−82%)
```

Selected cases (bytes in → bytes out):

| Case | Raw | Wrun | Δ |
|---|---:|---:|---:|
| `docker ps` (33 containers, live) | 11 792 B | 1 351 B | **−89%** |
| pytest 3-failure fixture | 2 462 B | 310 B | **−88%** |
| pytest 3-failure + `--quiet` | 2 462 B | 45 B | **−99%** |
| pytest 3-failure + `--max-failures=1` | 2 462 B | 155 B | **−94%** |
| pytest `--json` | 2 462 B | 563 B | **−78%** |
| vitest 2-failure fixture | 1 291 B | 538 B | **−59%** |
| tsc 4 errors / 3 files | 516 B | 273 B | **−48%** |
| ruff classic 6 errors | 359 B | 255 B | **−29%** |
| ruff modern Rust-style | 392 B | 156 B | **−61%** |
| ls -la with noise dirs | 268 B | 82 B | **−70%** |
| tree with deep noise subtrees | 194 B | 123 B | **−37%** |
| git diff (2-file fixture) | 274 B | 70 B | **−75%** |
| git log (graph fixture) | 93 B | 109 B | +17% |
| git status porcelain (already compact) | 34 B | 89 B | +161% |
| grep multi-file (few matches) | 65 B | 107 B | +64% |
| `grep -Hn` self-source (real) | 4 247 B | 658 B | **−85%** |
| generic error-pattern extraction | 190 B | 205 B | +8% |
| 10 KB minified-style long line | 10 008 B | 521 B | **−95%** |

**Observations**:
- **Verbose output wins big** (60–99% reduction). This is the common AI-agent case: `docker ps`, `git log`, `ls -la`, `git diff`, `pytest` with failures, long build logs.
- **Already-compact output adds a canonical header** (`--porcelain`, `--oneline`, single-file grep, empty diff). The `exit:N | tool | summary` line is 20–70 extra bytes, but gives the agent a one-glance answer without reparsing.
- **`--quiet` compresses to one line regardless of failure count** (99% on pytest with 3 failures).
- **Empty output becomes informative**: `git diff` with no changes produces 0 bytes raw vs `exit:0 | git_diff | no changes` in wrun. The agent can now distinguish "no diff" from "silent failure".
- **Full output is never lost** — the raw log is always written to `~/.local/share/wrun/*.log`. The `full: <path>` pointer is appended only when output was truncated, materially reduced vs raw, or came from a failing command (exit ≠ 0 with >2 KB raw). Clean, compact responses don't carry the pointer.

## Edge cases covered

The harness exercises and validates:

| Edge case | Behavior |
|---|---|
| Empty input (stdin mode) | Emits `exit:0` summary, no error |
| Heavy ANSI CSI codes | Stripped; content preserved |
| OSC 8 hyperlinks (ruff modern) | Stripped; URL not echoed |
| Unicode + emoji (`💥`, `测试`, `ação`) | Preserved byte-for-byte |
| 10 KB single line (minified JS / base64) | Detected if it contains `error/ERROR`; truncated at 500 chars |
| Command not found (`execve` fails) | `exit:127` |
| `git commit` with global flags (`git -c k=v commit`) | Subcommand detected correctly (skips `-c k=v`) |
| `docker ps` IPv4 + IPv6 port pairs | Deduplicated (`0.0.0.0:80, [::]:80` → `:80`) |
| `rg` without line numbers (`--no-line-number`) | Matches grouped under `(match)` |
| `rg` single-file (no path prefix) | Same — no raw pass-through |
| `tree` with noise subtrees (`node_modules`, `.git`) | Entire subtree pruned (indent-aware) |
| `ls -la` with `.` and `..` entries | Hidden along with noise dirs |
| `git log --graph --oneline` | Graph prefix chars (`*|/\_`) stripped before hash match |
| pytest all-passing one-liner | Duration captured despite trailing `=` |
| Quiet mode with non-zero exit | One-line summary only (no details) |

## Optimization techniques

1. **ANSI stripping** — CSI, OSC 8 hyperlinks, private mode sequences
2. **Path normalization** — relative to git root, worktree-aware, resolves `../../` traversals back to absolute when outside the project
3. **Tool-specific parsers** — 18 parsers in the registry (5 test/lint + 7 new + 6 aliases)
4. **Failures only** — passing tests are counted, not listed
5. **Stack trace pruning** — `site-packages`, `node_modules`, `_pytest`, `pluggy`, `asyncio`, `threading` frames hidden
6. **Rule grouping** — lint errors grouped by code with compact `[file:line, file:line, +N]` locations
7. **Recursive noise filtering** — `tree` and `ls` skip entire `node_modules/.git/__pycache__/…` subtrees
8. **IPv4+IPv6 port dedup** — `0.0.0.0:8080->80/tcp, [::]:8080->80/tcp` → `:8080`
9. **Compact summary everywhere** — `exit:N | tool | count/status | duration`
10. **Full output saved** — `~/.local/share/wrun/*.log`, auto-cleanup keeps last 20

## How it works

```
AI agent: uv run pytest tests/
    ↓
~/.zshenv detects non-interactive shell → sets WRUN_AUTO=1 + sources integration.zsh
    ↓
uv() shell function sees `uv run pytest` → prepends `wrun`
    ↓
wrun spawns subprocess (calls binary directly — shell functions bypassed, no recursion)
    ↓
captures stdout+stderr → strips ANSI → relativizes paths to git root
    ↓
detects tool: cmd-parts match → SINGLE_CMD_MAP / GIT_SUBCOMMANDS / DOCKER_SUBCOMMANDS / TOOL_MAP
    ↓
parser extracts: counts, failures with file:line, assertions, diagnostics
    ↓
formatter emits: `exit:N | tool | summary` + compact details + `full: path`
    ↓
agent receives minimal, parseable output; can jump directly to file:line locations
```

No infinite recursion is possible: `subprocess.run([cmd, ...])` invokes the binary directly, not via the shell, so wrapper shell functions are not triggered from inside wrun.

## Requirements

- Python 3.9+
- zsh (for shell integration; direct `wrun` usage works from any shell)

## License

MIT
