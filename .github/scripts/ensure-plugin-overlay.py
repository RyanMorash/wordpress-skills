#!/usr/bin/env python3
"""Put back fork-only sections in README.md and docs/*.md after an upstream merge.

A section is fork-only when its heading exists on the fork commit and not on
upstream. Skill files are left untouched so upstream skill text wins.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


HEADING = re.compile(r"(?m)^(#{1,6} .+)$")


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


def list_overlay_docs(rev: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", rev],
        check=True,
        capture_output=True,
        text=True,
    )
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if line == "README.md" or (line.startswith("docs/") and line.endswith(".md")):
            paths.append(line)
    return paths


def has_heading(text: str, heading: str) -> bool:
    return re.search(rf"(?m)^{re.escape(heading)}$", text) is not None


def fork_only_sections(fork_text: str, upstream_text: str) -> list[tuple[str, str, str | None]]:
    upstream_headings = set(HEADING.findall(upstream_text))
    matches = list(HEADING.finditer(fork_text))
    sections: list[tuple[str, str, str | None]] = []
    for index, match in enumerate(matches):
        heading = match.group(1)
        if heading in upstream_headings:
            continue
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(fork_text)
        next_heading = matches[index + 1].group(1) if index + 1 < len(matches) else None
        section = fork_text[start:end].rstrip() + "\n\n"
        sections.append((heading, section, next_heading))
    return sections


def append_section(text: str, section: str) -> str:
    updated = text
    if updated and not updated.endswith("\n"):
        updated += "\n"
    if updated and not updated.endswith("\n\n"):
        updated += "\n"
    return updated + section


def insert_section(text: str, section: str, next_heading: str | None) -> str:
    if next_heading is None:
        return append_section(text, section)
    match = re.search(rf"(?m)^{re.escape(next_heading)}$", text)
    if match is None:
        return append_section(text, section)
    prefix = text[: match.start()]
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    if prefix and not prefix.endswith("\n\n"):
        prefix += "\n"
    return prefix + section + text[match.start() :]


def restore_file(path: str, fork_text: str, upstream_text: str) -> None:
    sections = fork_only_sections(fork_text, upstream_text)
    if not sections:
        print(f"keep: {path} (no fork-only sections)")
        return

    file_path = Path(path)
    current = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
    missing = [heading for heading, _section, _next in sections if not has_heading(current, heading)]
    if not missing:
        print(f"keep: {path}")
        return

    updated = current
    # Later sections first, so an earlier section can anchor on the following heading.
    for heading, section, next_heading in reversed(sections):
        if has_heading(updated, heading):
            continue
        updated = insert_section(updated, section, next_heading)

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(updated, encoding="utf-8")
    print(f"restored: {path} ({', '.join(missing)})")

    written = file_path.read_text(encoding="utf-8")
    for heading, _section, _next in sections:
        if not has_heading(written, heading):
            raise SystemExit(f"Failed to restore {heading} in {path}")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: ensure-plugin-overlay.py <fork-rev> <upstream-rev>")
    fork_rev, upstream_rev = sys.argv[1], sys.argv[2]

    for path in list_overlay_docs(fork_rev):
        fork_text = git_show(fork_rev, path)
        if fork_text is None:
            raise SystemExit(f"Could not read {path} from {fork_rev}")
        upstream_text = git_show(upstream_rev, path)
        if upstream_text is None:
            print(f"keep: {path} (fork-only file)")
            continue
        restore_file(path, fork_text, upstream_text)


if __name__ == "__main__":
    main()
