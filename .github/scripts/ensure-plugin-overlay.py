#!/usr/bin/env python3
"""Restore this fork's Cursor and Grok Bot plugin notes after an upstream merge.

The sections are copied from the fork commit that was current before the merge,
so later edits to those notes are kept. Skill files themselves are left alone.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


README_START = "### Install as a Cursor or Grok Bot plugin\n"
README_END = "### Install globally for Antigravity\n"
README_ANCHORS = (
    "### Install globally for Antigravity\n",
    "## Compatibility\n",
)
PACKAGING_START = "## Cursor and Grok Bot plugin\n"


def git_show(rev: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{rev}:{path}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def extract_readme_section(text: str) -> str | None:
    start = text.find(README_START)
    if start == -1:
        return None
    end = text.find(README_END, start + len(README_START))
    if end == -1:
        return None
    return text[start:end].rstrip() + "\n\n"


def extract_packaging_section(text: str) -> str | None:
    start = text.find(PACKAGING_START)
    if start == -1:
        return None
    return text[start:].rstrip() + "\n"


def insert_before(text: str, section: str, anchors: tuple[str, ...]) -> str:
    for anchor in anchors:
        index = text.find(anchor)
        if index == -1:
            continue
        prefix = text[:index]
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        if prefix and not prefix.endswith("\n\n"):
            prefix += "\n"
        return prefix + section + text[index:]
    suffix = text
    if suffix and not suffix.endswith("\n"):
        suffix += "\n"
    if suffix and not suffix.endswith("\n\n"):
        suffix += "\n"
    return suffix + section


def restore(path: str, section: str | None, marker: str, anchors: tuple[str, ...] = ()) -> None:
    file_path = Path(path)
    current = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
    if marker in current:
        print(f"keep: {path}")
        return
    if section is None:
        raise SystemExit(f"Fork commit is missing the plugin section needed to restore {path}")

    if anchors:
        updated = insert_before(current, section, anchors)
    else:
        updated = current
        if updated and not updated.endswith("\n"):
            updated += "\n"
        if updated and not updated.endswith("\n\n"):
            updated += "\n"
        updated += section

    file_path.write_text(updated, encoding="utf-8")
    print(f"restored: {path}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: ensure-plugin-overlay.py <fork-rev>")
    fork_rev = sys.argv[1]

    readme = git_show(fork_rev, "README.md")
    packaging = git_show(fork_rev, "docs/packaging.md")
    if readme is None or packaging is None:
        raise SystemExit("Could not read README.md or docs/packaging.md from the fork commit")

    restore(
        "README.md",
        extract_readme_section(readme),
        README_START.strip(),
        README_ANCHORS,
    )
    restore(
        "docs/packaging.md",
        extract_packaging_section(packaging),
        PACKAGING_START.strip(),
    )


if __name__ == "__main__":
    main()
