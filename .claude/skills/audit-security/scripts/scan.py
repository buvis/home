#!/usr/bin/env python3
"""Static security scanner for ~/.claude/ configuration."""

import json
import re
import sys
from pathlib import Path


def scan_permissions(settings: dict, file_path: str) -> list[dict]:
    """Check permission allow/deny lists for security anti-patterns."""
    findings = []
    perms = settings.get("permissions", {})
    allow = perms.get("allow", [])
    deny = perms.get("deny", [])

    for entry in allow:
        if re.match(r"Bash\(\*\)", entry):
            findings.append({
                "severity": "critical",
                "category": "permissions",
                "file": file_path,
                "line": None,
                "description": "Bash(*) grants unrestricted shell access",
                "fix": "Restrict to specific commands: Bash(git *), Bash(npm *), etc.",
            })
        if re.match(r"(Write|Edit)\(\*\)", entry):
            findings.append({
                "severity": "high",
                "category": "permissions",
                "file": file_path,
                "line": None,
                "description": f"{entry} allows modifying any file on the system",
                "fix": "Restrict to project paths: Write(./src/**), Edit(./src/**)",
            })
        if re.match(r"\w+\(/\*\)", entry):
            findings.append({
                "severity": "high",
                "category": "permissions",
                "file": file_path,
                "line": None,
                "description": f"{entry} uses wildcard root path",
                "fix": "Restrict to specific directories",
            })
        sensitive_paths = ["~/.ssh/", "~/.aws/", "~/.gnupg/", "/etc/"]
        for sp in sensitive_paths:
            if sp in entry:
                findings.append({
                    "severity": "high",
                    "category": "permissions",
                    "file": file_path,
                    "line": None,
                    "description": f"Allow list includes sensitive path: {entry}",
                    "fix": f"Remove {sp} from allow list unless absolutely necessary",
                })

    if allow and not deny:
        findings.append({
            "severity": "medium",
            "category": "permissions",
            "file": file_path,
            "line": None,
            "description": "Allow list present but no deny list defined",
            "fix": "Add deny list for sensitive paths: .env, secrets/, credentials, SSH keys",
        })

    return findings


def scan_hooks(settings: dict, file_path: str, claude_dir: Path) -> list[dict]:
    """Check hook configurations for injection and suppression patterns."""
    findings = []
    hooks = settings.get("hooks", {})

    interpolation_re = re.compile(r"\$\{(file|command|content|input|tool_input|output)\}")
    suppression_re = re.compile(r"(2>/dev/null|\|\|\s*true|\|\|\s*exit\s+0)")
    scanned_scripts: set[str] = set()

    for hook_type, hook_entries in hooks.items():
        for entry in hook_entries:
            hook_list = entry.get("hooks", [])
            if not hook_list and "type" in entry:
                hook_list = [entry]

            for hook in hook_list:
                cmd = hook.get("command", "")

                if interpolation_re.search(cmd):
                    severity = "critical" if "sh -c" in cmd else "high"
                    findings.append({
                        "severity": severity,
                        "category": "hooks",
                        "file": file_path,
                        "line": None,
                        "description": f"Variable interpolation in {hook_type} hook command: {cmd}",
                        "fix": "Read tool_input from stdin JSON instead of interpolating into command string",
                    })

                if suppression_re.search(cmd):
                    findings.append({
                        "severity": "medium",
                        "category": "hooks",
                        "file": file_path,
                        "line": None,
                        "description": f"Silent error suppression in {hook_type} hook: {cmd}",
                        "fix": "Let errors propagate so security issues are visible",
                    })

                script_path = _resolve_hook_script(cmd, claude_dir)
                if script_path and script_path.is_file():
                    resolved = str(script_path.resolve())
                    if resolved not in scanned_scripts:
                        scanned_scripts.add(resolved)
                        findings.extend(_scan_hook_script(script_path, hook_type))

    return findings


def _resolve_hook_script(cmd: str, claude_dir: Path) -> Path | None:
    """Extract script path from a hook command string."""
    parts = cmd.split()
    for part in parts:
        if part.endswith(".sh") or part.endswith(".py"):
            expanded = part.replace("~/.claude/", str(claude_dir) + "/")
            expanded = expanded.replace("~/", str(Path.home()) + "/")
            return Path(expanded)
    return None


def _scan_hook_script(script_path: Path, hook_type: str) -> list[dict]:
    """Scan a hook script file for risky patterns."""
    findings = []
    try:
        content = script_path.read_text()
    except (OSError, UnicodeDecodeError):
        return findings

    lines = content.splitlines()
    interpolation_re = re.compile(r"\$\{(file|command|content|input|tool_input|output)\}")
    suppression_re = re.compile(r"(2>/dev/null|\|\|\s*true|\|\|\s*exit\s+0)")
    exfil_re = re.compile(r"(curl\s+.*(-X\s*POST|--data|-d\s)|wget\s+.*--post)", re.IGNORECASE)

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue

        if interpolation_re.search(line):
            findings.append({
                "severity": "high",
                "category": "hooks",
                "file": str(script_path),
                "line": i,
                "description": f"Variable interpolation in hook script",
                "fix": "Use jq to parse stdin JSON instead of shell interpolation",
            })

        if suppression_re.search(line):
            findings.append({
                "severity": "medium",
                "category": "hooks",
                "file": str(script_path),
                "line": i,
                "description": f"Silent error suppression in hook script",
                "fix": "Let errors propagate so security issues are visible",
            })

        if exfil_re.search(line):
            findings.append({
                "severity": "medium",
                "category": "hooks",
                "file": str(script_path),
                "line": i,
                "description": "Potential data exfiltration: HTTP POST in hook script",
                "fix": "Verify this outbound request is intentional and necessary",
            })

    if hook_type == "SessionStart":
        download_re = re.compile(r"(curl|wget)\s+.*\|\s*(sh|bash)", re.IGNORECASE)
        for i, line in enumerate(lines, 1):
            if download_re.search(line):
                findings.append({
                    "severity": "high",
                    "category": "hooks",
                    "file": str(script_path),
                    "line": i,
                    "description": "SessionStart hook downloads and executes a script",
                    "fix": "Pin scripts locally instead of fetching at runtime",
                })

    return findings


def scan_mcp(settings: dict, file_path: str) -> list[dict]:
    """Check MCP server configurations for risky patterns."""
    findings = []
    servers = settings.get("mcpServers", {})
    secret_re = re.compile(r"(sk-ant-[a-zA-Z0-9_-]{20,}|ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{20,}|AKIA[A-Z0-9]{16}|AIza[a-zA-Z0-9_-]{35})")

    for name, config in servers.items():
        cmd = config.get("command", "")
        args = config.get("args", [])
        all_parts = [cmd] + args

        if "npx" in cmd and "-y" in args:
            findings.append({
                "severity": "high",
                "category": "mcp",
                "file": file_path,
                "line": None,
                "description": f"MCP server '{name}' uses npx -y (auto-installs unreviewed packages)",
                "fix": "Install the package explicitly first, then reference it without -y",
            })

        for part in all_parts:
            if "0.0.0.0" in str(part):
                findings.append({
                    "severity": "high",
                    "category": "mcp",
                    "file": file_path,
                    "line": None,
                    "description": f"MCP server '{name}' binds to 0.0.0.0 (exposes to network)",
                    "fix": "Bind to 127.0.0.1 or localhost instead",
                })

        env = config.get("env", {})
        for key, val in env.items():
            if isinstance(val, str) and secret_re.search(val):
                findings.append({
                    "severity": "critical",
                    "category": "mcp",
                    "file": file_path,
                    "line": None,
                    "description": f"MCP server '{name}' has hardcoded secret in env.{key}",
                    "fix": "Use environment variable references instead of hardcoded values",
                })

    return findings


def scan_claude_md(claude_dir: Path) -> list[dict]:
    """Scan CLAUDE.md files for hardcoded secrets and risky instructions."""
    findings = []
    secret_patterns = [
        (r"sk-ant-[a-zA-Z0-9_-]{20,}", "Anthropic API key"),
        (r"ghp_[a-zA-Z0-9]{36}", "GitHub personal access token"),
        (r"github_pat_[a-zA-Z0-9_]{20,}", "GitHub fine-grained PAT"),
        (r"AKIA[A-Z0-9]{16}", "AWS access key"),
        (r"AIza[a-zA-Z0-9_-]{35}", "Google API key"),
        (r"Bearer\s+[a-zA-Z0-9_.-]{20,}", "Bearer token"),
    ]
    exec_re = re.compile(r"(curl\s+.*\|\s*(sh|bash)|wget\s+.*\|\s*(sh|bash))", re.IGNORECASE)

    md_files = list(claude_dir.glob("CLAUDE.md"))
    md_files.extend(claude_dir.glob("projects/*/CLAUDE.md"))

    for md_path in md_files:
        try:
            content = md_path.read_text()
        except (OSError, UnicodeDecodeError):
            continue

        lines = content.splitlines()
        for i, line in enumerate(lines, 1):
            for pattern, desc in secret_patterns:
                if re.search(pattern, line):
                    findings.append({
                        "severity": "critical",
                        "category": "secrets",
                        "file": str(md_path),
                        "line": i,
                        "description": f"Hardcoded {desc} found",
                        "fix": "Remove the secret and use environment variables instead",
                    })

            if exec_re.search(line):
                findings.append({
                    "severity": "high",
                    "category": "secrets",
                    "file": str(md_path),
                    "line": i,
                    "description": "URL execution instruction (curl/wget pipe to shell)",
                    "fix": "Download and review scripts before executing",
                })

    return findings


def add_line_numbers(findings: list[dict], file_path: str, content: str) -> None:
    """Try to add line numbers to findings that don't have them by searching file content."""
    lines = content.splitlines()
    for finding in findings:
        if finding["file"] != file_path or finding["line"] is not None:
            continue
        desc = finding["description"]
        for i, line in enumerate(lines, 1):
            if finding["category"] == "permissions":
                for entry_match in re.finditer(r'"([^"]*)"', line):
                    if entry_match.group(1) in desc:
                        finding["line"] = i
                        break
            if finding["line"] is not None:
                break


def scan(claude_dir: Path) -> dict:
    """Run all security checks and return findings."""
    findings = []

    settings_path = claude_dir / "settings.json"
    if settings_path.is_file():
        try:
            raw = settings_path.read_text()
            settings = json.loads(raw)
            sf = str(settings_path)
            findings.extend(scan_permissions(settings, sf))
            findings.extend(scan_hooks(settings, sf, claude_dir))
            findings.extend(scan_mcp(settings, sf))
            add_line_numbers(findings, sf, raw)
        except (json.JSONDecodeError, OSError):
            pass

    for project_settings in claude_dir.glob("projects/*/settings.json"):
        try:
            raw = project_settings.read_text()
            ps = json.loads(raw)
            psf = str(project_settings)
            findings.extend(scan_permissions(ps, psf))
            findings.extend(scan_hooks(ps, psf, claude_dir))
            findings.extend(scan_mcp(ps, psf))
            add_line_numbers(findings, psf, raw)
        except (json.JSONDecodeError, OSError):
            pass

    findings.extend(scan_claude_md(claude_dir))

    summary = {"critical": 0, "high": 0, "medium": 0}
    for f in findings:
        sev = f["severity"]
        if sev in summary:
            summary[sev] += 1

    return {"findings": findings, "summary": summary}


def main():
    claude_dir = Path.home() / ".claude"

    for arg in sys.argv[1:]:
        if arg.startswith("--claude-dir="):
            claude_dir = Path(arg.split("=", 1)[1])
        elif arg == "--claude-dir" and sys.argv.index(arg) + 1 < len(sys.argv):
            claude_dir = Path(sys.argv[sys.argv.index(arg) + 1])

    result = scan(claude_dir)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
