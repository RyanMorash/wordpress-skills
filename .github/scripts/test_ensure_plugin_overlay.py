#!/usr/bin/env python3
"""Restore fork-only doc sections and check the upstream sync dry run."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parents[1]

spec = importlib.util.spec_from_file_location(
    "ensure_plugin_overlay", SCRIPTS / "ensure-plugin-overlay.py"
)
overlay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(overlay)


FORK_README_HEADINGS = (
    "### Install globally for Cursor",
    "### Install as a Cursor or Grok Bot plugin",
    "### Install as a Claude Code plugin",
)
FORK_PACKAGING_HEADINGS = (
    "## Cursor and Grok Bot plugin",
    "## Claude Code plugin",
)


def git(repo: Path | None, *args: str) -> str:
    command = ["git"]
    if repo is not None:
        command.extend(["-C", str(repo)])
    command.extend(args)
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(f"{command}\n{result.stdout}\n{result.stderr}")
    return result.stdout


def git_config(repo: Path) -> None:
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")


def git_commit(repo: Path, message: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-m", message)


def without_headings(text: str, drop: set[str]) -> str:
    matches = list(overlay.iter_headings(text))
    pieces: list[str] = []
    cursor = 0
    for index, (start, heading) in enumerate(matches):
        if heading not in drop:
            continue
        end = matches[index + 1][0] if index + 1 < len(matches) else len(text)
        pieces.append(text[cursor:start])
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


class OverlayRestoreTest(unittest.TestCase):
    def test_shipped_docs_round_trip_without_fork_sections(self) -> None:
        cases = {
            REPO / "README.md": set(FORK_README_HEADINGS),
            REPO / "docs" / "packaging.md": set(FORK_PACKAGING_HEADINGS),
            REPO / "docs" / "upstream-sync.md": {"## This fork"},
        }
        for path, drop in cases.items():
            with self.subTest(path=path.name):
                original = path.read_text(encoding="utf-8")
                upstream = without_headings(original, drop)
                for heading in drop:
                    self.assertNotIn(heading, upstream)
                with tempfile.TemporaryDirectory() as tmp:
                    restored_path = Path(tmp) / path.name
                    restored_path.write_text(upstream, encoding="utf-8")
                    overlay.restore_file(str(restored_path), original, upstream)
                    restored = restored_path.read_text(encoding="utf-8")
                    self.assertEqual(restored.rstrip("\n"), original.rstrip("\n"))

    def test_sections_restore_in_order_before_the_shared_heading(self) -> None:
        fork = (
            "# Guide\n\n"
            "## Shared\n\nshared\n\n"
            "## Cursor\n\ncursor body\n\n"
            "## Grok Bot\n\ngrok body\n\n"
            "## Claude Code\n\nclaude body\n\n"
            "## License\n\nGPL\n"
        )
        upstream = "# Guide\n\n## Shared\n\nshared\n\n## License\n\nGPL\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "README.md"
            path.write_text(upstream, encoding="utf-8")
            overlay.restore_file(str(path), fork, upstream)
            restored = path.read_text(encoding="utf-8")
        license_at = restored.index("## License")
        cursor_at = restored.index("## Cursor")
        grok_at = restored.index("## Grok Bot")
        claude_at = restored.index("## Claude Code")
        self.assertLess(cursor_at, grok_at)
        self.assertLess(grok_at, claude_at)
        self.assertLess(claude_at, license_at)
        self.assertIn("cursor body", restored)
        self.assertIn("grok body", restored)
        self.assertIn("claude body", restored)
        self.assertEqual(restored.count("## Cursor"), 1)

    def test_existing_section_is_kept_and_a_missing_one_is_inserted(self) -> None:
        fork = (
            "# Guide\n\n"
            "## Cursor\n\nfresh cursor\n\n"
            "## Claude Code\n\nclaude body\n\n"
            "## License\n\nGPL\n"
        )
        upstream = "# Guide\n\n## License\n\nGPL\n"
        current = "# Guide\n\n## Cursor\n\nstale cursor\n\n## License\n\nGPL\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "README.md"
            path.write_text(current, encoding="utf-8")
            overlay.restore_file(str(path), fork, upstream)
            restored = path.read_text(encoding="utf-8")
        self.assertIn("stale cursor", restored)
        self.assertNotIn("fresh cursor", restored)
        self.assertLess(restored.index("## Claude Code"), restored.index("## License"))
        self.assertEqual(restored.count("## Cursor"), 1)

    def test_shared_headings_are_not_copied(self) -> None:
        text = "# Guide\n\n## Shared\n\nshared\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "README.md"
            path.write_text(text, encoding="utf-8")
            before = path.read_bytes()
            overlay.restore_file(str(path), text, text)
            self.assertEqual(path.read_bytes(), before)

    def test_heading_match_is_the_full_line(self) -> None:
        fork = (
            "# Guide\n\n"
            "## Cursor\n\ncursor body\n\n"
            "## Cursor plugin\n\nplugin body\n"
        )
        upstream = "# Guide\n\n## Cursor plugin\n\nplugin body\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "README.md"
            path.write_text(upstream, encoding="utf-8")
            overlay.restore_file(str(path), fork, upstream)
            restored = path.read_text(encoding="utf-8")
        self.assertLess(restored.index("## Cursor\n"), restored.index("## Cursor plugin"))
        self.assertIn("cursor body", restored)
        self.assertEqual(restored.count("plugin body"), 1)

    def test_fenced_shell_comment_is_not_a_heading(self) -> None:
        fork = (
            "# Guide\n\n"
            "## Shared\n\nshared\n\n"
            "## Plugin\n\n"
            "```bash\n"
            "# Clone agent-skills\n"
            "```\n\n"
            "plugin body\n\n"
            "## After\n\nafter\n"
        )
        current = (
            "# Guide\n\n"
            "## Shared\n\nshared upstream\n\n"
            "```bash\n"
            "## Plugin\n"
            "```\n\n"
            "## After\n\nafter\n"
        )
        upstream = current
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "README.md"
            path.write_text(current, encoding="utf-8")
            overlay.restore_file(str(path), fork, upstream)
            restored = path.read_text(encoding="utf-8")
        self.assertEqual(restored.count("## Plugin"), 2)
        plugin_at = restored.index("## Plugin\n")
        self.assertLess(restored.index("```bash\n## Plugin\n```"), plugin_at)
        self.assertLess(plugin_at, restored.index("## After"))
        self.assertIn("# Clone agent-skills", restored[plugin_at:])
        self.assertIn("plugin body", restored[plugin_at: restored.index("## After")])
        self.assertIn("shared upstream", restored)

    def test_missing_anchor_appends_and_missing_file_is_created(self) -> None:
        fork = "# Guide\n\n## Plugin\n\nplugin body\n"
        upstream = "# Guide\n\nshared"
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / "README.md"
            existing.write_text("# Guide\n\nshared", encoding="utf-8")
            overlay.restore_file(str(existing), fork, upstream)
            self.assertEqual(
                existing.read_text(encoding="utf-8"),
                "# Guide\n\nshared\n\n## Plugin\n\nplugin body\n\n",
            )

            missing = Path(tmp) / "docs" / "packaging.md"
            overlay.restore_file(str(missing), fork, upstream)
            self.assertEqual(missing.read_text(encoding="utf-8"), "## Plugin\n\nplugin body\n\n")

    def test_main_lists_readme_and_docs_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git(None, "init", "-b", "trunk", str(repo))
            git_config(repo)
            (repo / "README.md").write_text("# Guide\n", encoding="utf-8")
            (repo / "docs").mkdir()
            (repo / "docs" / "packaging.md").write_text("# Pack\n", encoding="utf-8")
            (repo / "docs" / "notes.txt").write_text("skip\n", encoding="utf-8")
            (repo / "skills" / "demo").mkdir(parents=True)
            (repo / "skills" / "demo" / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
            git_commit(repo, "base")
            base = git(repo, "rev-parse", "HEAD").strip()
            previous = os.getcwd()
            os.chdir(repo)
            try:
                self.assertEqual(overlay.list_overlay_docs(base), ["README.md", "docs/packaging.md"])
            finally:
                os.chdir(previous)


class SyncDryRunTest(unittest.TestCase):
    def test_dry_run_keeps_fork_files_and_takes_upstream_skill_edits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            origin = root / "origin.git"
            upstream = root / "upstream.git"
            work = root / "work"
            upstream_work = root / "upstream-work"
            git(None, "init", "--bare", "-b", "trunk", str(origin))
            git(None, "init", "--bare", "-b", "trunk", str(upstream))

            git(None, "init", "-b", "trunk", str(work))
            git_config(work)
            self._write(work / "shared" / "scripts" / "validate-skills.mjs", "process.exit(0)\n")
            self._write(work / ".github" / "scripts" / "sync-upstream-fork.sh", (SCRIPTS / "sync-upstream-fork.sh").read_text(encoding="utf-8"))
            self._write(work / ".github" / "scripts" / "ensure-plugin-overlay.py", (SCRIPTS / "ensure-plugin-overlay.py").read_text(encoding="utf-8"))
            self._write(work / "README.md", "# Guide\n\nShared intro.\n\n## License\n\nGPL\n")
            self._write(work / "skills" / "keep" / "SKILL.md", "keep-base\n")
            self._write(work / "skills" / "old" / "SKILL.md", "old\n")
            git_commit(work, "base")
            git(work, "remote", "add", "origin", str(origin))
            git(work, "push", "origin", "trunk")
            git(None, "clone", str(origin), str(upstream_work))
            git_config(upstream_work)
            git(upstream_work, "config", "protocol.file.allow", "always")
            git(upstream_work, "remote", "rename", "origin", "upstream")
            git(upstream_work, "remote", "set-url", "upstream", str(upstream))

            self._write(work / "README.md", "# Guide\n\nShared intro fork.\n\n## Cursor\n\ncursor body\n\n## Grok Bot\n\ngrok body\n\n## Claude Code\n\nclaude body\n\n## License\n\nGPL\n")
            self._write(work / "skills" / "keep" / "SKILL.md", "keep-fork\n")
            self._write(work / ".cursor-plugin" / "plugin.json", '{"name":"wordpress-skills"}\n')
            self._write(work / "assets" / "logo.svg", "logo\n")
            self._write(work / "docs" / "only-on-fork.md", "# Fork note\n\nfork only\n")
            git_commit(work, "fork overlay")
            fork_sha = git(work, "rev-parse", "HEAD").strip()
            git(work, "push", "origin", "trunk")
            git(work, "config", "protocol.file.allow", "always")

            self._write(upstream_work / "README.md", "# Guide\n\nShared intro upstream.\n\n## License\n\nGPL\n")
            self._write(upstream_work / "skills" / "keep" / "SKILL.md", "keep-upstream\n")
            (upstream_work / "skills" / "old" / "SKILL.md").unlink()
            self._write(upstream_work / "skills" / "new" / "SKILL.md", "new\n")
            git_commit(upstream_work, "upstream skills")
            git(upstream_work, "push", "upstream", "trunk")

            env = os.environ.copy()
            env.update(
                {
                    "SYNC_MODE": "dry-run",
                    "UPSTREAM_URL": str(upstream),
                    "UPSTREAM_BRANCH": "trunk",
                    "BASE_BRANCH": "trunk",
                    "SYNC_REMOTE": "wordpress-agent-skills",
                    "SYNC_BRANCH": "chore/sync-upstream-skills",
                }
            )
            env.pop("GH_TOKEN", None)
            env.pop("GITHUB_TOKEN", None)
            result = subprocess.run(
                ["bash", ".github/scripts/sync-upstream-fork.sh"],
                cwd=work,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                self.fail(f"sync exited {result.returncode}\n{result.stdout}\n{result.stderr}")

            readme = (work / "README.md").read_text(encoding="utf-8")
            self.assertIn("Shared intro upstream.", readme)
            self.assertNotIn("Shared intro fork.", readme)
            self.assertLess(readme.index("## Cursor"), readme.index("## Grok Bot"))
            self.assertLess(readme.index("## Grok Bot"), readme.index("## Claude Code"))
            self.assertLess(readme.index("## Claude Code"), readme.index("## License"))
            self.assertIn("cursor body", readme)
            self.assertIn("grok body", readme)
            self.assertIn("claude body", readme)
            self.assertEqual((work / "skills" / "keep" / "SKILL.md").read_text(encoding="utf-8"), "keep-upstream\n")
            self.assertFalse((work / "skills" / "old" / "SKILL.md").exists())
            self.assertEqual((work / "skills" / "new" / "SKILL.md").read_text(encoding="utf-8"), "new\n")
            self.assertEqual((work / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8"), '{"name":"wordpress-skills"}\n')
            self.assertEqual((work / "assets" / "logo.svg").read_text(encoding="utf-8"), "logo\n")
            self.assertIn("fork only", (work / "docs" / "only-on-fork.md").read_text(encoding="utf-8"))
            self.assertEqual(git(origin, "rev-parse", "trunk").strip(), fork_sha)
            remote_branches = git(origin, "branch")
            self.assertNotIn("chore/sync-upstream-skills", remote_branches)
            self.assertIn("Dry run: not pushing.", result.stdout)

    def _write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
