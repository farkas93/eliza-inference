from __future__ import annotations

import pathlib
import re
import sys


ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
PROFILE_DIR = ROOT_DIR / "configs" / "profiles"
ALIASES_PATH = PROFILE_DIR / "aliases.sh"
PROFILE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_./-])(?:small|medium|stt|tts|vocode|voice)/[A-Za-z0-9][A-Za-z0-9._-]*"
)
CLI_PROFILE_PATTERN = re.compile(
    r"--profile(?:\s+|=)((?:(?:small|medium|stt|tts|vocode|voice)/|"
    r"(?:eliza-medium|eliza-small|stt|tts|vocode-bridge|voice-assistant)-)"
    r"[A-Za-z0-9_.-]+)"
)
ALIAS_PATTERN = re.compile(r'^\s*([^#].*?)\)\s+profile="([^"]+)"\s*;;\s*$')
SCAN_ROOTS = (
    ROOT_DIR / "README.md",
    ROOT_DIR / "configs" / "eliza-stack.toml",
    ROOT_DIR / "docs",
    ROOT_DIR / "scripts",
    ROOT_DIR / "services",
    ROOT_DIR / "systemd",
)


def canonical_profiles() -> set[str]:
    return {
        path.relative_to(PROFILE_DIR).with_suffix("").as_posix()
        for path in PROFILE_DIR.rglob("*.env")
    }


def aliases() -> dict[str, str]:
    mappings: dict[str, str] = {}
    for line in ALIASES_PATH.read_text(encoding="utf-8").splitlines():
        match = ALIAS_PATTERN.match(line)
        if match is None:
            continue
        patterns, target = match.groups()
        for alias in patterns.split("|"):
            mappings[alias] = target
    return mappings


def scanned_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for root in SCAN_ROOTS:
        if root.is_file():
            files.append(root)
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path in {ALIASES_PATH, pathlib.Path(__file__).resolve()}:
                continue
            if path.suffix in {".md", ".py", ".service", ".sh", ".toml"} or not path.suffix:
                files.append(path)
    return sorted(set(files))


def normalize_reference(profile: str) -> str:
    prefix_mappings = (
        ("eliza-medium-", "medium/"),
        ("eliza-small-", "small/"),
        ("stt-", "stt/"),
        ("tts-", "tts/"),
        ("vocode-bridge-", "vocode/bridge-"),
        ("voice-assistant-", "voice/assistant-"),
    )
    for prefix, replacement in prefix_mappings:
        if profile.startswith(prefix):
            return f"{replacement}{profile[len(prefix):]}"
    return profile


def main() -> int:
    profiles = canonical_profiles()
    alias_map = aliases()
    failures: list[str] = []

    for alias, target in sorted(alias_map.items()):
        if target not in profiles:
            failures.append(f"configs/profiles/aliases.sh: alias {alias} targets missing profile {target}")

    valid_references = profiles | {alias for alias, target in alias_map.items() if target in profiles}
    for path in scanned_files():
        relative_path = path.relative_to(ROOT_DIR)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(lines, start=1):
            references = {match.group(0) for match in PROFILE_PATTERN.finditer(line)}
            references.update(match.group(1) for match in CLI_PROFILE_PATTERN.finditer(line))
            for raw_profile in references:
                profile = normalize_reference(raw_profile)
                if profile.endswith(".env"):
                    profile = profile[:-4]
                if profile not in valid_references:
                    failures.append(f"{relative_path}:{line_number}: unresolved profile {raw_profile}")

    if failures:
        print("Profile reference validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print(f"Validated {len(profiles)} profiles and {len(alias_map)} aliases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
