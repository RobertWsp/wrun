# wrun

Token-optimized command wrapper for AI coding agents. Wraps test runners, linters, VCS tools, and filesystem commands to produce minimal, actionable output — reducing token consumption **87–97% on verbose commands** (144 674 raw tokens → 4 714 after wrun across the full test corpus).

## Why

AI coding agents (Claude Code, OpenCode, Cursor, etc.) waste context window on verbose tool output. A `docker ps` with 33 containers emits 11 KB of tabular data that AI has to parse to answer "is the API up?". A pytest run with 3 failures produces 50+ lines of framework noise hiding the 3 line:column pairs the agent needs. A `git diff` emits thousands of `+`/`-` lines when `file +N -M` is enough to decide the next action.

wrun sits between the agent and the tool: it runs the command, parses the output with a tool-specific parser, and emits ultra-compact output the agent can act on without rereading the whole blob.

Nothing is lost — the full output is always saved to `~/.local/share/wrun/*.log`. A `→path` pointer is appended only when it adds value: when output was truncated, when the raw log has materially more lines than what was rendered, or when a non-zero exit produced substantial output. Compact, complete responses (e.g. `✓git_status main clean`) stay clean — no noisy pointer.

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

### Pipeline-aware wrapping (TTY detection)

Commands whose native output is line-oriented and commonly fed to pipelines (`xargs`, `head`, `awk`, `cut`) check `[[ -t 1 ]]` before wrapping. When stdout is **not a TTY**, they pass through to the real binary so downstream consumers see the raw output. This keeps shell one-liners working even with `WRUN_AUTO=1` exported globally:

```bash
# With WRUN_AUTO=1 — ls sees stdout is a pipe, skips wrun → raw file list
ls -t ~/.local/share/wrun/*.log | head -1 | xargs cat

# In terminal (stdout is TTY) — ls is wrapped → optimized output with noise hidden
ls -la
```

Tools with TTY-aware wrapping: `ls`, `tree`, `grep`, `rg`, `git`, `docker`.

Diagnostic tools keep unconditional wrapping (output is always structured, agents want it parsed even when captured): `pytest`, `vitest`, `jest`, `ruff`, `biome`, `tsc`, `mypy`, `make`, `cargo`, `kubectl`, `bun`, `npx`, `bunx`, `uv`.

**Override**: set `WRUN_FORCE_PIPE=1` to wrap even in pipelines when you want the optimized summary programmatically:

```bash
WRUN_FORCE_PIPE=1 docker ps | grep "Up"   # get compact docker_ps rendering
WRUN_FORCE_PIPE=1 git log --oneline -20 | head -5
```

## Manual usage

```bash
wrun uv run pytest tests/
wrun ruff check .
wrun tsc --noEmit
wrun docker ps
wrun git log --oneline -20
wrun --full docker ps           # bypass optimization, just strip ANSI + relativize paths
wrun --no-compact git status    # verbose format (disable ultra-compact)
pytest tests/ 2>&1 | wrun --stdin --tool pytest   # pipe mode
```

### Options

```
--full              Bypass optimization (still strips ANSI + relativizes paths)
--no-compact        Disable ultra-compact mode (use verbose format)
--json              Structured JSON output
-q, --quiet         Summary line only
--max-failures N    Max failures/entries to display (default: 10)
--max-lines N       Max error lines per failure (default: 15)
--no-save           Don't save full output to disk
--stdin             Read from stdin instead of executing
--tool TOOL         Hint parser for --stdin mode
```

Set `WRUN_COMPACT=0` to disable ultra-compact globally (e.g. for scripting).

## Supported tools

### Test runners & linters
| Tool | Parser | Extracts |
|---|---|---|
| **pytest** | `PytestParser` | file:line per failure, assertion diff, multi-line messages |
| **vitest / jest / bun test** | `VitestBunParser` | failure block per test, duration, summary counts |
| **ruff** | `RuffParser` | classic + Rust-style diagnostics, grouped by rule code |
| **biome** | `BiomeParser` | 4 reporters (pretty, summary, github, json) · lint/assist/parse/format categories · severity (error/warning) · duration + fixable + checked/fixed/skipped metadata |
| **tsc / mypy / ty** | `TscParser` | error code + file:line + message |

### VCS & filesystem tools
| Tool | Parser | Output shape |
|---|---|---|
| **git status** | `GitStatusParser` | porcelain codes (`M`/`A`/`D`/`R`/`??`) + branch + count rollup |
| **git diff** | `GitDiffParser` | per-file `status path +N -M`; handles default / `--stat` / `--name-only` / `--name-status` / `--numstat` |
| **git log / show** | `GitLogParser` | `hash subject` one per line, handles `--graph`/`--oneline` |
| **git add/commit/push/pull/…** | `GitWriteParser` | 1-line summary (commit SHA, refspec update, etc.) |
| **docker ps / images** | `DockerPsParser` | ID, name, image, status, compact ports (IPv4+IPv6 dedup) |
| **docker logs** | `DockerLogsParser` | timestamps stripped, repeated errors collapsed (`msg x47`), 30-line tail deduped |
| **grep / rg / ag** | `GrepRgParser` | grouped by file, capped 50 total / 10 per file, line-number optional |
| **ls / tree** | `LsTreeParser` | compact listing, filters `.`, `..`, and noise dirs recursively |

### Build & infra
| Tool | Parser | Extracts |
|---|---|---|
| **cargo** | `CargoParser` | errors grouped by code (`E0001 x2: msg [a.rs:10+1]`), warnings count, test panics |
| **make / cmake** | `MakeParser` | error lines, warning count, last targets |
| **kubectl** | `KubectlParser` | table/describe/apply/logs mode, log line deduplication |

### Package managers
| Tool | Parser | Extracts |
|---|---|---|
| **npm / pnpm / yarn / bun install** | `PackageInstallParser` | added/updated/removed counts, deprecated warnings |
| **pip install / uv add / bundle install** | `PackageInstallParser` | installed packages, already-satisfied count |

### Fallback
| Tool | Parser | Features |
|---|---|---|
| **anything else** | `GenericParser` | Error-pattern extraction with ±1 line context; smart install/download detection (ultra-compressed for benign verbose output) |

Noise directories auto-hidden by `ls`/`tree`: `node_modules`, `.git`, `__pycache__`, `.venv`, `venv`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `dist`, `build`, `.next`, `.nuxt`, `target`, `.idea`, `.vscode`.

## Real output examples

All examples below are captured from actual command runs, no hand-editing. Ultra-compact is the default format.

### pytest

```
✓pytest 1p 0.20s
```

3 failures out of 11 tests:
```
✗pytest 3F/11 0.3s
✗test_login@8: AssertionError: Expected 200, got 401 | assert 401 == 200
✗test_query@42: TypeError: NoneType has no len()
✗test_post@15: ConnectionError: connection refused
```

### git status (multi-state repo — modified, added, deleted, renamed, untracked)

```
✓git_status main 1M 1A 1D 1R 1?
A  src/added.py
 M src/b.py
 D src/c.py
R  src/a.py -> src/renamed.py
?? src/untracked.py
```

### git diff HEAD

Raw: 25 lines / 513 B → wrun: 5 lines / 55 B (**74% token reduction**)
```
✓git_diff 4f +2-2
A src/added.py +1 -0
M src/b.py +1 -1
D src/c.py +0 -1
M src/renamed.py
```

### git diff --name-only origin/master...HEAD

```
✓git_diff 10f
M api/app/api/routes/admin.py
M api/app/repositories/users.py
M api/tests/test_admin_dashboard_stats.py
A front/src/stores/__tests__/admin-dashboard-stats.test.ts
M front/src/pages/admin/DashboardPage.tsx
…
```

### git log

```
✓git_log 4c
c04d2dc test commit body
a068946 feat: add src layout
7c0f71f feat: add readme
fa72488 initial
```

### git commit

```
✓git_write commit c04d2dc on main: test commit body (4 files)
```

### docker ps (33 running containers)

Raw: 37 lines / 11 792 B → wrun: 17 lines / 1 351 B (**66% token reduction**)
```
✓docker_ps 33↑
3200e45dfde8 crm-api-bt-868j96khh-ca crm-bt-868j96khh-ca-api Up 3 minutes (healthy) :8121
ba8a8e68279d crm-realtime-bt-868j96khh-ca crm-bt-868j96khh-ca-realtime Up 3 minutes 8000/tcp,:8171
9b43fe0835e4 crm-meilisearch-branch-test getmeili/meilisearch:v1.12 Up 3 minutes (healthy) :7710
…
+21
```

### grep / rg (grouped by file)

```
✓grep 3/2f
./sample.py (2):
  1: def foo():
  3: def bar():
./tests/t.py (1):
  1: def t(): pass
```

### ls -la (with noise dirs + `.` and `..` filtered)

Raw: 11 lines / 529 B → wrun: 5 lines / 45 B (**86% token reduction**)
```
✓ls 2d 2f -6
F       10 README.md
F       60 sample.py
D     4096 src
D     4096 tests
```

### ruff (lint errors grouped by rule)

```
✗ruff 6F
F401×3 `os` imported but unused[api.py:1+2]
E302×2 expected 2 blank lines, found 1[api.py:15+1]
E501 line too long (95 > 79 characters)[util.py:88]
3fix
```

### biome (full reporter coverage: pretty / summary / json / github)

Pretty reporter (default):

```
✗biome 2e 1w 3f 15ms
lint/suspicious/noExplicitAny Unexpected any. Specify a different type.[App.tsx:12]
lint/correctness/noUnusedVariables This variable is unused.[api/client.ts:45]
lint/style/useConst[w] This let declares a variable that is never reassigned.[utils.ts:8]
1fix
```

Parse errors (syntax, non-lint category):

```
✗biome 1e 1f 2ms
parse Expected a semicolon or an implicit semicolon after a statement, but found none.[broken.ts:5]
```

Format diagnostics (whole-file, no `:line:col`):

```
✗biome 2e 2f 3ms
format×2 File content differs from formatting output[foo.ts+1]
2fix
```

Clean run (no diagnostics):

```
✓biome clean 12f 8ms
```

### cargo (errors grouped by code)

```
✗cargo 3e 2w
E0001×2: cannot find value `x` in this scope [main.rs:10+1]
E0308: mismatched types [lib.rs:5]
```

### npm / pip install

```
✓install +234
  deprecated: inflight
  deprecated: glob
```

```
✓install installed: certifi-2023.7.22 requests-2.31.0 urllib3-2.0.7
```

## Measured reduction — 81-case harness

`tests/harness.py` runs every parser against synthetic + real commands and asserts structural expectations (field presence, counts, line numbers, flags). Run it with:

```bash
python3 tests/harness.py
```

Current result:

```
Total: 81 | PASS: 83 | FAIL: 0
```

The harness includes **8 cases using actual Biome 2.4.12 output** (`tests/corpus/biome_real_*.txt`) captured from `npm install @biomejs/biome@latest` runs against TypeScript fixtures covering: clean files, explicit any, unused vars, debugger, unused imports, format violations, assist/organizeImports, and all 4 reporters (pretty, summary, github, json).

Token counts measured with [tiktoken](https://github.com/openai/tiktoken) using the `cl100k_base` encoding (GPT-4 BPE — the de-facto proxy for modern LLM token accounting; Claude and Gemini use similar BPE granularity, so per-case deltas are robust across providers). Reproduce with:

```bash
pip install --user tiktoken
python3 tests/token_report.py
```

| Tool · case | Raw B | Wrun B | Raw tok | Wrun tok | Δ bytes | Δ tokens |
|---|---:|---:|---:|---:|---:|---:|
| pytest 3 failures (corpus) | 2 462 | 209 | 491 | 67 | **−91%** | **−87%** |
| pytest 3 failures + `--quiet` | 2 462 | 22 | 491 | 14 | **−99%** | **−97%** |
| pytest 3 failures + `--max-failures=1` | 2 462 | 91 | 491 | 37 | **−96%** | **−92%** |
| pytest `--json` | 2 462 | 563 | 491 | 155 | **−77%** | **−68%** |
| pytest all-passing synthetic | 278 | 20 | 54 | 12 | **−93%** | **−78%** |
| vitest 2 failures | 1 291 | 350 | 700 | 116 | **−73%** | **−83%** |
| tsc 4 errors / 3 files | 516 | 223 | 160 | 75 | **−57%** | **−53%** |
| ruff classic 6 errors | 359 | 166 | 130 | 67 | **−54%** | **−48%** |
| ruff modern (Rust-style) | 392 | 108 | 131 | 44 | **−72%** | **−66%** |
| biome pretty 3 errors (synthetic) | 1 104 | 265 | 278 | 72 | **−76%** | **−74%** |
| biome warnings-only (synthetic) | 745 | 186 | 190 | 55 | **−75%** | **−71%** |
| biome mixed err+warn+fixable | 1 089 | 276 | 262 | 80 | **−75%** | **−69%** |
| biome format category | 760 | 88 | 185 | 32 | **−88%** | **−83%** |
| biome many (15 diagnostics) | 2 906 | 258 | 678 | 89 | **−91%** | **−86%** |
| biome summary reporter (aggregated) | 742 | 23 | 159 | 17 | **−97%** | **−89%** |
| biome quiet mode | 1 089 | 23 | 262 | 17 | **−98%** | **−93%** |
| **biome REAL 2.4.12 · pretty single-file** | 3 962 | 441 | 1 083 | 119 | **−89%** | **−89%** |
| **biome REAL 2.4.12 · pretty multi-file (15 diags)** | 9 025 | 597 | 2 423 | 161 | **−93%** | **−93%** |
| **biome REAL 2.4.12 · github reporter** | 2 356 | 587 | 601 | 154 | **−75%** | **−74%** |
| **biome REAL 2.4.12 · summary reporter** | 1 881 | 22 | 409 | 17 | **−99%** | **−95%** |
| **biome REAL 2.4.12 · JSON reporter** | 4 045 | 592 | 1 015 | 158 | **−85%** | **−84%** |
| **biome REAL 2.4.12 · format-only** | 883 | 96 | 198 | 28 | **−89%** | **−85%** |
| **biome REAL 2.4.12 · assist/organizeImports** | 1 523 | 170 | 382 | 45 | **−89%** | **−88%** |
| cargo: error with location | 250 | 102 | 80 | 39 | **−59%** | **−51%** |
| cargo: clean build | 101 | 15 | 30 | 10 | **−85%** | **−66%** |
| docker_ps 2 containers (stdin) | 359 | 104 | 119 | 41 | **−71%** | **−65%** |
| docker_ps Paused+Removing states | 375 | 145 | 95 | 53 | **−61%** | **−44%** |
| docker_logs: error surfacing + tail | 246 | 224 | 104 | 60 | **−9%** | **−42%** |
| make: --max-failures respected | 521 | 106 | 259 | 55 | **−80%** | **−78%** |
| `ls -la` with noise dirs | 268 | 45 | 148 | 21 | **−83%** | **−85%** |
| `tree -L 2` with deep noise | 194 | 115 | 62 | 38 | **−41%** | **−38%** |
| git diff (2-file fixture) | 274 | 55 | 114 | 30 | **−80%** | **−73%** |
| git diff `--name-only` (4 files) | 138 | 145 | 33 | 37 | +5% | +12% |
| git log graph fixture | 93 | 94 | 34 | 33 | +1% | +3% |
| git_status porcelain (already compact) | 34 | 57 | 15 | 28 | +68% | +87% |
| grep multi-file (few matches) | 65 | 99 | 28 | 45 | +52% | +61% |
| generic: large benign output (install/download) | 14 289 | 130 | 2 999 | 32 | **−99%** | **−99%** |
| edge: 10 KB minified-style long line | 10 008 | 518 | 1 255 | 72 | **−95%** | **−94%** |
| edge: OSC 8 hyperlinks (ruff modern) | 134 | 53 | 52 | 23 | **−60%** | **−55%** |
| edge: heavy ANSI codes | 35 | 35 | 18 | 11 | +0% | **−39%** |
| edge: empty input (stdin) | 0 | 17 | 0 | 6 | - | - |
| **AGGREGATED (81-case corpus)** | **1 089 347** | **15 852** | **144 674** | **4 714** | **−99%** | **−97%** |

**Reading the table**:
- Bold negative deltas = wrun wins. **Verbose + structured output** (pytest failures, biome pretty, docker lists, cargo errors, 10 KB lines) dominates this region with 66–99% reductions.
- Already-compact payloads (`git log --oneline`, `git status --porcelain`, small greps) show positive deltas because the meta header costs ~10–30 tokens. This is a *deliberate* trade-off: the canonical header gives the agent a zero-parse answer (`3M 1?` vs reparsing 4 porcelain codes).
- Byte and token deltas usually agree within ±5 percentage points. Tokens can drop faster than bytes when the raw output has BPE-inefficient content — ANSI escapes (`\x1b[31m`), box-drawing (`━`), repeated indentation — which collapse heavily under GPT-4 BPE.

**Why tokens matter more than bytes**: LLM context windows and billing are measured in tokens, not bytes. A 9 KB Biome pretty-reporter output costs ~2 423 tokens raw but only ~161 after wrun — a **93% token saving**, which means 15× more tool output fits before hitting context limits. For agents running dozens of tool calls per session this compounds into whole extra turns of productive work.

### Analysis of positive-delta cases (where wrun adds tokens)

Five cases in the table show **positive deltas** — wrun output is larger than raw. These are deliberate tradeoffs, not regressions:

| Case | Δ tok | Tokens added | Value added | Verdict |
|---|---:|---|---|---|
| `git_status` porcelain (`M/?? /A`) | **+13** | `✓git_status main 1M 1A 1?` (~13 tok) | Zero-parse rollup — agent reads "1M 1A 1?" instead of mentally reducing 3 porcelain codes | ✅ Tradeoff — value grows with entry count; a 30-file porcelain status saves ~90% |
| `grep` multi-file (few matches) | **+17** | Meta line + per-file `./file.py (N):` headers | Grouping by file + count. With 3 matches overhead is significant; with 50+ matches the grouping is essential | ✅ Tradeoff — same structure scales to 1000+ matches |
| `git diff --name-only` (4 paths) | **+4** | Single `exit:0\n` line prefix | Zero-byte transformation; agent still gets the canonical exit code signal | ✅ Near break-even — adaptive passthrough skips meta line when raw already fits the shape |
| `generic` error-pattern extraction | **+9** | `exit:N \| generic` meta line | Tells agent: parser didn't recognize the tool, used error-pattern heuristic | ✅ Small cost, informative |
| `git log` graph fixture | **+2** | Meta line; offset by removal of graph chars (`* `, `\|\\`) | Near break-even. BPE-expensive graph glyphs collapse cleanly | ✅ Effectively neutral |

**Pattern**: positive deltas cluster around **already-compact inputs** (≤ 200 bytes raw). For scale-varying tools (`git_status`, `grep`, `ls`) the same emitted structure that looks expensive on tiny inputs dominates the savings on real-world inputs — a production `git status` with 50 entries, or a `grep -rn` across 200 files, reaches the same ~−90% territory as Biome's pretty reporter.

### Adaptive passthrough (surgical)

For cases where the parser performs **no semantic transformation** — e.g. `git diff --name-only` emits a bare path list that agents consume as-is — wrun detects the pattern and skips the meta line entirely, emitting `exit:N\n<raw>`. This drops the 4-path fixture from +30% tokens (with meta) to +12% tokens (passthrough) — the residual overhead is the `exit:0\n` signal agents parse.

Guards (all must hold for passthrough to engage):
- `result.extra.get("git_diff_inferred_status") is True` — parser confirmed raw is pure path list
- `exit_code == 0` — non-zero exits keep structured output (agent needs failure context)
- No `--json` / `--quiet` / `--full` flag
- Raw input ≤ 200 bytes and meta version would be larger (≥ 8 byte overhead)

**Not on the table but worth noting**: `heavy ANSI codes` edge case is **bytes +0% but tokens −39%**. Raw `\x1b[31mERROR\x1b[0m` is BPE-expensive (each escape code tokenizes into 3-4 sub-tokens); wrun strips ANSI and keeps plain text, bytes stay roughly flat but tokens drop sharply. This is why token measurement matters — byte-only accounting underestimates real agent-context savings on colorful CLI tools.

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
| `docker logs` repeated error lines | Collapsed (`ERROR: timeout x47`) |
| `rg` without line numbers (`--no-line-number`) | Matches grouped under `(match)` |
| `rg` single-file (no path prefix) | Same — no raw pass-through |
| `tree` with noise subtrees (`node_modules`, `.git`) | Entire subtree pruned (indent-aware) |
| `ls -la` with `.` and `..` entries | Hidden along with noise dirs |
| `git log --graph --oneline` | Graph prefix chars (`*|/\_`) stripped before hash match |
| pytest all-passing one-liner | Duration captured despite trailing `=` |
| Quiet mode with non-zero exit | One-line summary only (no details) |
| Biome 2.x warning icon (`!` vs 1.x `⚠`) | Both accepted; severity inferred |
| Biome 2.x info icon (`i` vs 1.x `ℹ`) | Both accepted for fix hints |
| Biome 2.x GitHub key order (`title=` first) | Keys parsed in any order |
| Biome 2.x JSON schema (ns duration, string path, line/column) | 2.x + 1.x schemas both supported |
| Biome 2.x JSON preamble + `check ━` footer | Blob extracted from middle; footer ignored |
| Biome summary reporter (`reporter/format ━`, `reporter/violations ━`) | Headers recognized; aggregate summary surfaced |
| kubectl log lines repeated | Collapsed via deduplication |
| `npm install` / `pip install` verbose output | PackageInstallParser: counts + deprecated warnings only |

## Optimization techniques

1. **Ultra-compact output** — default format uses `✓/✗tool summary` icons, `NF/total` for counts, `×N` for grouped lint rules, `↑↓` for container states; saves additional 3–8 percentage points over verbose format
2. **ANSI stripping** — CSI, OSC 8 hyperlinks, OSC sequences (BEL/ST terminators), private mode
3. **Path normalization** — relative to git root, worktree-aware, resolves `../../` traversals back to absolute when outside the project
4. **Tool-specific parsers** — 19 parser classes, 24 registry entries counting aliases (mypy/ty → TscParser, ag → GrepRgParser, npm/pip/bundle → PackageInstallParser, etc.)
5. **Failures only** — passing tests are counted, not listed
6. **Stack trace pruning** — `site-packages`, `node_modules`, `_pytest`, `pluggy`, `asyncio`, `threading` frames hidden
7. **Rule grouping** — lint errors grouped by code with compact `[file:line+N]` locations
8. **Severity split** — biome shows `Ne Mw` separately; per-rule `[w]` / `[i]` tags
9. **Log line deduplication** — repeated consecutive identical lines collapsed to `line xN` (threshold: 3+); applied to docker logs, kubectl logs
10. **Recursive noise filtering** — `tree` and `ls` skip entire `node_modules/.git/__pycache__/…` subtrees
11. **IPv4+IPv6 port dedup** — `0.0.0.0:8080->80/tcp, [::]:8080->80/tcp` → `:8080`
12. **Multi-reporter detection** — biome's 4 reporters (pretty/summary/github/json) handled with schema differences between Biome 1.x and 2.x
13. **TTY-aware wrapping** — `ls`/`tree`/`grep`/`rg`/`git`/`docker` skip optimization when stdout is piped; override with `WRUN_FORCE_PIPE=1`
14. **SIGPIPE handling** — `SIG_DFL` + `BrokenPipeError` trap so `wrun cmd | head` exits cleanly without tracebacks
15. **Adaptive passthrough** — pure path-list outputs (e.g. `git diff --name-only`) skip the meta line when it would add tokens with no value
16. **Smart install detection** — GenericParser detects install/download patterns and applies ultra-aggressive compression (3 lines + tail)
17. **Full output saved** — `~/.local/share/wrun/*.log`, auto-cleanup keeps last 20; `→path` pointer only when agent benefits from it

## How it works

```
AI agent: uv run pytest tests/
    ↓
~/.zshenv detects non-interactive shell → sets WRUN_AUTO=1 + sources integration.zsh
    ↓
uv() shell function sees `uv run pytest` → checks _wrun_active / _wrun_pipe_active → prepends `wrun`
    ↓
wrun spawns subprocess (calls binary directly — shell functions bypassed, no recursion)
    ↓
captures stdout+stderr → strips ANSI → relativizes paths to git root
    ↓
detects tool: cmd-parts match → SINGLE_CMD_MAP / GIT_SUBCOMMANDS / DOCKER_SUBCOMMANDS / TOOL_MAP
    ↓
parser extracts: counts, failures with file:line, assertions, diagnostics, severity
    ↓
formatter emits ultra-compact: `✗pytest 3F/11 0.3s` + `✗test_name@line: msg` + `→path`
    ↓
agent receives minimal, parseable output; can jump directly to file:line locations
```

No infinite recursion is possible: `subprocess.run([cmd, ...])` invokes the binary directly, not via the shell, so wrapper shell functions are not triggered from inside wrun.

For shell pipelines like `ls *.log | head -1 | xargs cat`, the `_wrun_pipe_active` helper detects that stdout is not a TTY and skips wrapping, so downstream consumers see raw file paths instead of the optimized `✓ls 2d 2f` header. Diagnostic tools (pytest, ruff, biome, tsc, …) keep unconditional wrapping — their structured output benefits agents that capture via subprocess.

## Requirements

- Python 3.9+
- zsh (for shell integration; direct `wrun` usage works from any shell)

## License

MIT
