#!/usr/bin/env python3
"""Stop hook: analyze tool usage observations and create/update instincts.

Runs at session end. Reads observations since last analysis, applies pattern
detectors, creates or updates instinct files, and rebuilds project CLAUDE.md.

Python 3, stdlib only.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

INSTINCTS_ROOT = Path.home() / ".claude" / "instincts"
PROJECTS_DIR = INSTINCTS_ROOT / "projects"
REGISTRY_FILE = INSTINCTS_ROOT / "projects.json"


def detect_project() -> tuple[str, str, str]:
    """Determine project identity from git remote or path.

    Returns (hash, name, remote_url).
    """
    try:
        remote = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5
        )
        if remote.returncode == 0 and remote.stdout.strip():
            url = remote.stdout.strip()
            clean = re.sub(r"://[^@]+@", "://", url)
            h = hashlib.sha256(clean.encode()).hexdigest()[:12]
            name = Path(url.rstrip("/")).stem
            return h, name, clean
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    try:
        toplevel = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5
        )
        if toplevel.returncode == 0 and toplevel.stdout.strip():
            path = toplevel.stdout.strip()
            h = hashlib.sha256(path.encode()).hexdigest()[:12]
            return h, Path(path).name, ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return "global", "global", ""


def load_observations(project_hash: str, since: str | None) -> list[dict]:
    """Read JSONL observations since timestamp. Skip corrupted lines."""
    obs_file = PROJECTS_DIR / project_hash / "observations.jsonl"
    if not obs_file.exists():
        return []

    observations = []
    for line in obs_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if since and entry.get("ts", "") <= since:
            continue
        observations.append(entry)
    return observations


def get_last_analysis(project_hash: str) -> str | None:
    """Read last analysis timestamp."""
    ts_file = PROJECTS_DIR / project_hash / "last_analysis"
    if ts_file.exists():
        return ts_file.read_text(encoding="utf-8").strip() or None
    return None


def set_last_analysis(project_hash: str) -> None:
    """Write current timestamp as last analysis marker."""
    ts_file = PROJECTS_DIR / project_hash / "last_analysis"
    ts_file.parent.mkdir(parents=True, exist_ok=True)
    ts_file.write_text(
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        encoding="utf-8"
    )


def _extract_file_path(tool_input: dict | str) -> str:
    """Extract file_path from tool input (may be dict or JSON string)."""
    if isinstance(tool_input, dict):
        return tool_input.get("file_path", "")
    if isinstance(tool_input, str):
        try:
            parsed = json.loads(tool_input)
            if isinstance(parsed, dict):
                return parsed.get("file_path", "")
        except (json.JSONDecodeError, ValueError):
            pass
    return ""


def _extract_edit_content(tool_input: dict | str) -> str:
    """Extract the substantive content change from an Edit/Write input."""
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except (json.JSONDecodeError, ValueError):
            return ""
    if not isinstance(tool_input, dict):
        return ""
    # For Edit: old_string -> new_string is the change
    if "new_string" in tool_input:
        return f"{tool_input.get('old_string', '')}|{tool_input['new_string']}"
    # For Write: the content itself
    if "content" in tool_input:
        return tool_input["content"][:500]
    return ""


def detect_corrections(observations: list[dict]) -> list[dict]:
    """Detect user correction patterns (undo/redo on same file).

    Finds Edit/Write on file X followed within 2 tool calls by Edit/Write
    on the same file with different content. Requires 3+ occurrences.
    """
    edit_tools = {"Edit", "Write", "MultiEdit"}
    corrections: dict[str, list[dict]] = {}  # pattern_key -> list of evidence

    for i, obs in enumerate(observations):
        if obs.get("tool") not in edit_tools:
            continue
        fp = _extract_file_path(obs.get("in", {}))
        if not fp:
            continue
        content_a = _extract_edit_content(obs.get("in", {}))

        # Look at next 2 tool calls for same-file edit with different content
        for j in range(i + 1, min(i + 3, len(observations))):
            next_obs = observations[j]
            if next_obs.get("tool") not in edit_tools:
                continue
            next_fp = _extract_file_path(next_obs.get("in", {}))
            if next_fp != fp:
                continue
            content_b = _extract_edit_content(next_obs.get("in", {}))
            if content_a and content_b and content_a != content_b:
                # Normalize key: strip path-specific parts, keep file extension
                ext = Path(fp).suffix or "unknown"
                pattern_key = f"correction-{ext}-{obs.get('tool')}"
                if pattern_key not in corrections:
                    corrections[pattern_key] = []
                corrections[pattern_key].append({
                    "ts": obs.get("ts", ""),
                    "sid": obs.get("sid", ""),
                    "file": fp,
                    "tool": obs.get("tool", ""),
                    "original": content_a[:200],
                    "corrected": content_b[:200],
                })
                break  # Only count once per initial edit

    # Filter: require 3+ occurrences (PRD conservative threshold)
    candidates = []
    for key, evidence in corrections.items():
        if len(evidence) < 3:
            continue
        candidates.append({
            "type": "correction",
            "id": key,
            "description": f"Correction pattern detected on {evidence[0].get('tool', 'Edit')} calls",
            "observation_count": len(evidence),
            "evidence": evidence,
        })
    return candidates


def _normalize_tool_input(tool_input: dict | str) -> str:
    """Normalize tool input by stripping file-specific details."""
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except (json.JSONDecodeError, ValueError):
            return ""
    if not isinstance(tool_input, dict):
        return ""
    # Keep tool structure but strip paths, line numbers, specific content
    normalized = {}
    for k, v in tool_input.items():
        if k in ("file_path", "path", "command"):
            # Keep key but generalize value
            if k == "file_path" and isinstance(v, str):
                normalized[k] = Path(v).suffix or "file"
            elif k == "command" and isinstance(v, str):
                # Keep just the binary name
                normalized[k] = v.split()[0] if v.split() else ""
            else:
                normalized[k] = "path"
        elif k in ("old_string", "new_string", "content", "pattern"):
            normalized[k] = "content"
        else:
            normalized[k] = str(v)[:50]
    return json.dumps(normalized, sort_keys=True)


def detect_sequences(observations: list[dict]) -> list[dict]:
    """Detect repeated tool call sequences (3+ tools appearing 3+ times).

    Uses sliding window approach, normalizes by removing file-specific details.
    """
    if len(observations) < 3:
        return []

    # Build normalized tool signatures
    signatures = []
    for obs in observations:
        tool = obs.get("tool", "")
        norm_input = _normalize_tool_input(obs.get("in", {}))
        signatures.append(f"{tool}:{norm_input}")

    # Find repeated sequences of length 3-5
    sequence_counts: dict[str, list[int]] = {}
    for window_size in (3, 4, 5):
        for i in range(len(signatures) - window_size + 1):
            seq = tuple(signatures[i:i + window_size])
            seq_key = " -> ".join(seq)
            if seq_key not in sequence_counts:
                sequence_counts[seq_key] = []
            sequence_counts[seq_key].append(i)

    # Filter: require 3+ occurrences, non-overlapping
    candidates = []
    for seq_key, positions in sequence_counts.items():
        # Remove overlapping occurrences
        non_overlapping = [positions[0]]
        tools = seq_key.split(" -> ")
        window = len(tools)
        for pos in positions[1:]:
            if pos >= non_overlapping[-1] + window:
                non_overlapping.append(pos)
        if len(non_overlapping) < 3:
            continue

        tool_names = [t.split(":")[0] for t in tools]
        seq_id = f"sequence-{'-'.join(tool_names).lower()}"
        evidence = []
        for pos in non_overlapping[:5]:
            if pos < len(observations):
                evidence.append({
                    "ts": observations[pos].get("ts", ""),
                    "sid": observations[pos].get("sid", ""),
                    "position": pos,
                })
        candidates.append({
            "type": "sequence",
            "id": seq_id,
            "description": f"Repeated sequence: {' -> '.join(tool_names)}",
            "observation_count": len(non_overlapping),
            "evidence": evidence,
        })
    return candidates


_ERROR_PATTERNS = re.compile(
    r"(error|Error|ERROR|failed|FAILED|exception|Exception|"
    r"command not found|No such file|Permission denied|"
    r"ModuleNotFoundError|ImportError|FileNotFoundError|"
    r"exit code [1-9]|returned non-zero|ENOENT|EACCES)",
)

_NOISE_RE = re.compile(
    r"(/[^\s:]+)|(\bline \d+\b)|(\b0x[0-9a-f]+\b)|(\"[^\"]{20,}\")",
    re.IGNORECASE,
)


def _normalize_error(output: str) -> str:
    """Normalize error message by stripping paths, line numbers, hex values."""
    output = output[:500]
    return _NOISE_RE.sub("_", output).strip()


def _normalize_fix(tool: str, tool_input: dict | str) -> str:
    """Normalize a fix action to a comparable signature."""
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except (json.JSONDecodeError, ValueError):
            return f"{tool}:raw"
    if not isinstance(tool_input, dict):
        return f"{tool}:unknown"

    if tool == "Bash":
        cmd = tool_input.get("command", "")
        binary = cmd.split()[0] if cmd.split() else ""
        return f"Bash:{binary}"
    if tool == "Edit":
        ext = Path(tool_input.get("file_path", "")).suffix
        return f"Edit:{ext}"
    return f"{tool}:generic"


def detect_error_fixes(observations: list[dict]) -> list[dict]:
    """Detect Bash errors followed by consistent fix patterns.

    Finds Bash tool calls with error output followed by a fix action.
    Requires 3+ occurrences of the same error class resolved the same way.
    """
    error_fix_pairs: dict[str, list[dict]] = {}  # key -> evidence list

    for i, obs in enumerate(observations):
        if obs.get("tool") != "Bash":
            continue
        output = str(obs.get("out", ""))
        if not _ERROR_PATTERNS.search(output):
            continue

        error_class = _normalize_error(output)

        # Look at next 3 tool calls for a fix
        for j in range(i + 1, min(i + 4, len(observations))):
            fix_obs = observations[j]
            fix_tool = fix_obs.get("tool", "")
            fix_sig = _normalize_fix(fix_tool, fix_obs.get("in", {}))

            pair_key = f"{error_class}||{fix_sig}"
            if pair_key not in error_fix_pairs:
                error_fix_pairs[pair_key] = []
            error_fix_pairs[pair_key].append({
                "ts": obs.get("ts", ""),
                "sid": obs.get("sid", ""),
                "error": output[:200],
                "fix_tool": fix_tool,
                "fix_sig": fix_sig,
            })
            break  # Only match first fix per error

    candidates = []
    for key, evidence in error_fix_pairs.items():
        if len(evidence) < 3:
            continue
        error_part = key.split("||")[0][:80]
        fix_part = key.split("||")[1] if "||" in key else "unknown"
        candidates.append({
            "type": "error_fix",
            "id": f"error-fix-{fix_part.replace(':', '-').lower()}",
            "description": f"Error '{error_part}' consistently fixed with {fix_part}",
            "observation_count": len(evidence),
            "evidence": evidence,
        })
    return candidates


def _slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:60].strip("-")


def _initial_confidence(count: int) -> float:
    """Calculate initial confidence from observation count."""
    if count >= 11:
        return 0.85
    if count >= 6:
        return 0.7
    if count >= 3:
        return 0.5
    return 0.3


def _parse_instinct_frontmatter(content: str) -> dict:
    """Parse YAML frontmatter from instinct file."""
    if not content.startswith("---"):
        return {}
    end = content.find("---", 3)
    if end == -1:
        return {}
    frontmatter = content[3:end].strip()
    result = {}
    for line in frontmatter.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"')
            if key in ("confidence", "observations"):
                try:
                    value = float(value) if "." in value else int(value)
                except ValueError:
                    pass
            result[key] = value
    return result


def _build_trigger(candidate: dict) -> str:
    """Generate a trigger description from the candidate."""
    ctype = candidate.get("type", "")
    desc = candidate.get("description", "")
    if ctype == "correction":
        return f"when editing files ({desc})"
    if ctype == "sequence":
        return f"when performing workflow ({desc})"
    if ctype == "error_fix":
        return f"when encountering errors ({desc})"
    return f"when {desc}"


def _build_evidence_section(evidence: list[dict]) -> str:
    """Format evidence list as markdown bullets."""
    lines = []
    for e in evidence[:10]:
        ts = e.get("ts", "unknown")
        sid = e.get("sid", "unknown")[:8]
        detail = ""
        if "file" in e:
            detail = f" on {e['file']}"
        elif "error" in e:
            detail = f" - {e['error'][:80]}"
        lines.append(f"- Observed {ts} (session {sid}){detail}")
    return "\n".join(lines)


def create_or_update_instinct(candidate: dict, project_hash: str) -> None:
    """Create or update an instinct file from a detector candidate.

    Confidence rules:
    - New: based on observation count (0.3/0.5/0.7/0.85)
    - Existing confirming: +0.05 (cap 0.9)
    - Existing contradicting: -0.1 (floor 0.1)
    """
    instinct_id = _slugify(candidate.get("id", "unknown"))
    if not instinct_id:
        return

    instinct_dir = PROJECTS_DIR / project_hash / "instincts"
    instinct_dir.mkdir(parents=True, exist_ok=True)
    instinct_file = instinct_dir / f"{instinct_id}.md"

    obs_count = candidate.get("observation_count", 1)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Contradicting observations only weaken existing instincts, never create new ones
    if candidate.get("contradicting") and not instinct_file.exists():
        return

    if instinct_file.exists():
        existing = instinct_file.read_text(encoding="utf-8")
        meta = _parse_instinct_frontmatter(existing)
        old_confidence = float(meta.get("confidence", 0.3))
        old_obs = int(meta.get("observations", 0))

        # Contradicting: -0.1 (floor 0.1), Confirming: +0.05 (cap 0.9)
        if candidate.get("contradicting"):
            new_confidence = max(0.1, old_confidence - 0.1)
        else:
            new_confidence = min(0.9, old_confidence + 0.05)
        new_obs = old_obs + obs_count

        # Update frontmatter values in place
        existing = re.sub(
            r"^confidence:.*$", f"confidence: {new_confidence:.2f}",
            existing, count=1, flags=re.MULTILINE
        )
        existing = re.sub(
            r"^last_updated:.*$", f"last_updated: {today}",
            existing, count=1, flags=re.MULTILINE
        )
        existing = re.sub(
            r"^observations:.*$", f"observations: {new_obs}",
            existing, count=1, flags=re.MULTILINE
        )
        # Append new evidence
        new_evidence = _build_evidence_section(candidate.get("evidence", []))
        existing = existing.rstrip() + "\n" + new_evidence + "\n"
        instinct_file.write_text(existing, encoding="utf-8")
    else:
        confidence = _initial_confidence(obs_count)
        trigger = _build_trigger(candidate)
        evidence = _build_evidence_section(candidate.get("evidence", []))
        description = candidate.get("description", "Detected pattern")

        content = f"""---
id: {instinct_id}
trigger: "{trigger}"
confidence: {confidence:.2f}
domain: {candidate.get('type', 'workflow')}
scope: project
project_id: {project_hash}
created: {today}
last_updated: {today}
observations: {obs_count}
---
## Action
{description}

## Evidence
{evidence}
"""
        instinct_file.write_text(content, encoding="utf-8")


def _get_project_claude_md_path() -> Path | None:
    """Determine project CLAUDE.md path from current git context."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            project_root = result.stdout.strip()
            encoded = project_root.replace("/", "-")
            return Path.home() / ".claude" / "projects" / encoded / "CLAUDE.md"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def rebuild_claude_md(project_hash: str) -> None:
    """Regenerate instincts section in project CLAUDE.md.

    Reads all instinct files, filters to confidence >= 0.5, writes between
    <!-- INSTINCTS:START --> and <!-- INSTINCTS:END --> markers.
    """
    instinct_dir = PROJECTS_DIR / project_hash / "instincts"
    if not instinct_dir.exists():
        return

    # Collect active instincts
    active_instincts = []
    for instinct_file in sorted(instinct_dir.glob("*.md")):
        content = instinct_file.read_text(encoding="utf-8")
        meta = _parse_instinct_frontmatter(content)
        confidence = float(meta.get("confidence", 0))
        if confidence < 0.5:
            continue
        trigger = meta.get("trigger", "").strip('"')
        # Extract action from ## Action section
        action = ""
        in_action = False
        for line in content.splitlines():
            if line.startswith("## Action"):
                in_action = True
                continue
            if line.startswith("## ") and in_action:
                break
            if in_action and line.strip():
                action = line.strip()
                break
        active_instincts.append({
            "id": meta.get("id", instinct_file.stem),
            "trigger": trigger,
            "action": action,
            "confidence": confidence,
        })

    claude_md_path = _get_project_claude_md_path()
    if not claude_md_path:
        return

    start_marker = "<!-- INSTINCTS:START -->"
    end_marker = "<!-- INSTINCTS:END -->"

    # Read existing content
    existing = ""
    if claude_md_path.exists():
        existing = claude_md_path.read_text(encoding="utf-8")

    if not active_instincts:
        # Remove markers section if no active instincts
        if start_marker in existing:
            before = existing[:existing.index(start_marker)]
            after_idx = existing.index(end_marker) + len(end_marker)
            after = existing[after_idx:]
            cleaned = (before.rstrip() + "\n" + after.lstrip()).strip()
            if cleaned:
                claude_md_path.write_text(cleaned + "\n", encoding="utf-8")
        return

    # Build instincts section
    lines = [start_marker, "", "## Learned Instincts", ""]
    for inst in active_instincts:
        lines.append(
            f"- **{inst['trigger']}**: {inst['action']} "
            f"(confidence: {inst['confidence']:.2f})"
        )
    lines.extend(["", end_marker])
    instincts_block = "\n".join(lines)

    if start_marker in existing and end_marker in existing:
        # Replace existing section
        before = existing[:existing.index(start_marker)]
        after = existing[existing.index(end_marker) + len(end_marker):]
        new_content = before + instincts_block + after
    elif existing:
        # Append to existing file
        new_content = existing.rstrip() + "\n\n" + instincts_block + "\n"
    else:
        # Create new file
        claude_md_path.parent.mkdir(parents=True, exist_ok=True)
        new_content = instincts_block + "\n"

    claude_md_path.write_text(new_content, encoding="utf-8")


def main() -> None:
    # Read Stop hook payload from stdin
    try:
        json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        pass

    # Skip automated sessions
    session_name = os.environ.get("CLAUDE_SESSION_NAME", "")
    if any(kw in session_name for kw in ("autopilot", "de-sloppify")):
        return

    project_hash, _, _ = detect_project()

    # Ensure project directory exists
    proj_dir = PROJECTS_DIR / project_hash
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "instincts").mkdir(exist_ok=True)

    # Load recent observations (since last analysis) for correction/error-fix detectors
    since = get_last_analysis(project_hash)
    recent_observations = load_observations(project_hash, since)
    if not recent_observations:
        return

    # Load ALL observations for sequence detector (cross-session patterns)
    all_observations = load_observations(project_hash, None)

    # Run detectors
    candidates = []
    candidates.extend(detect_corrections(recent_observations))
    candidates.extend(detect_sequences(all_observations))
    candidates.extend(detect_error_fixes(recent_observations))

    # Create/update instincts from candidates
    for candidate in candidates:
        create_or_update_instinct(candidate, project_hash)

    # Rebuild project CLAUDE.md with active instincts
    rebuild_claude_md(project_hash)

    # Mark analysis complete
    set_last_analysis(project_hash)


if __name__ == "__main__":
    main()
