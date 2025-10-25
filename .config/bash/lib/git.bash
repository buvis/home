git_sync_main() {
  set -euo pipefail
  local branch
  branch="$(git rev-parse --abbrev-ref HEAD)"
  git stash push -u -m "pre-rebase $(date -Iseconds)"
  if git fetch origin && git rebase origin/main; then
    git stash pop || true
    git push --force-with-lease origin "$branch"
  else
    echo "Rebase failed; resolve conflicts, then run: git rebase --continue"
    echo "Your stash is preserved (check with: git stash list)"
  fi
}
