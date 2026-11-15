# Packaging and installation

This repo is the **source of truth** under `skills/`.

To distribute skills to other repos/tools (without symlinks), use the skillpack scripts.

## Build dist

Build a packaged copy under `dist/`:

- `node shared/scripts/skillpack-build.mjs --clean`

Outputs:

- `dist/codex/.codex/skills/*` (OpenAI Codex repo layout)
- `dist/vscode/.github/skills/*` (VS Code / Copilot repo layout)
- `dist/claude/.claude/skills/*` (Claude Code repo layout)
- `dist/cursor/.cursor/skills/*` (Cursor repo layout)

Antigravity is opt-in. Add `--targets=codex,vscode,claude,cursor,antigravity` to also build:

- `dist/antigravity/.agents/skills/*` (Antigravity repo layout)

## Install into another repo

1. Build dist (above).
2. Install into a destination repo:

- `node shared/scripts/skillpack-install.mjs --dest=../some-repo --targets=codex,vscode,claude,cursor`

To include Antigravity, build it first and include it in the install targets:

- `node shared/scripts/skillpack-build.mjs --clean --targets=codex,vscode,claude,cursor,antigravity`
- `node shared/scripts/skillpack-install.mjs --dest=../some-repo --targets=codex,vscode,claude,cursor,antigravity`

By default, install mode is `replace` (it replaces only the skill directories it installs).

## Cursor and Grok Bot plugin

The repository root is also a Cursor plugin, which Grok Bot installs from the same manifest.

- `.cursor-plugin/plugin.json` declares the plugin and points `skills` at `./skills/`.
- `.cursor-plugin/marketplace.json` registers that plugin at the repository root (`"source": "."`).

No skill copies are required. Both clients discover each `skills/<name>/SKILL.md` from the manifest.

## Claude Code plugin

The repository root is also a Claude Code plugin.

- `.claude-plugin/plugin.json` declares the plugin. Skills stay in the default `skills/` directory, and the manifest leaves `skills` unset so Claude Code scans that directory once.
- `.claude-plugin/marketplace.json` registers that plugin at the repository root (`"source": "./"`). The entry `name` matches the manifest `name`.

`version` in `plugin.json` is `1.0.0`. Claude Code keeps an installed copy on that version until the string changes, so bump it when publishing skill updates. `plugin.json` is the version source; keep `version` off the marketplace entry.

No skill copies are required. Claude Code discovers each `skills/<name>/SKILL.md` from that layout.
