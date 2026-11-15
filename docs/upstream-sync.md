# Upstream sync (automation plan)

## This fork

`.github/workflows/sync-upstream-fork.yml` keeps this fork current with [WordPress/agent-skills](https://github.com/WordPress/agent-skills) `trunk`. It runs every day at 11:17 UTC (6:17am Eastern Standard Time) and can be started with **Run workflow**.

The job merges upstream into this repository, then restores files that exist only on this fork, including `.cursor-plugin/`, `.claude-plugin/`, and `assets/logo.svg`. It also puts back fork-only sections in `README.md` and `docs/*.md`.

Skill files follow upstream, including files upstream removes. Do not keep fork-only edits under `skills/`; the next sync replaces them. When the merge applies, the workflow pushes to `trunk`. If that push is rejected, it opens a pull request from `chore/sync-upstream-skills`.

The script is `.github/scripts/sync-upstream-fork.sh`. Run it locally with `SYNC_MODE=dry-run` to preview a merge without pushing.

## Release indexes

Goal: when upstream changes (WordPress core releases, Gutenberg releases, docs updates), the repo should **regenerate indexes** and (eventually) **open PRs** that update affected skills/references.

## What to automate first (low risk)

1. **Indexes and matrices**
   - WordPress core version list (latest stable + recent).
   - Gutenberg releases list (latest stable + recent).
   - WordPress ↔ Gutenberg mapping table (derived from canonical docs where available).
2. **Routing metadata refresh**
   - Update `shared/references/*.json` files only.

This keeps automation deterministic and reviewable before it starts rewriting skill prose.

## Later automation (higher risk)

- “Reference chunk regeneration” from upstream docs into `skills/*/references/*.md`.
- Task-shaped deltas (e.g. a new Gutenberg package, new block APIs, changes in theme.json schema).
- Semi-automated PRs that include:
  - regenerated references
  - updated checklists
  - updated eval scenarios

## Scripts

- `shared/scripts/update-upstream-indices.mjs`
  - Fetches upstream sources and rewrites JSON indexes in `shared/references/`.

## CI / PR bot design (recommended)

- Schedule a workflow (daily/weekly).
- Run `shared/scripts/update-upstream-indices.mjs`.
- If `git diff` is non-empty, open a PR with:
  - a summary of changes
  - links to upstream release notes
  - a checklist for human review (“does this impact blocks/themes/plugin workflows?”)

## Validation

- Always run `node shared/scripts/validate-skills.mjs`.
- Optional: use Agent Skills reference validator:
  - `skills-ref validate skills/<skill-name>`

## Canonical sources

The automation should prefer canonical sources and avoid scraping where possible.

- WordPress core releases and API endpoints (official WordPress APIs)
- Gutenberg releases (GitHub releases)
- WordPress developer docs (used for the WP↔Gutenberg mapping when no API exists)
