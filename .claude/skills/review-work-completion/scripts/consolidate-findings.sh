#!/usr/bin/env bash
# Consolidates findings from multiple agent outputs
# Usage: consolidate-findings.sh NAME:FILE [NAME:FILE ...]
# Example: consolidate-findings.sh ALICE:alice.txt BOB:bob.txt DIANA:diana.txt
# Outputs: consolidated findings sorted by consensus then severity

set -euo pipefail

if [[ $# -eq 0 ]]; then
    echo "Usage: $0 NAME:FILE [NAME:FILE ...]" >&2
    echo "Example: $0 ALICE:alice.txt BOB:bob.txt DIANA:diana.txt" >&2
    exit 1
fi

TOTAL_AGENTS=$#

# Severity order for sorting (lower = more severe)
severity_order() {
  case "$1" in
    "🔴") echo 1 ;;
    "🟠") echo 2 ;;
    "🟡") echo 3 ;;
    "⚪") echo 4 ;;
    *) echo 5 ;;
  esac
}

# Parse single agent output file
# Output format: AGENT|SEVERITY|DESCRIPTION|FILE|TASK
parse_agent_output() {
  local file="$1"
  local agent="$2"

  [[ ! -f "$file" ]] && return

  while IFS= read -r line; do
    # Skip empty lines and "no issues" lines
    [[ -z "$line" ]] && continue
    # Strip markdown code fences
    [[ "$line" =~ ^\`\`\` ]] && continue
    [[ "$line" == *"No issues found"* ]] && continue

    # Parse: [AGENT] {emoji} {description} | File: {path} | Task: {id}
    if [[ "$line" == *" | File:"*" | Task:"* ]]; then
      local part1="${line%% | File:*}"
      local rest="${line#* | File: }"
      local file_path="${rest%% | Task:*}"
      local task="${rest##* | Task: }"

      local after_agent="${part1#*] }"

      local severity=""
      case "$after_agent" in
        🔴*) severity="🔴"; after_agent="${after_agent#🔴 }" ;;
        🟠*) severity="🟠"; after_agent="${after_agent#🟠 }" ;;
        🟡*) severity="🟡"; after_agent="${after_agent#🟡 }" ;;
        ⚪*) severity="⚪"; after_agent="${after_agent#⚪ }" ;;
        *) continue ;;
      esac

      local desc="$after_agent"

      # Trim whitespace
      desc="${desc#"${desc%%[![:space:]]*}"}"
      desc="${desc%"${desc##*[![:space:]]}"}"
      file_path="${file_path#"${file_path%%[![:space:]]*}"}"
      file_path="${file_path%"${file_path##*[![:space:]]}"}"
      task="${task#"${task%%[![:space:]]*}"}"
      task="${task%"${task##*[![:space:]]}"}"

      echo "${agent}|${severity}|${desc}|${file_path}|${task}"
    fi
  done < "$file"
}

# Normalize description for matching (lowercase, remove extra spaces)
normalize() {
  echo "$1" | tr '[:upper:]' '[:lower:]' | tr -s ' ' | sed 's/^ *//;s/ *$//'
}

declare -A issues_by_key=()
declare -A agents_by_key=()
declare -A severity_by_key=()
declare -A file_by_key=()
declare -A task_by_key=()
declare -A desc_by_key=()
issue_count=0

# Parse all agent outputs from NAME:FILE pairs
for agent_pair in "$@"; do
  agent="${agent_pair%%:*}"
  file="${agent_pair#*:}"

  [[ -z "$file" || ! -f "$file" ]] && continue

  while IFS='|' read -r src_agent severity desc file_path task; do
    [[ -z "$desc" ]] && continue

    key="$(normalize "$desc")|$(normalize "$file_path")"

    if [[ -z "${issues_by_key[$key]:-}" ]]; then
      issues_by_key[$key]=1
      agents_by_key[$key]="$agent"
      issue_count=$((issue_count + 1))
      severity_by_key[$key]="$severity"
      file_by_key[$key]="$file_path"
      task_by_key[$key]="$task"
      desc_by_key[$key]="$desc"
    else
      issues_by_key[$key]=$((${issues_by_key[$key]} + 1))
      agents_by_key[$key]="${agents_by_key[$key]}, $agent"
      if [[ $(severity_order "$severity") -lt $(severity_order "${severity_by_key[$key]}") ]]; then
        severity_by_key[$key]="$severity"
      fi
    fi
  done < <(parse_agent_output "$file" "$agent")
done

# Check if any issues found
if [[ $issue_count -eq 0 ]]; then
  echo "✅ No issues found - all agents passed"
  exit 0
fi

# Output header
echo "| Consensus | Severity | Issue | File | Task | Found By |"
echo "|-----------|----------|-------|------|------|----------|"

# Sort and output
{
  for key in "${!issues_by_key[@]}"; do
    count="${issues_by_key[$key]}"
    severity="${severity_by_key[$key]}"
    sev_num=$(severity_order "$severity")
    echo "${count}|${sev_num}|${key}"
  done
} | sort -t'|' -k1,1rn -k2,2n | while IFS='|' read -r count sev_num key; do
  severity="${severity_by_key[$key]}"
  desc="${desc_by_key[$key]}"
  file_path="${file_by_key[$key]}"
  task="${task_by_key[$key]}"
  agents="${agents_by_key[$key]}"

  echo "| [${count}/${TOTAL_AGENTS}] | ${severity} | ${desc} | ${file_path} | ${task} | ${agents} |"
done
