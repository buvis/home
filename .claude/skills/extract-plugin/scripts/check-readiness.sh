#!/usr/bin/env bash
# Plugin extraction readiness check.
#
# Usage: check-readiness.sh <skill-or-component> [<skill> ...]
#
# Greps five surfaces in ~/.claude/ for inbound references to each cluster item,
# then runs the inverse check (what each cluster item references outward).
# Also probes for personal data that must be sanitized before publish.

set -uo pipefail

if [ $# -eq 0 ]; then
  echo "Usage: $0 <name> [<name> ...]" >&2
  echo "       name = skill, command, agent, or hook (bare name, no extension)" >&2
  exit 1
fi

CLAUDE_DIR="${HOME}/.claude"
ITEMS=("$@")

# Build a regex matching any of the items, with word boundaries
JOINED=$(IFS='|'; echo "${ITEMS[*]}")
PATTERN="\\b(${JOINED})\\b"

echo "═══════════════════════════════════════════════════════════════════"
echo "  PLUGIN EXTRACTION READINESS"
echo "═══════════════════════════════════════════════════════════════════"
echo "  Cluster: ${ITEMS[*]}"
echo

# ───────────────────────────────────────────────────────────────────
# Inbound references: who else points at our cluster items?
# ───────────────────────────────────────────────────────────────────
echo "── INBOUND ────────────────────────────────────────────────────"

scan_surface() {
  local label="$1"
  shift
  local results
  results=$(grep -lE "$PATTERN" "$@" 2>/dev/null || true)
  if [ -n "$results" ]; then
    echo "[$label] references found in:"
    echo "$results" | sed 's|^|  |'
  fi
}

# 1. Hooks (python files + settings.json)
mapfile -t HOOK_FILES < <(find "$CLAUDE_DIR/hooks" -maxdepth 1 -name '*.py' 2>/dev/null)
if [ ${#HOOK_FILES[@]} -gt 0 ]; then
  scan_surface "hooks" "${HOOK_FILES[@]}" "$CLAUDE_DIR/settings.json"
fi

# 2. Commands
mapfile -t CMD_FILES < <(find "$CLAUDE_DIR/commands" -maxdepth 1 -name '*.md' 2>/dev/null)
if [ ${#CMD_FILES[@]} -gt 0 ]; then
  scan_surface "commands" "${CMD_FILES[@]}"
fi

# 3. Agents
mapfile -t AGENT_FILES < <(find "$CLAUDE_DIR/agents" -maxdepth 1 -name '*.md' 2>/dev/null)
if [ ${#AGENT_FILES[@]} -gt 0 ]; then
  scan_surface "agents" "${AGENT_FILES[@]}"
fi

# 4. Other skills (excluding cluster itself)
mapfile -t SKILL_FILES < <(find "$CLAUDE_DIR/skills" -name 'SKILL.md' 2>/dev/null)
FILTERED=()
for skill_md in "${SKILL_FILES[@]}"; do
  skip=0
  for item in "${ITEMS[@]}"; do
    if [[ "$skill_md" == */"$item"/SKILL.md ]]; then
      skip=1
      break
    fi
  done
  [ $skip -eq 0 ] && FILTERED+=("$skill_md")
done
if [ ${#FILTERED[@]} -gt 0 ]; then
  scan_surface "other-skills" "${FILTERED[@]}"
fi

# 5. Rules
mapfile -t RULE_FILES < <(find "$CLAUDE_DIR/rules" -name '*.md' 2>/dev/null)
if [ ${#RULE_FILES[@]} -gt 0 ]; then
  scan_surface "rules" "${RULE_FILES[@]}"
fi

# 6. User instructions (AGENTS.md, CLAUDE.md, GEMINI.md at ~/.claude root)
USER_INSTRUCTION_FILES=()
for f in "$CLAUDE_DIR/AGENTS.md" "$CLAUDE_DIR/CLAUDE.md" "$CLAUDE_DIR/GEMINI.md"; do
  [ -f "$f" ] && USER_INSTRUCTION_FILES+=("$f")
done
if [ ${#USER_INSTRUCTION_FILES[@]} -gt 0 ]; then
  scan_surface "user-instructions" "${USER_INSTRUCTION_FILES[@]}"
fi

# 7. Shell rc / shell plugins
SHELL_RC_FILES=()
for f in "$HOME/.zshrc" "$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.profile"; do
  [ -f "$f" ] && SHELL_RC_FILES+=("$f")
done
mapfile -t SHELL_PLUGIN_FILES < <(find "$HOME/.config/bash" "$HOME/.config/fish" "$HOME/.oh-my-zsh/custom" -type f \( -name '*.bash' -o -name '*.zsh' -o -name '*.fish' -o -name '*.sh' \) 2>/dev/null)
ALL_SHELL_FILES=("${SHELL_RC_FILES[@]}" "${SHELL_PLUGIN_FILES[@]}")
if [ ${#ALL_SHELL_FILES[@]} -gt 0 ]; then
  scan_surface "shell-rc" "${ALL_SHELL_FILES[@]}"
fi

echo
# ───────────────────────────────────────────────────────────────────
# Inverse: what do our cluster items reference outside?
# ───────────────────────────────────────────────────────────────────
echo "── INVERSE (outward refs from cluster) ────────────────────────"

EXTERNAL_PATTERN='(~/\.claude/(hooks|commands|agents|skills)/[a-z0-9_-]+|/Users/[a-z]+/\.claude/|CLAUDE_PLUGIN_ROOT|CLAUDE_SKILL_DIR|`/[a-z][a-z0-9-]+`|Invoke `/[a-z][a-z0-9-]+`|/[a-z][a-z0-9-]+ skill)'

for item in "${ITEMS[@]}"; do
  for loc in "$CLAUDE_DIR/skills/$item" "$CLAUDE_DIR/commands/$item.md" "$CLAUDE_DIR/agents/$item.md" "$CLAUDE_DIR/hooks/$item.py"; do
    if [ -e "$loc" ]; then
      if [ -d "$loc" ]; then
        hits=$(grep -rnE "$EXTERNAL_PATTERN" "$loc" 2>/dev/null || true)
      else
        hits=$(grep -nE "$EXTERNAL_PATTERN" "$loc" 2>/dev/null || true)
      fi
      if [ -n "$hits" ]; then
        echo "[$item] outward references:"
        echo "$hits" | sed 's|^|  |'
      fi
    fi
  done
done

echo
# ───────────────────────────────────────────────────────────────────
# Soft coupling: non-cluster hooks that string-match cluster runtime artifacts
# ───────────────────────────────────────────────────────────────────
echo "── SOFT COUPLING (non-cluster hooks referencing cluster runtime) ─"

# Build a regex over likely-runtime identifiers derived from cluster names
# (e.g. "autopilot" from "run-autopilot", "de-sloppify" if it appears as a literal).
# Also include common sentinel patterns: _<UPPER>_LOOP env vars, dev/local/<cluster>/.
SOFT_TERMS=()
for item in "${ITEMS[@]}"; do
  # base name without 'run-' / 'use-' prefix
  stripped="${item#run-}"
  stripped="${stripped#use-}"
  SOFT_TERMS+=("$stripped")
  # ALL CAPS sentinel form for env vars
  upper=$(echo "$stripped" | tr '[:lower:]-' '[:upper:]_')
  SOFT_TERMS+=("_${upper}_LOOP")
  SOFT_TERMS+=("dev/local/${stripped}/")
done

# Dedupe + join
mapfile -t SOFT_UNIQ < <(printf '%s\n' "${SOFT_TERMS[@]}" | sort -u)
SOFT_PATTERN=$(IFS='|'; echo "${SOFT_UNIQ[*]}")

# Exclude cluster's own hook files from this scan
NON_CLUSTER_HOOKS=()
for h in "${HOOK_FILES[@]}"; do
  skip=0
  for item in "${ITEMS[@]}"; do
    if [[ "$h" == */"$item".py ]] || [[ "$h" == */"$item"_*.py ]]; then
      skip=1
      break
    fi
  done
  [ $skip -eq 0 ] && NON_CLUSTER_HOOKS+=("$h")
done

if [ ${#NON_CLUSTER_HOOKS[@]} -gt 0 ]; then
  hits=$(grep -nE "$SOFT_PATTERN" "${NON_CLUSTER_HOOKS[@]}" 2>/dev/null || true)
  if [ -n "$hits" ]; then
    echo "Non-cluster hooks reference cluster runtime artifacts:"
    echo "$hits" | sed 's|^|  |'
    echo
    echo "  → Each match is a soft contract. Document the keyword/path"
    echo "    as a stability invariant in the plugin's README, or update"
    echo "    the personal hook to use a more explicit signal."
  fi
fi

echo
# ───────────────────────────────────────────────────────────────────
# Personal-data probe: anything that won't fly on the marketplace
# ───────────────────────────────────────────────────────────────────
echo "── PERSONAL-DATA PROBE (must be sanitized before publish) ─────"

PERSONAL_PATTERN='/Users/bob|~/bim/|buvis-plugins|/dev/local/|affaan-m/'
for item in "${ITEMS[@]}"; do
  for loc in "$CLAUDE_DIR/skills/$item" "$CLAUDE_DIR/commands/$item.md" "$CLAUDE_DIR/agents/$item.md" "$CLAUDE_DIR/hooks/$item.py"; do
    if [ -e "$loc" ]; then
      if [ -d "$loc" ]; then
        hits=$(grep -rnE "$PERSONAL_PATTERN" "$loc" 2>/dev/null || true)
      else
        hits=$(grep -nE "$PERSONAL_PATTERN" "$loc" 2>/dev/null || true)
      fi
      if [ -n "$hits" ]; then
        echo "[$item] personal references:"
        echo "$hits" | sed 's|^|  |'
      fi
    fi
  done
done

echo
echo "═══════════════════════════════════════════════════════════════════"
echo "  Review each finding and classify per the SKILL.md Phase 2 table:"
echo "    same-cluster / different-cluster (plugin or pending) /"
echo "    personal-only / built-in / soft-coupling / shell-function /"
echo "    user-instructions / MISSING-FROM-PLUGIN (expand cluster and re-run)"
echo "═══════════════════════════════════════════════════════════════════"
