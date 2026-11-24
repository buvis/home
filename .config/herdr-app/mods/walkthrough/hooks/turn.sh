#!/bin/sh
# Records an agent's turns for the walkthrough mod, so "Last turn" can show
# exactly what one prompt changed. Claude Code runs it from two hooks:
#
#   UserPromptSubmit:  sh .../turn.sh start    the working tree before the turn
#   Stop:              sh .../turn.sh stop     the working tree after it
#
# ~/.herdr/walkthrough/turns/<repo key>/<seconds>-<pid>/
#   start.json, end.json   the hook's input, as Claude Code sent it
#   start.meta, end.meta   tree=<snapshot>, when, session, terminal (written last)
#   start.big, end.big     the new files over 1 MB each snapshot left out, one per line
#   objects/               the blobs and trees of content the index didn't already name
#   index                  the snapshot's own index (dropped once the turn is over)
#
# A snapshot is `git add -A && git write-tree --missing-ok` against an index
# (a copy of the repository's) and an object folder of its own. The
# repository's objects are left out of sight on purpose: git updates the
# modification time of an object it finds again, so a snapshot that could see
# them would touch them. Files the copied index already names keep pointing at
# the repository's objects, which the walkthrough reads beside the turn's.
# The repository's index, refs and objects are never written, not even their
# times. New files over 1 MB are left out, as the walkthrough leaves them unread.
#
# It never gets in the agent's way: nothing is printed (UserPromptSubmit's
# output would be added to Claude's context), and every failure is a quiet exit 0.
# Needs only sh and git.

KEEP=20
MAX_BYTES=1048576

base="${HOME}/.herdr/walkthrough/turns"

# A field of the hook's one-line JSON, when it is a plain string (no escapes).
field() {
  sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"\([^\"\\\\]*\)\".*/\1/p" "$2" | head -n 1
}

# The tree of the working tree now: `snapshot <turn folder> <index> <list of files left out>`.
snapshot() {
  turn=$1 index=$2 list=$3
  if [ ! -f "$index" ]; then
    # The repository's own index, copied: its file stats spare re-reading every unchanged file.
    real=$(git rev-parse --path-format=absolute --git-path index) || return 1
    [ -f "$real" ] && cp -p "$real" "$index"
  fi
  # New files over the limit, as pathspecs that leave them out.
  big=$(git -c core.quotePath=false ls-files --others --exclude-standard -z \
    | xargs -0 sh -c '[ $# -gt 0 ] && find "$@" -prune -type f -size +'"$MAX_BYTES"'c' sh 2>/dev/null)
  printf '%s\n' "$big" | grep -v '^$' > "$list"
  set -- .
  while IFS= read -r path; do
    [ -n "$path" ] || continue
    set -- "$@" ":(exclude,literal)$path"
    # A file that was small when the turn began is in this index already: out with it too, or its old content stays.
    GIT_INDEX_FILE="$index" git update-index --force-remove -- "$path" 2>/dev/null
  done <<EOF
$big
EOF
  add() {
    GIT_INDEX_FILE="$index" GIT_OBJECT_DIRECTORY="$turn/objects" \
      git -c core.fsmonitor=false -c gc.auto=0 -c maintenance.auto=false add -A -- "$@" &&
    GIT_INDEX_FILE="$index" GIT_OBJECT_DIRECTORY="$turn/objects" git write-tree --missing-ok
  }
  # A copied index git can't use here (a split index, say) is dropped, and the snapshot starts over without it.
  add "$@" || { rm -f "$index"; add "$@"; }
}

# Writes a file whole or not at all: the mod treats a turn as begun or ended once its .meta is there.
put() {
  printf '%s' "$2" > "$1.tmp" && mv "$1.tmp" "$1"
}

# The turns of this repository, newest first.
turns() {
  ls -1 "$repo" 2>/dev/null | grep -E '^[0-9]+-[0-9]+$' | sort -r
}

main() {
  event=$1
  case "$event" in start|stop) ;; *) return 0 ;; esac
  mkdir -p "$base" || return 0
  input="$base/input.$$"
  cat > "$input" || return 0

  cwd=$(field cwd "$input")
  [ -n "$cwd" ] && cd "$cwd" 2>/dev/null
  top=$(git rev-parse --show-toplevel 2>/dev/null) || return 0
  cd "$top" || return 0
  key=$(printf '%s' "$top" | git hash-object --stdin | cut -c1-16) || return 0
  repo="$base/$key"
  mkdir -p "$repo" || return 0
  [ -f "$repo/top" ] || put "$repo/top" "$top"
  session=$(field session_id "$input")
  now=$(date +%s)

  if [ "$event" = start ]; then
    # A background task's notification comes as a prompt too; it starts no turn. Mid-turn, the
    # turn goes on; after it, the next Stop ends the session's last turn again, with this work in it.
    grep -q '"prompt"[[:space:]]*:[[:space:]]*"<task-notification>' "$input" && return 0
    turn="$repo/$now-$(printf '%06d' $$)"
    mkdir -p "$turn/objects" || return 0
    mv "$input" "$turn/start.json"
    # An ended turn's index, or one of this session's earlier turns', is dead weight; another session's running turn still needs its own.
    for old in $(turns); do
      [ "$repo/$old" = "$turn" ] && continue
      if [ -f "$repo/$old/end.meta" ] || { [ -n "$session" ] && grep -qx "session=$session" "$repo/$old/start.meta"; }; then
        rm -f "$repo/$old/index"
      fi
    done
    # A failed snapshot leaves start.json without start.meta: this turn's Stop then finds it, and ends no older turn in its place.
    tree=$(snapshot "$turn" "$turn/index" "$turn/start.big") || { rm -rf "$turn/objects" "$turn/index"; return 0; }
    put "$turn/start.meta" "tree=$tree
started=$now
session=$session
terminal=${HC_TERMINAL_ID:-}
"
    # The newest $KEEP turns stay; an older one goes with its objects.
    turns | tail -n +$((KEEP + 1)) | while IFS= read -r old; do rm -rf "${repo:?}/$old"; done
    return 0
  fi

  # Stop: the session's newest turn, known by the start.json its start saved first. Ended already when a stop hook
  # kept the agent going; then it ends again, later. Without a start snapshot (still being taken, failed, or cut
  # short by the hook's timeout) nothing is written: an older turn of the session is over, and stays as it ended.
  turn=
  for name in $(turns); do
    if [ -z "$session" ] || grep -qx "session=$session" "$repo/$name/start.meta" || [ "$(field session_id "$repo/$name/start.json")" = "$session" ]; then
      turn="$repo/$name"
      break
    fi
  done
  [ -n "$turn" ] && [ -f "$turn/start.meta" ] || return 0
  tree=$(snapshot "$turn" "$turn/index" "$turn/end.big") || return 0
  mv "$input" "$turn/end.json"
  put "$turn/end.meta" "tree=$tree
ended=$now
"
}

main "$@" >/dev/null 2>&1
rm -f "${HOME}/.herdr/walkthrough/turns/input.$$" 2>/dev/null
exit 0
