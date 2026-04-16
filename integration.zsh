# ─── wrun shell integration ─────────────────────────────────────────────────────
# Auto-wraps test/lint/type-check commands with wrun for optimized AI output.
#
# Activation: export WRUN_AUTO=1
# When WRUN_AUTO != 1, all commands run normally (zero overhead).
#
# Source this file in .zshrc:
#   [[ -f ~/.local/share/wrun/integration.zsh ]] && source ~/.local/share/wrun/integration.zsh
#
# Safe: subprocess.run() in wrun calls binaries directly, not shell functions.
# No infinite recursion possible.
# ──────────────────────────────────────────────────────────────────────────────

# Guard: only define once
(( ${+functions[_wrun_active]} )) && return

_wrun_active() {
    [[ "$WRUN_AUTO" == "1" ]]
}

# ─── Direct tool wrappers ────────────────────────────────────────────────────
# For tools called directly (not through uv/bun/npx)

pytest() {
    if _wrun_active; then command wrun pytest "$@"; else command pytest "$@"; fi
}

py.test() {
    if _wrun_active; then command wrun py.test "$@"; else command py.test "$@"; fi
}

vitest() {
    if _wrun_active; then command wrun vitest "$@"; else command vitest "$@"; fi
}

jest() {
    if _wrun_active; then command wrun jest "$@"; else command jest "$@"; fi
}

mypy() {
    if _wrun_active; then command wrun mypy "$@"; else command mypy "$@"; fi
}

# ─── uv wrapper ──────────────────────────────────────────────────────────────
# Wraps: uv run pytest/ruff/mypy/ty

uv() {
    if _wrun_active && [[ "$1" == "run" ]]; then
        case "$2" in
            pytest|py.test|ruff|mypy|ty)
                command wrun uv "$@"
                return $?
                ;;
        esac
    fi
    command uv "$@"
}

# ─── bun wrapper ─────────────────────────────────────────────────────────────
# Wraps: bun test, bun run test, bun run lint, bun run typecheck

bun() {
    if _wrun_active; then
        case "$1" in
            test)
                command wrun bun "$@"
                return $?
                ;;
            run)
                case "$2" in
                    test|lint|typecheck|type-check|check)
                        command wrun bun "$@"
                        return $?
                        ;;
                esac
                ;;
        esac
    fi
    command bun "$@"
}

# ─── npx/bunx wrapper ───────────────────────────────────────────────────────
# Wraps: npx tsc, npx vitest, npx jest, bunx tsc, etc.

npx() {
    if _wrun_active; then
        case "$1" in
            tsc|vitest|jest|biome)
                command wrun npx "$@"
                return $?
                ;;
        esac
    fi
    command npx "$@"
}

bunx() {
    if _wrun_active; then
        case "$1" in
            tsc|vitest|jest|biome)
                command wrun bunx "$@"
                return $?
                ;;
        esac
    fi
    command bunx "$@"
}

# ─── ruff wrapper (direct call) ─────────────────────────────────────────────

ruff() {
    if _wrun_active; then
        case "$1" in
            check|format)
                command wrun ruff "$@"
                return $?
                ;;
        esac
    fi
    command ruff "$@"
}

# ─── biome wrapper (direct call) ────────────────────────────────────────────

biome() {
    if _wrun_active; then
        case "$1" in
            check|lint|ci)
                command wrun biome "$@"
                return $?
                ;;
        esac
    fi
    command biome "$@"
}

# ─── tsc wrapper (direct call) ──────────────────────────────────────────────

tsc() {
    if _wrun_active; then command wrun tsc "$@"; else command tsc "$@"; fi
}

# ─── Convenience aliases ────────────────────────────────────────────────────

alias wrun-on='export WRUN_AUTO=1'
alias wrun-off='unset WRUN_AUTO'
alias wrun-status='echo "WRUN_AUTO=${WRUN_AUTO:-off}"'
