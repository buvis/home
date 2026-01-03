git_sync_master() {
  local branch
  branch="$(git rev-parse --abbrev-ref HEAD)" || {
    echo "Not in a git repo"
    return 2
  }
  git stash push -u -m "pre-rebase $(date -Iseconds)" >/dev/null 2>&1 || true
  if git fetch origin && git rebase origin/master; then
    git stash pop >/dev/null 2>&1 || true
    git push --force-with-lease origin "$branch" || return
  else
    echo "Rebase failed; resolve conflicts, then run: git rebase --continue" >&2
    echo "Your stash is preserved (check with: git stash list)" >&2
    return 1
  fi
}
