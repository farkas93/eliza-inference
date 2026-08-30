"""Publish curated benchmark results to the repository root as BENCHMARKS.md.

`benchmarks/RESULTS.md` stays a local working copy (gitignored); the
published `BENCHMARKS.md` at the repo root is what gets committed and
pushed so the tables render on the git host.
"""
from __future__ import annotations

import datetime
import pathlib
import subprocess
from typing import Callable

PUBLISHED_NAME = "BENCHMARKS.md"
WORKING_COPY = pathlib.Path("benchmarks") / "RESULTS.md"


class PublishError(Exception):
    """Raised when benchmark results cannot be published."""


def _git(root: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
    )


def _git_out(root: pathlib.Path, *args: str) -> str:
    result = _git(root, *args)
    if result.returncode != 0:
        raise PublishError(f"git {' '.join(args)} failed: {(result.stderr or '').strip()}")
    return (result.stdout or "").strip()


def current_branch(root: pathlib.Path) -> str:
    return _git_out(root, "rev-parse", "--abbrev-ref", "HEAD")


def publish_results(
    root: pathlib.Path,
    regenerate: Callable[[], None] | None = None,
    target_branch: str = "main",
    force: bool = False,
    dry_run: bool = False,
    progress_callback: Callable[[str], None] | None = None,
) -> str:
    """Copy RESULTS.md to BENCHMARKS.md, commit, and push.

    Publishing is restricted to `target_branch` unless `force` is set.
    Returns a short human-readable status summary.
    """
    emit = progress_callback or (lambda _msg: None)

    branch = current_branch(root)
    if branch != target_branch and not force:
        raise PublishError(
            f"publish commits directly to '{target_branch}', but the current branch is '{branch}'. "
            f"Switch to '{target_branch}' first, or pass --force to publish from '{branch}'."
        )

    if regenerate is not None:
        emit("Regenerating benchmarks/RESULTS.md")
        regenerate()

    working = root / WORKING_COPY
    if not working.exists():
        raise PublishError(f"No working copy at {WORKING_COPY}. Run `eliza-cli bench compare` first.")
    content = working.read_text(encoding="utf-8")

    published = root / PUBLISHED_NAME
    if published.exists() and published.read_text(encoding="utf-8") == content:
        return "BENCHMARKS.md already up to date; nothing to publish."

    if dry_run:
        action = "create" if not published.exists() else "update"
        return f"[dry-run] Would {action} {PUBLISHED_NAME} and push a commit on '{branch}'."

    emit(f"Writing {PUBLISHED_NAME}")
    published.write_text(content, encoding="utf-8")

    stage = _git(root, "add", "--", PUBLISHED_NAME)
    if stage.returncode != 0:
        raise PublishError(f"git add failed: {(stage.stderr or '').strip()}")

    staged = _git(root, "diff", "--cached", "--quiet", "--", PUBLISHED_NAME)
    if staged.returncode == 0:
        return "BENCHMARKS.md already up to date; nothing to publish."

    date_tag = datetime.date.today().isoformat()
    commit = _git(root, "commit", "-m", f"docs: publish benchmark results ({date_tag})", "--", PUBLISHED_NAME)
    if commit.returncode != 0:
        raise PublishError(f"git commit failed: {(commit.stderr or '').strip()}{(commit.stdout or '').strip()}")

    emit(f"Pushing '{branch}'")
    push = _git(root, "push", "origin", branch)
    if push.returncode != 0:
        raise PublishError(
            "Committed locally but the push failed: "
            f"{(push.stderr or push.stdout or '').strip()}"
        )
    return f"Published {PUBLISHED_NAME} and pushed to origin/{branch}."
