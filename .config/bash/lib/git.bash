# Rebase current feature branch onto remote's default branch
# - stashes uncommitted changes, restores after success
# - force-pushes updated branch to origin
# - if on base branch, just pulls instead
git_catchup_parent() {
  local branch base candidate
  local stashed=false

  branch="$(git rev-parse --abbrev-ref HEAD)" || {
    echo "Not in a git repo"
    return 2
  }

  # try symbolic-ref, but verify it exists
  base=""
  candidate="$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@')"
  if [[ -n "$candidate" ]] && git show-ref --verify --quiet "refs/remotes/origin/$candidate"; then
    base="$candidate"
  fi

  # fallback to common names
  [[ -z "$base" ]] && {
    for b in main master; do
      git show-ref --verify --quiet "refs/remotes/origin/$b" && {
        base="$b"
        break
      }
    done
  }
  [[ -z "$base" ]] && {
    echo "Cannot determine base branch"
    return 2
  }

  [[ "$branch" == "$base" ]] && {
    git pull --ff-only origin "$branch"
    return
  }

  if ! git diff --quiet HEAD || [[ -n "$(git ls-files -o --exclude-standard)" ]]; then
    git stash push -u -m "pre-rebase $(date -Iseconds)"
    stashed=true
  fi

  if git fetch origin && git rebase "origin/$base"; then
    $stashed && git stash pop
    git push --force-with-lease origin "$branch" || return
  else
    echo "Rebase failed; resolve conflicts, then: git rebase --continue" >&2
    $stashed && echo "Stash preserved (git stash list)" >&2
    return 1
  fi
}

git_resolve_conflict() {
  if ! git rev-parse --git-dir &>/dev/null; then
    echo "Not in a git repository"
    return 1
  fi

  if ! git diff --name-only --diff-filter=U | grep -q .; then
    echo "No conflicts to resolve"
    return 0
  fi

  echo "/resolve-git-conflicts" | claude --permission-mode acceptEdits --allowedTools "Bash(git:*) Read Edit"
}
