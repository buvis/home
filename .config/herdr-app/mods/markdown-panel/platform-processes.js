import { fileApi } from "./platform-files.js";
import { paths } from "./platform-paths.js";
import { checked, jsonRows, powershell, unavailable, validPid, elapsedSeconds } from "./platform-command.js";

export const processTable = (rows) => ({ rows, byPid: new Map(rows.map((row) => [row.pid, row])), byParent: Map.groupBy(rows, (row) => row.ppid) });

export function unixProcesses(text) {
  return String(text ?? "").split(/\r?\n/).flatMap((line) => {
    const match = /^\s*(\d+)\s+(\d+)\s+(\S+)\s+(.*)$/.exec(line);
    return match ? [{ pid: Number(match[1]), ppid: Number(match[2]), etime: match[3], command: match[4] }] : [];
  });
}

export function windowsProcesses(text, now = Date.now()) {
  return jsonRows(text).map((row) => {
    const started = Date.parse(row.created);
    const seconds = Number.isFinite(started) ? Math.max(0, Math.floor((now - started) / 1000)) : 0;
    return { pid: Number(row.pid), ppid: Number(row.ppid), etime: `${Math.floor(seconds / 3600)}:${String(Math.floor(seconds / 60) % 60).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`, command: row.command || row.name || "", name: row.name || "", started: Number.isFinite(started) ? started : null, ...(row.executable ? { executable: row.executable } : {}), ...(row.bytes != null ? { bytes: Number(row.bytes) } : {}) };
  }).filter((row) => row.pid > 0);
}

export const lsofFields = (text) => {
  const lines = String(text ?? "").split(/\r?\n/), starts = lines.flatMap((line, i) => line[0] === "p" ? [i] : []);
  return starts.map((at, i) => ({ pid: Number(lines[at].slice(1)), fields: lines.slice(at + 1, starts[i + 1] ?? lines.length) }));
};

const LOOK_END = "kanso-look-end";
// One command: home, and for each pid whether it is alive and its session record. Alive is empty when the check itself failed.
const LOOK = String.raw`home=$(printf %s "$HOME")
printf '%s\n' "home=$home"
for pid in "$@"; do
  err=$(kill -0 "$pid" 2>&1)
  rc=$?
  alive=
  if [ "$rc" -eq 0 ]; then alive=1
  elif [ "$rc" -eq 1 ]; then
    case "$err" in
      *[Pp]ermission*|*[Nn]ot\ permitted*|*[Aa]ccess\ denied*) ;;
      *) alive=0 ;;
    esac
  fi
  printf '%s\n' "pid=$pid" "alive=$alive" record
  f="$home/.claude/sessions/$pid.json"
  if [ -f "$f" ]; then cat "$f" || true; fi
  printf '\n%s\n' "${LOOK_END}"
done`;
const windowsLook = (ids) => `$userHome = $env:USERPROFILE
Write-Output ('home=' + $userHome)
foreach ($id in @(${ids.join(",")})) {
  $alive = ''
  try {
    $proc = Get-Process -Id $id -ErrorAction Stop
    if ($proc) { $alive = '1' }
  } catch {
    $msg = ''
    if ($_.Exception) { $msg = [string]$_.Exception.Message }
    if ($msg -and $msg -notmatch 'permission|not permitted|access denied') { $alive = '0' }
  }
  Write-Output ('pid=' + $id)
  Write-Output ('alive=' + $alive)
  Write-Output 'record'
  try {
    $file = [IO.Path]::Combine($userHome, '.claude', 'sessions', ([string]$id + '.json'))
    if ([IO.File]::Exists($file)) { [IO.File]::ReadAllText($file) }
  } catch { }
  Write-Output '${LOOK_END}'
}`;
const readRecord = (body) => {
  if (!body) return null;
  try { return JSON.parse(body); } catch { return null; }
};
export function parseLook(text) {
  const lines = String(text ?? "").replace(/^\uFEFF/, "").split(/\r?\n/);
  const home = lines.find((line) => line.startsWith("home="))?.slice(5) ?? "";
  const scan = lines.reduce((state, line, i) => {
    if (i <= state.skip) return state;
    if (!line.startsWith("pid=")) return state;
    const pid = Number(line.slice(4));
    const aliveText = (lines[i + 1] ?? "").startsWith("alive=") ? lines[i + 1].slice(6) : "";
    const alive = aliveText === "1" ? true : aliveText === "0" ? false : null;
    const start = lines[i + 2] === "record" ? i + 3 : i + 2;
    const end = lines.findIndex((row, at) => at >= start && row === LOOK_END);
    const stop = end < 0 ? lines.length : end;
    const record = readRecord(lines.slice(start, stop).join("\n").trim());
    const pair = pid > 0 ? [[pid, { alive, record }]] : [];
    return { skip: stop, pairs: [...state.pairs, ...pair] };
  }, { skip: -1, pairs: [] });
  return { home, found: new Map(scan.pairs) };
}
const RUNNING = String.raw`d="$2"/.claude/sessions
if ! out=$(LC_ALL=C ls -d "$d" 2>&1); then case "$out" in *": No such file or directory") exit 0;; *) echo "can't look at $d: $out" >&2; exit 2;; esac; fi
if [ ! -r "$d" ] || [ ! -x "$d" ]; then echo "can't read $d" >&2; exit 2; fi
for f in "$d"/*.json; do
  [ -f "$f" ] || continue
  grep -qF "\"sessionId\":\"$1\"" "$f"; rc=$?
  if [ $rc -eq 1 ]; then continue; elif [ $rc -ne 0 ]; then echo "can't read $f" >&2; exit 2; fi
  p=$(basename "$f" .json)
  kill -0 "$p" 2>/dev/null || continue
  comm=$(LC_ALL=C ps -p "$p" -o comm= 2>/dev/null)
  [ "$(basename "$comm")" = claude ] || continue
  want=$(sed -n 's/.*"procStart":"\([^"]*\)".*/\1/p' "$f")
  if [ -n "$want" ]; then have=$(LC_ALL=C TZ=UTC ps -p "$p" -o lstart= 2>/dev/null | sed 's/^ *//;s/ *$//'); [ "$have" = "$want" ] || continue; fi
  echo "$p"; exit 0
done
exit 0`;
export function processApi(platform, run) {
  const list = async ({ pids, on } = {}) => {
    if (pids) pids.forEach(validPid);
    const options = on ? { on } : undefined;
    const rows = platform === "windows"
      ? windowsProcesses(checked(await powershell(run, "$ErrorActionPreference='Stop'; @(Get-CimInstance Win32_Process | ForEach-Object { @{pid=$_.ProcessId;ppid=$_.ParentProcessId;command=$_.CommandLine;name=$_.Name;executable=$_.ExecutablePath;bytes=$_.WorkingSetSize;created=$(if ($_.CreationDate) {$_.CreationDate.ToUniversalTime().ToString('o')} else {$null})} }) | ConvertTo-Json -Compress", options)).stdout)
      : unixProcesses(checked(await run("ps", ["-axo", "pid=,ppid=,etime=,command="], options)).stdout);
    return processTable(pids ? rows.filter((row) => pids.map(Number).includes(row.pid)) : rows);
  };
  const exists = async (pid, options) => {
    validPid(pid);
    if (platform === "windows") return (await list({ ...options, pids: [pid] })).byPid.has(Number(pid));
    const result = await run("kill", ["-0", String(pid)], options);
    if (result.code === 0) return true;
    return result.code === 1 && !/(?:permission|not permitted|access denied)/i.test(result.stderr ?? "") ? false : null;
  };
  const cwd = async (pids, options) => {
    pids.forEach(validPid);
    if (platform === "windows") return unavailable("Working directories of other processes");
    if (!pids.length) return { state: "ok", values: new Map() };
    const r = await run("lsof", ["-a", "-d", "cwd", "-p", pids.join(","), "-F", "pn"], options);
    if (r.code !== 0 && r.code !== 1) checked(r);
    return { state: "ok", values: new Map(lsofFields(r.stdout).flatMap(({ pid, fields }) => fields.filter((line) => line[0] === "n").map((line) => [pid, line.slice(1)]))) };
  };
  const openFiles = async (pids, options) => {
    pids.forEach(validPid);
    if (platform === "windows") return unavailable("Open files of other processes");
    if (!pids.length) return { state: "ok", values: [] };
    const r = await run("lsof", ["-a", "-p", pids.join(","), "-Fn"], options);
    if (r.code !== 0 && r.code !== 1) checked(r);
    return { state: "ok", values: lsofFields(r.stdout).flatMap(({ pid, fields }) => fields.filter((line) => line[0] === "n").map((line) => ({ pid, path: line.slice(1) }))) };
  };
  const startTime = async (pid, now = Date.now()) => {
    validPid(pid);
    if (platform === "windows") return (await list({ pids: [pid] })).byPid.get(Number(pid))?.started ?? NaN;
    const r = await run("ps", ["-o", "etime=", "-p", String(pid)]);
    return r.code === 0 && r.stdout.trim() ? now - elapsedSeconds(r.stdout.trim()) * 1000 : NaN;
  };
  const identity = async (pid, now = Date.now()) => {
    validPid(pid);
    if (platform === "windows") {
      const row = (await list({ pids: [pid] })).byPid.get(Number(pid));
      return row?.started != null ? { comm: row.name, start: row.started } : null;
    }
    const r = await run("ps", ["-p", String(pid), "-o", "etime=,comm="]);
    const match = r.code === 0 ? /^\s*(\S+)\s+(.+?)\s*$/.exec(r.stdout) : null;
    return match ? { comm: match[2], start: now - elapsedSeconds(match[1]) * 1000 } : null;
  };
  const memory = async () => {
    if (platform !== "windows") return run("ps", ["-axo", "pid=,rss=,comm="]);
    const rows = jsonRows(checked(await powershell(run, "$ErrorActionPreference='Stop'; @(Get-CimInstance Win32_Process | ForEach-Object { @{pid=$_.ProcessId;kb=[Math]::Ceiling([double]$_.WorkingSetSize/1024);comm=$_.Name} }) | ConvertTo-Json -Compress")).stdout);
    return { code: 0, stdout: rows.map((row) => `${row.pid} ${row.kb} ${row.comm}`).join("\n") };
  };
  const look = async (pids = []) => {
    const ids = pids.map((pid) => validPid(pid));
    if (platform === "windows") return parseLook(checked(await powershell(run, windowsLook(ids))).stdout);
    return parseLook(checked(await run("sh", ["-c", LOOK, "sh", ...ids])).stdout);
  };
  const runningSession = async (session, home) => {
    if (platform !== "windows") {
      const result = checked(await run("sh", ["-c", RUNNING, "sh", session, home]));
      const pid = Number(result.stdout.trim());
      return Number.isInteger(pid) && pid > 0 ? pid : null;
    }
    const files = fileApi(platform, run), directory = paths.join(home, ".claude", "sessions");
    if (!await files.test(directory, "directory")) return null;
    const records = (await files.directory(directory)).filter((entry) => !entry.dir && /^\d+\.json$/.test(entry.name));
    const table = await list();
    const found = await Promise.all(records.map(async (entry) => {
      const record = JSON.parse(await files.read(paths.join(directory, entry.name)));
      if (record.sessionId !== session) return null;
      const pid = Number(entry.name.slice(0, -5)), process = table.byPid.get(pid);
      if (!process || paths.basename(process.name).replace(/\.exe$/i, "").toLowerCase() !== "claude") return null;
      if (record.procStart) {
        const wanted = Date.parse(record.procStart);
        if (!Number.isFinite(wanted) || process.started == null) throw new Error("The conversation's process start could not be verified");
        if (Math.abs(wanted - process.started) > 2000) return null;
      }
      return pid;
    }));
    return found.find(Boolean) ?? null;
  };
  return { list, exists, cwd, openFiles, startTime, identity, memory, runningSession, look };
}
