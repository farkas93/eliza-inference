"""Shell completion support for eliza-cli.

`render_bash`/`render_zsh` emit completion scripts that fetch dynamic
candidates (services, canonical profile ids) from
`eliza-cli completion-data --what <kind>`, which runs discovery without
runtime probing so it stays fast.
"""
from __future__ import annotations

import pathlib

from .benchmarks import BENCHMARK_TYPES, TYPE_ALIASES
from .discovery import DiscoveryEngine

TOP_LEVEL_COMMANDS = ("list", "download", "benchmark", "bench", "tui", "completion", "completion-data")
BENCH_SUBCOMMANDS = ("run", "all", "compare", "list", "publish")
TYPE_CHOICE_VALUES = BENCHMARK_TYPES + tuple(TYPE_ALIASES)


def completion_data(root: pathlib.Path, what: str) -> list[str]:
    """Return completion candidates for the given kind."""
    if what == "commands":
        return list(TOP_LEVEL_COMMANDS)
    if what == "bench-subcommands":
        return list(BENCH_SUBCOMMANDS)
    if what == "types":
        return list(TYPE_CHOICE_VALUES)
    if what in ("services", "profiles"):
        stack = DiscoveryEngine(root).discover(probe=False)
        if what == "services":
            return sorted(stack.services)
        return sorted(stack.profiles)
    return []


BASH_SCRIPT = r"""
# eliza-cli bash completion
_eliza_cli_completions() {
    local cur prev cmd bench_cmd entry
    cur="${COMP_WORDS[COMP_CWORD]}"
    cmd=""
    bench_cmd=""
    local i
    for ((i = 1; i < COMP_CWORD; i++)); do
        entry="${COMP_WORDS[i]}"
        case "$entry" in
            -*) continue ;;
        esac
        if [[ -z "$cmd" ]]; then
            case "$entry" in
                benchmark|bench) cmd="bench" ;;
                list|download|tui|completion|completion-data) cmd="$entry" ;;
            esac
            continue
        fi
        if [[ "$cmd" == "bench" && -z "$bench_cmd" ]]; then
            case "$entry" in
                run|all|compare|list|publish) bench_cmd="$entry" ;;
            esac
        fi
    done
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    if [[ "$prev" == "--profile" ]]; then
        COMPREPLY=( $(compgen -W "$("$eliza_bin" completion-data --what profiles 2>/dev/null)" -- "$cur") )
        return 0
    fi

    if [[ -z "$cmd" ]]; then
        COMPREPLY=( $(compgen -W "$("$eliza_bin" completion-data --what commands 2>/dev/null)" -- "$cur") )
        return 0
    fi

    if [[ "$cmd" == "bench" && -z "$bench_cmd" ]]; then
        COMPREPLY=( $(compgen -W "$("$eliza_bin" completion-data --what bench-subcommands 2>/dev/null)" -- "$cur") )
        return 0
    fi

    if [[ "$cmd" == "bench" && "$bench_cmd" == "run" ]]; then
        local words
        words="$("$eliza_bin" completion-data --what types 2>/dev/null) $("$eliza_bin" completion-data --what services 2>/dev/null) --profile --force"
        COMPREPLY=( $(compgen -W "$words" -- "$cur") )
        return 0
    fi

    if [[ "$cmd" == "download" ]]; then
        COMPREPLY=( $(compgen -W "$("$eliza_bin" completion-data --what services 2>/dev/null) --profile" -- "$cur") )
        return 0
    fi

    if [[ "$cmd" == "completion" ]]; then
        COMPREPLY=( $(compgen -W "bash zsh" -- "$cur") )
        return 0
    fi

    if [[ "$cmd" == "bench" && ( "$bench_cmd" == "compare" || "$bench_cmd" == "list" ) ]]; then
        COMPREPLY=( $(compgen -W "--profile --service $("$eliza_bin" completion-data --what services 2>/dev/null)" -- "$cur") )
        return 0
    fi
    return 0
}

_eliza_cli_complete() {
    local eliza_bin
    eliza_bin="$(command -v eliza-cli 2>/dev/null || echo eliza-cli)"
    COMPREPLY=()
    _eliza_cli_completions
}

complete -F _eliza_cli_complete eliza-cli
"""

ZSH_SCRIPT = r"""#compdef eliza-cli
# eliza-cli zsh completion

_eliza_cli_candidates() {
    local eliza_bin
    eliza_bin="$(command -v eliza-cli 2>/dev/null || echo eliza-cli)"
    "$eliza_bin" completion-data --what "$1" 2>/dev/null | tr '\n' ' '
}

_eliza_cli() {
    local -a words_so_far
    words_so_far=("${words[2,CURRENT-1]}")
    local cmd="" bench_cmd="" entry
    for entry in "${words_so_far[@]}"; do
        [[ "$entry" == -* ]] && continue
        if [[ -z "$cmd" ]]; then
            case "$entry" in
                benchmark|bench) cmd="bench" ;;
                list|download|tui|completion|completion-data) cmd="$entry" ;;
            esac
            continue
        fi
        if [[ "$cmd" == "bench" && -z "$bench_cmd" ]]; then
            case "$entry" in
                run|all|compare|list|publish) bench_cmd="$entry" ;;
            esac
        fi
    done

    if [[ "$PREV" == "--profile" ]]; then
        _values 'profiles' $(_eliza_cli_candidates profiles)
        return
    fi

    if [[ -z "$cmd" ]]; then
        _values 'commands' $(_eliza_cli_candidates commands)
        return
    fi

    if [[ "$cmd" == "bench" && -z "$bench_cmd" ]]; then
        _values 'benchmark actions' $(_eliza_cli_candidates bench-subcommands)
        return
    fi

    if [[ "$cmd" == "bench" && "$bench_cmd" == "run" ]]; then
        _values 'options' $(_eliza_cli_candidates types) $(_eliza_cli_candidates services) '--profile' '--force'
        return
    fi

    if [[ "$cmd" == "download" ]]; then
        _values 'services' $(_eliza_cli_candidates services) '--profile'
        return
    fi

    if [[ "$cmd" == "completion" ]]; then
        _values 'shells' bash zsh
        return
    fi
}

_eliza_cli "$@"
"""


def render_bash() -> str:
    return BASH_SCRIPT.lstrip("\n")


def render_zsh() -> str:
    return ZSH_SCRIPT
