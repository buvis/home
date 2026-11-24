import { paths } from "./platform-paths.js";
import { powershell, psQuote, windowsArg } from "./platform-command.js";

export const STOP_LOOP = 'g="$1"; shift; for a in "$@"; do case "$a" in *:force) "$0" "$g" stop-server "${a%:force}" force;; *) "$0" "$g" stop-server "$a";; esac; done';
const DETACHED = 'nohup "$0" "$@" >/dev/null 2>&1 &';

const memoryGuardReason = "Memory is not available on Linux.";

export function systemApi(platform, run) {
  const status = (appHome) => platform === "windows"
    ? powershell(run, `$env:HERDR_APP_HOME=${psQuote(appHome)}; & herdr-app status; exit $LASTEXITCODE`)
    : run("sh", ["-c", 'HERDR_APP_HOME="$1" herdr-app status', "_", appHome]);
  const restart = (appHome) => platform === "windows"
    ? powershell(run, `Start-Process -FilePath powershell -WindowStyle Hidden -ArgumentList @('-NoProfile','-NonInteractive','-Command',${psQuote(`Start-Sleep -Seconds 1; $env:HERDR_APP_HOME=${psQuote(appHome)}; Start-Process herdr-app`)}) -ErrorAction Stop`)
    : run("sh", ["-c", '(sleep 1; HERDR_APP_HOME="$1" nohup herdr-app >/dev/null 2>&1 &) >/dev/null 2>&1', "_", appHome]);
  const battery = async () => {
    if (platform === "macos") {
      const r = await run("pmset", ["-g", "ps"]);
      return r.code === 0 ? /Battery Power/.test(r.stdout) : null;
    }
    const r = platform === "windows"
      ? await powershell(run, "Add-Type -AssemblyName System.Windows.Forms; [Windows.Forms.SystemInformation]::PowerStatus.PowerLineStatus.ToString()")
      : await run("sh", ["-c", 'for f in /sys/class/power_supply/*/online; do [ -f "$f" ] || continue; cat "$f"; done']);
    if (r.code !== 0 || !r.stdout.trim() || /Unknown/.test(r.stdout)) return null;
    return platform === "windows" ? r.stdout.trim() === "Offline" : !r.stdout.split(/\s+/).includes("1");
  };
  const hostname = ({ short = true } = {}) => platform === "windows" ? powershell(run, "[Environment]::MachineName") : run("hostname", short ? ["-s"] : []);
  const temporary = async () => {
    if (platform === "windows") return [(await powershell(run, "[IO.Path]::GetTempPath()")).stdout.trim()].filter(Boolean);
    const r = await run("sh", ["-c", 'printf %s "${TMPDIR:-/tmp}"']);
    return [...new Set([...(platform === "macos" ? ["/private/tmp"] : []), "/tmp", r.code === 0 ? r.stdout.trim() : ""].filter(Boolean))];
  };
  const userHome = async () => (platform === "windows" ? await powershell(run, "$HOME") : await run("sh", ["-c", 'printf %s "$HOME"'])).stdout.trim();
  const startDocker = () => platform === "macos" ? run("open", ["-a", "Docker"]) : platform === "windows"
    ? powershell(run, "Start-Process -FilePath (Join-Path $env:ProgramFiles 'Docker\\Docker\\Docker Desktop.exe') -ErrorAction Stop")
    : run("systemctl", ["--user", "start", "docker-desktop"]);
  const stopDocker = () => platform === "macos" ? run("osascript", ["-e", 'quit app "Docker"']) : platform === "windows" ? run("taskkill", ["/IM", "Docker Desktop.exe"]) : run("systemctl", ["--user", "stop", "docker-desktop"]);
  const hiddenGuard = (node, file, args, appHome) => {
    const start = `$child=Start-Process -FilePath ${psQuote(node)} -ArgumentList ${psQuote([file, ...args].map(windowsArg).join(" "))} -WindowStyle Hidden -PassThru -ErrorAction Stop`;
    const capture = args[0] === "install" && appHome
      ? `; for ($i=0; $i -lt 100; $i++) { $record=Get-Content -LiteralPath ${psQuote(paths.join(appHome, "data", "kanso-guard", "window-program.json"))} -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json -ErrorAction SilentlyContinue; if ($record.installerPid -eq $child.Id -or $child.HasExited) { break }; Start-Sleep -Milliseconds 100 }`
      : "";
    return powershell(run, `${appHome ? `$env:HERDR_APP_HOME=${psQuote(appHome)}; ` : ""}${start}${capture}`);
  };
  const guardRun = (node, file, args, appHome) => platform === "windows" ? hiddenGuard(node, file, args, appHome) : run("sh", ["-c", DETACHED, node, file, ...args]);
  const guardStop = (node, file, args) => platform === "windows"
    ? powershell(run, `Start-Process -FilePath powershell.exe -WindowStyle Hidden -ArgumentList ${psQuote(["-NoProfile", "-NonInteractive", "-Command", args.map((arg) => {
      const force = arg.endsWith(":force"), pid = force ? arg.slice(0, -6) : arg;
      return `& ${psQuote(node)} ${psQuote(file)} stop-server ${psQuote(pid)}${force ? " force" : ""}`;
    }).join("; ")].map(windowsArg).join(" "))} -ErrorAction Stop`)
    : run("sh", ["-c", DETACHED, "sh", "-c", STOP_LOOP, node, file, ...args]);
  const containerShell = (name, os) => ["docker", "exec", "-it", name, ...(os === "windows" ? ["cmd.exe"] : ["sh", "-c", "command -v bash >/dev/null 2>&1 && exec bash || exec sh"])];
  return { guardRun, guardStop, containerShell, status, restart, battery, hostname, temporary, userHome, startDocker, stopDocker, memoryGuardAvailable: platform === "macos" || platform === "windows", memoryGuardReason };
}
