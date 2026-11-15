#!/usr/bin/env bash
# Merge WordPress/agent-skills into this fork.
# Skill files follow upstream. Files that exist only on this fork are restored
# afterward (plugin manifests, logo, and similar). Fork-only sections in
# README.md and docs/*.md are put back as well.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# Later steps check out another commit, which can replace this file mid-run.
# Continue from a copy so the rest of the script stays stable.
if [[ -z "${SYNC_REEXEC:-}" ]]; then
  reexec_dir="$(mktemp -d)"
  cp "$ROOT/.github/scripts/sync-upstream-fork.sh" "$reexec_dir/sync-upstream-fork.sh"
  cp "$ROOT/.github/scripts/ensure-plugin-overlay.py" "$reexec_dir/ensure-plugin-overlay.py"
  export SYNC_REEXEC=1
  export SYNC_OVERLAY_PY="$reexec_dir/ensure-plugin-overlay.py"
  exec bash "$reexec_dir/sync-upstream-fork.sh"
fi

UPSTREAM_URL="${UPSTREAM_URL:-https://github.com/WordPress/agent-skills.git}"
UPSTREAM_BRANCH="${UPSTREAM_BRANCH:-trunk}"
BASE_BRANCH="${BASE_BRANCH:-trunk}"
SYNC_REMOTE="${SYNC_REMOTE:-wordpress-agent-skills}"
SYNC_BRANCH="${SYNC_BRANCH:-chore/sync-upstream-skills}"

if [[ -z "${SYNC_MODE:-}" ]]; then
  if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
    SYNC_MODE="auto"
  else
    SYNC_MODE="dry-run"
  fi
fi

case "$SYNC_MODE" in
  auto | dry-run) ;;
  *)
    echo "SYNC_MODE must be auto or dry-run (got: ${SYNC_MODE})" >&2
    exit 2
    ;;
esac

export GIT_AUTHOR_NAME="${GIT_AUTHOR_NAME:-github-actions[bot]}"
export GIT_AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL:-41898282+github-actions[bot]@users.noreply.github.com}"
export GIT_COMMITTER_NAME="${GIT_COMMITTER_NAME:-$GIT_AUTHOR_NAME}"
export GIT_COMMITTER_EMAIL="${GIT_COMMITTER_EMAIL:-$GIT_AUTHOR_EMAIL}"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is dirty. Commit or stash local changes before syncing." >&2
  exit 1
fi

if git remote get-url "$SYNC_REMOTE" >/dev/null 2>&1; then
  git remote set-url "$SYNC_REMOTE" "$UPSTREAM_URL"
else
  git remote add "$SYNC_REMOTE" "$UPSTREAM_URL"
fi

git fetch "$SYNC_REMOTE" "$UPSTREAM_BRANCH"
git fetch origin "$BASE_BRANCH"

FORK_HEAD="$(git rev-parse "origin/${BASE_BRANCH}")"
UPSTREAM_HEAD="$(git rev-parse "${SYNC_REMOTE}/${UPSTREAM_BRANCH}")"
MERGE_BASE="$(git merge-base "$FORK_HEAD" "$UPSTREAM_HEAD")"

# Files added on this fork since it diverged, and still absent from upstream.
# A file upstream deleted existed at the merge base, so it is not included.
list_fork_only_paths() {
  local path
  while IFS= read -r -d '' path; do
    if ! git cat-file -e "${UPSTREAM_HEAD}:${path}" 2>/dev/null; then
      printf '%s\0' "$path"
    fi
  done < <(git diff --name-only -z --no-renames --diff-filter=A "$MERGE_BASE" "$FORK_HEAD")
}

close_open_sync_pr() {
  local number
  if [[ -z "${GH_TOKEN:-}" && -z "${GITHUB_TOKEN:-}" ]]; then
    echo "No GitHub token is set, so any open sync pull request was left in place." >&2
    return 0
  fi
  if ! number="$(gh pr list --base "$BASE_BRANCH" --head "$SYNC_BRANCH" --state open --json number --jq '.[0].number')"; then
    echo "Could not list open sync pull requests." >&2
    return 1
  fi
  if [[ -z "$number" || "$number" == "null" ]]; then
    return 0
  fi
  if ! gh pr close "$number" --comment "Closed because these upstream skill changes are already on ${BASE_BRANCH}."; then
    echo "Could not close pull request #${number}." >&2
    return 1
  fi
  git push origin --delete "$SYNC_BRANCH" || true
  echo "Closed pull request #${number}."
}

if git merge-base --is-ancestor "$UPSTREAM_HEAD" "$FORK_HEAD"; then
  echo "Fork ${BASE_BRANCH} already contains ${UPSTREAM_URL} ${UPSTREAM_BRANCH} (${UPSTREAM_HEAD})."
  if [[ "$SYNC_MODE" == "auto" ]]; then
    close_open_sync_pr || echo "Fork is already up to date. An open sync pull request may still need to be closed." >&2
  fi
  exit 0
fi

echo "Upstream commits not in this fork:"
git log --oneline "${FORK_HEAD}..${UPSTREAM_HEAD}"

COMMIT_LIST="$(git log -50 --oneline "${FORK_HEAD}..${UPSTREAM_HEAD}")"
MERGE_MESSAGE="$(cat <<EOF
chore: sync skills from WordPress/agent-skills

Merge ${UPSTREAM_HEAD} from ${UPSTREAM_URL} (${UPSTREAM_BRANCH}).

Upstream commits:
${COMMIT_LIST}
EOF
)"

git checkout -B "$SYNC_BRANCH" "$FORK_HEAD"

set +e
git merge --no-ff -m "$MERGE_MESSAGE" "$UPSTREAM_HEAD"
merge_status=$?
set -e

if [[ "$merge_status" -ne 0 ]]; then
  echo "Resolving conflicts. Upstream wins, including deletions. Files added only on this fork stay."
  while IFS= read -r -d '' path; do
    if git cat-file -e "${UPSTREAM_HEAD}:${path}" 2>/dev/null; then
      if ! git checkout --theirs -- "$path"; then
        git rm -f -- "$path" || true
      fi
    elif git cat-file -e "${MERGE_BASE}:${path}" 2>/dev/null; then
      git rm -f -- "$path" || true
    elif ! git checkout --ours -- "$path"; then
      git rm -f -- "$path" || true
    fi
    git add -- "$path" || true
  done < <(git diff --name-only -z --diff-filter=U)

  if [[ -n "$(git diff --name-only --diff-filter=U)" ]]; then
    echo "Unresolved conflicts remain:" >&2
    git diff --name-only --diff-filter=U >&2
    exit 1
  fi

  if git diff --cached --quiet && git diff --quiet; then
    git commit --allow-empty --no-edit
  else
    git commit --no-edit
  fi
fi

# Restore paths this fork added. Do not put back files upstream removed.
while IFS= read -r -d '' path; do
  git checkout "$FORK_HEAD" -- "$path"
done < <(list_fork_only_paths)

python3 "$SYNC_OVERLAY_PY" "$FORK_HEAD" "$UPSTREAM_HEAD"

if ! git diff --quiet || ! git diff --cached --quiet; then
  git add -u -- README.md docs
  git commit -m "chore: keep fork-only plugin files and docs"
fi

while IFS= read -r -d '' path; do
  if [[ ! -e "$path" ]]; then
    echo "Fork-only path is missing after sync: ${path}" >&2
    exit 1
  fi
done < <(list_fork_only_paths)

echo "Validating skills..."
node shared/scripts/validate-skills.mjs

if git diff --quiet "$FORK_HEAD" HEAD; then
  echo "No file changes after preserving the fork overlay."
  exit 0
fi

echo "Files changed relative to ${BASE_BRANCH}:"
git diff --stat "$FORK_HEAD" HEAD

if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  {
    echo "### Upstream skill sync"
    echo
    echo "Merged \`${UPSTREAM_HEAD}\` from WordPress/agent-skills \`${UPSTREAM_BRANCH}\`."
    echo
    echo '```'
    printf '%s\n' "$COMMIT_LIST"
    echo '```'
  } >>"$GITHUB_STEP_SUMMARY"
fi

if [[ "$SYNC_MODE" == "dry-run" ]]; then
  echo "Dry run: not pushing."
  exit 0
fi

if git push origin "HEAD:${BASE_BRANCH}"; then
  echo "Updated ${BASE_BRANCH}."
  if ! close_open_sync_pr; then
    echo "Updated ${BASE_BRANCH}, but the sync pull request could not be closed." >&2
    exit 1
  fi
  if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    echo "Pushed the merge to \`${BASE_BRANCH}\`." >>"$GITHUB_STEP_SUMMARY"
  fi
  exit 0
fi

echo "Push to ${BASE_BRANCH} was rejected. Opening a pull request instead."
if git ls-remote --exit-code --heads origin "$SYNC_BRANCH" >/dev/null 2>&1; then
  git fetch origin "$SYNC_BRANCH"
  git push --force-with-lease="$SYNC_BRANCH" origin "HEAD:${SYNC_BRANCH}"
else
  git push -u origin "HEAD:${SYNC_BRANCH}"
fi

PR_BODY="$(cat <<EOF
Brings this fork up to date with skill changes from [WordPress/agent-skills](https://github.com/WordPress/agent-skills) \`${UPSTREAM_BRANCH}\`.

Upstream commits:

\`\`\`
${COMMIT_LIST}
\`\`\`

Files that exist only on \`${BASE_BRANCH}\` stay in place, including plugin manifests and \`assets/logo.svg\`. Fork-only sections in \`README.md\` and \`docs/*.md\` are kept. Skill files follow upstream.

A direct push to \`${BASE_BRANCH}\` was rejected, so this pull request needs a merge.
EOF
)"

existing="$(gh pr list --base "$BASE_BRANCH" --head "$SYNC_BRANCH" --state open --json number --jq '.[0].number')"
if [[ -n "$existing" && "$existing" != "null" ]]; then
  gh pr edit "$existing" --title "chore: sync skills from WordPress/agent-skills" --body "$PR_BODY"
  echo "Updated pull request #${existing}."
else
  gh pr create \
    --base "$BASE_BRANCH" \
    --head "$SYNC_BRANCH" \
    --title "chore: sync skills from WordPress/agent-skills" \
    --body "$PR_BODY"
fi

if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  echo "Opened or updated a pull request from \`${SYNC_BRANCH}\`." >>"$GITHUB_STEP_SUMMARY"
fi
