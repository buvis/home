import { checked, jsonRows, powershell, psQuote, windowsArg } from "./platform-command.js";

// 2097150 is a multiple of 3, so only the last read slice's base64 is padded. A write uses WRITE_RAW.
export const CHUNK = 2097150;
// Write chunks stay under Linux 131072 bytes per argument, macOS 1048576 for argv plus the environment, and Windows 32767 for the command line.
export const WRITE_RAW = { linux: 90000, macos: 210000, windows: 4500 };
const WIN_LINE = "powershell.exe -NoProfile -NonInteractive -Command ".length + "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); ".length + 2;
export const windowsCommandLength = (script) => WIN_LINE + String(script).length;
const B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

class Utf8 {
  constructor() { this.raw = []; this.n = 0; }

  add(b) { this.raw[this.n] = b & 255; this.n = this.n + 1; return this; }

  put(cp) {
    if (cp < 0x80) return this.add(cp);
    if (cp < 0x800) return this.add(0xc0 | (cp >> 6)).add(0x80 | (cp & 63));
    if (cp < 0x10000) return this.add(0xe0 | (cp >> 12)).add(0x80 | ((cp >> 6) & 63)).add(0x80 | (cp & 63));
    return this.add(0xf0 | (cp >> 18)).add(0x80 | ((cp >> 12) & 63)).add(0x80 | ((cp >> 6) & 63)).add(0x80 | (cp & 63));
  }
}

const bytesOf = (text) => [...String(text ?? "")].reduce((out, ch) => out.put(ch.codePointAt(0)), new Utf8());

const encodeSlice = (raw, start, end) => Array.from({ length: Math.ceil((end - start) / 3) }, (_, group) => {
  const i = start + group * 3;
  const b0 = raw[i];
  const b1 = i + 1 < end ? raw[i + 1] : null;
  const b2 = i + 2 < end ? raw[i + 2] : null;
  return B64[b0 >> 2] + B64[((b0 & 3) << 4) | ((b1 ?? 0) >> 4)] + (b1 == null ? "=" : B64[((b1 & 15) << 2) | ((b2 ?? 0) >> 6)]) + (b2 == null ? "=" : B64[b2 & 63]);
}).join("");

export const base64Chunks = (text, chunk = CHUNK) => {
  const { raw, n } = bytesOf(text);
  if (n === 0) return [""];
  return Array.from({ length: Math.ceil(n / chunk) }, (_, i) => encodeSlice(raw, i * chunk, Math.min(n, (i + 1) * chunk)));
};

export class SaveConflict extends Error {
  constructor() { super("changed on disk"); this.conflict = true; }
}

// GNU stat and base64 on a Mac PATH do not speak the system flags.
const bin = (platform, name) => platform === "macos" ? `/usr/bin/${name}` : name;

const unixScript = (platform) => {
  const stat = `${bin(platform, "stat")} ${platform === "macos" ? "-L -f %z" : "-L -c %s"}`;
  const hash = platform === "macos" ? `${bin(platform, "shasum")} -a 256` : "sha256sum";
  const b64 = `${bin(platform, "base64")} ${platform === "macos" ? "-D" : "-d"}`;
  return [
    "target=$1",
    "textb64=$2",
    "expb64=$3",
    "mode=$4",
    "phase=$5",
    "dir=$6",
    'if [ "$phase" = shot ] || [ "$phase" = begin ]; then dir=$(mktemp -d) || exit 1; fi',
    'cleanup() { status=$?; trap - EXIT; if [ -n "$dir" ]; then rm -rf "$dir"; fi; exit "$status"; }',
    "trap cleanup EXIT",
    'if [ -n "$textb64" ]; then',
    `  if [ "$phase" = more ] || [ "$phase" = end ]; then printf %s "$textb64" | ${b64} >> "$dir/new" || exit 1`,
    `  else printf %s "$textb64" | ${b64} > "$dir/new" || exit 1; fi`,
    'elif [ "$phase" = shot ] || [ "$phase" = begin ]; then : > "$dir/new"; fi',
    'if [ "$mode" = match ]; then',
    '  if [ -n "$expb64" ]; then',
    `    if [ "$phase" = more ] || [ "$phase" = end ]; then printf %s "$expb64" | ${b64} >> "$dir/exp" || exit 1`,
    `    else printf %s "$expb64" | ${b64} > "$dir/exp" || exit 1; fi`,
    '  elif [ "$phase" = shot ] || [ "$phase" = begin ]; then : > "$dir/exp"; fi',
    "fi",
    'if [ "$phase" = begin ] || [ "$phase" = more ]; then trap - EXIT; printf %s "$dir"; exit 0; fi',
    'if [ "$mode" = create ]; then if [ -e "$target" ] || [ -L "$target" ]; then exit 3; fi',
    'else',
    '  if [ ! -f "$target" ]; then exit 3; fi',
    `  s1=$(${stat} "$target") || exit 1`,
    `  s2=$(${stat} "$dir/exp") || exit 1`,
    '  [ "$s1" = "$s2" ] || exit 3',
    `  h1=$(${hash} "$target") || exit 1`,
    `  h2=$(${hash} "$dir/exp") || exit 1`,
    '  [ "${h1%% *}" = "${h2%% *}" ] || exit 3',
    "fi",
    'cat "$dir/new" > "$target"',
  ].join("\n");
};

const winPut = (b64, dest, append) => {
  const quoted = psQuote(b64 ?? "");
  if (append) return b64
    ? `$extra=[Convert]::FromBase64String(${quoted}); $out=[IO.File]::Open(${dest},'Append','Write','Read'); try { $out.Write($extra,0,$extra.Length) } finally { $out.Dispose() }`
    : "";
  return `if ([string]::IsNullOrEmpty(${quoted})) { [IO.File]::WriteAllBytes(${dest}, [byte[]]::new(0)) } else { [IO.File]::WriteAllBytes(${dest}, [Convert]::FromBase64String(${quoted})) }`;
};

const winScript = ({ path, textB64, expB64, mode, phase, dir }) => {
  const fresh = phase === "shot" || phase === "begin";
  const keep = phase === "begin" || phase === "more";
  const start = fresh
    ? "$dir=Join-Path $env:TEMP ('kanso-'+[guid]::NewGuid().ToString('N')); New-Item -ItemType Directory -Path $dir | Out-Null"
    : `$dir=${psQuote(dir)}`;
  const compare = mode === "create"
    ? "if (Test-Path -LiteralPath $target) { $code = 3 }"
    : "if (-not (Test-Path -LiteralPath $target)) { $code = 3 } else { $ra=[IO.File]::Open($target,'Open','Read','ReadWrite'); $rb=[IO.File]::Open($expected,'Open','Read','Read'); try { if ($ra.Length -ne $rb.Length) { $code = 3 } } finally { $ra.Dispose(); $rb.Dispose() }; if ($code -eq 0 -and (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $expected -Algorithm SHA256).Hash) { $code = 3 } }";
  const put = "if ($code -eq 0) { $bytes=[IO.File]::ReadAllBytes($new); if (Test-Path -LiteralPath $target) { $fs=[IO.File]::Open($target,'Open','Write','Read'); try { $fs.SetLength(0); $fs.Write($bytes,0,$bytes.Length) } finally { $fs.Dispose() } } else { [IO.File]::WriteAllBytes($target,$bytes) } }";
  const body = [
    winPut(textB64, "$new", !fresh),
    mode === "match" ? winPut(expB64, "$expected", !fresh) : "",
    keep ? "$keep=$true; [Console]::Out.Write($dir)" : compare,
    keep ? "" : put,
  ].filter(Boolean).join("; ");
  return `${start}; $code=0; $keep=$false; $target=${psQuote(path)}; $new=Join-Path $dir 'new'; $expected=Join-Path $dir 'exp'; try { ${body} } finally { if (-not $keep -and (Test-Path -LiteralPath $dir)) { Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue } }; if ($code -ne 0) { exit $code }`;
};

const writeStep = (platform, path, textB64, expB64, mode, phase) => platform === "windows"
  ? { script: (dir) => winScript({ path, textB64, expB64, mode, phase, dir }), keeps: phase === "begin" || phase === "more" }
  : { cmd: "sh", args: (dir) => ["-c", unixScript(platform), "put", path, textB64, expB64, mode, phase, dir ?? ""], keeps: phase === "begin" || phase === "more" };

export const writeSteps = (platform, path, text, expected) => {
  const raw = WRITE_RAW[platform] ?? WRITE_RAW.linux;
  const parts = base64Chunks(text, raw);
  const expParts = expected == null ? null : base64Chunks(expected, raw);
  const mode = expected == null ? "create" : "match";
  const one = parts.length === 1 && (expParts == null || expParts.length <= 1);
  const rounds = one ? 1 : Math.max(parts.length, expParts?.length ?? 1);
  return Array.from({ length: rounds }, (_, i) => writeStep(
    platform, path, parts[i] ?? "", expParts ? (expParts[i] ?? "") : "", mode,
    one ? "shot" : i === 0 ? "begin" : i === rounds - 1 ? "end" : "more",
  ));
};

// find prints each directory twice in a row, so its type costs no extra call.
export const pairEntries = (raw) => {
  const names = raw.slice(0, 2 * (500 + 2)).map((name) => name.slice(2));
  const paired = names.reduce((out, name) => [...out, name === names[out.length - 1] && !out.at(-1)], []);
  return names.flatMap((name, i) => (paired[i] ? [] : [{ name, dir: paired[i + 1] === true }])).slice(0, 500 + 1);
};

const unixTree = (platform) => {
  const stat = `${bin(platform, "stat")} ${platform === "macos" ? "-L -f '%z %m'" : "-L -c '%s %Y'"}`;
  return [
    "root=$1",
    "shift",
    `stamp=$(${stat} "$root") || exit 1`,
    "printf '\\005%s\\000' \"$stamp\"",
    "for rel in \"$@\"; do",
    "  if [ -n \"$rel\" ]; then dir=\"$root/$rel\"; else dir=\"$root\"; fi",
    "  printf '\\001%s\\000' \"$rel\"",
    "  find -H \"$dir\" -mindepth 1 -maxdepth 1 ! -name .git \\( -type d -print0 -print0 -o -print0 \\) || exit 1",
    "  printf '\\002\\000'",
    "done",
    "top=$(git -C \"$root\" rev-parse --show-toplevel 2>/dev/null) || top=",
    "printf '\\003%s\\000' \"$top\"",
    "if [ -n \"$top\" ]; then git -C \"$root\" status --porcelain=v1 -z --no-renames --untracked-files=normal 2>/dev/null | tr '\\000' '\\n'; printf '\\000'; fi",
    "printf '\\004\\000'",
  ].join("\n");
};

const winTree = (root, rels) => `
$root = ${psQuote(root)}
$rels = @(${rels.map(psQuote).join(",")})
$item = Get-Item -LiteralPath $root
$stamp = '{0} {1}' -f $item.Length, ([DateTimeOffset]$item.LastWriteTimeUtc).ToUnixTimeSeconds()
[Console]::Out.Write([string][char]5 + $stamp + [char]0)
foreach ($rel in $rels) {
  $dir = if ([string]::IsNullOrEmpty($rel)) { $root } else { Join-Path $root $rel }
  [Console]::Out.Write([string][char]1 + $rel + [char]0)
  foreach ($row in @(Get-ChildItem -LiteralPath $dir -Force | Where-Object { $_.Name -ne '.git' } | Select-Object -First 501)) {
    $kind = if ($row.PSIsContainer -and -not ($row.Attributes -band [IO.FileAttributes]::ReparsePoint)) { 'd' } else { 'f' }
    [Console]::Out.Write($kind + [char]9 + $row.Name + [char]0)
  }
  [Console]::Out.Write([string][char]2 + [char]0)
}
$top = ''
& git -C $root rev-parse --show-toplevel 2>$null | ForEach-Object { $top = "$_".Trim() }
[Console]::Out.Write([string][char]3 + $top + [char]0)
if ($top) {
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = 'git'
  $psi.Arguments = '-C ' + ${windowsArg(root)} + ' status --porcelain=v1 -z --no-renames --untracked-files=normal'
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $false
  $psi.UseShellExecute = $false
  $psi.StandardOutputEncoding = [Text.UTF8Encoding]::new($false)
  $proc = [System.Diagnostics.Process]::Start($psi)
  $text = $proc.StandardOutput.ReadToEnd().Replace([char]0, [char]10)
  $proc.WaitForExit()
  [Console]::Out.Write($text)
}
[Console]::Out.Write([string][char]0 + [char]4 + [char]0)
`;

export function fileApi(platform, run) {
  const ps = (script, options) => powershell(run, "$ErrorActionPreference='Stop'; " + script, options);
  const mkdir = (path, options) => platform === "windows" ? ps(`[IO.Directory]::CreateDirectory(${psQuote(path)}) | Out-Null`, options) : run("mkdir", ["-p", path], options);
  const remove = (paths, { recursive = false, ...options } = {}) => platform === "windows"
    ? ps(`foreach ($path in @(${paths.map(psQuote).join(",")})) { if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force${recursive ? " -Recurse" : ""} } }`, options)
    : run("rm", [recursive ? "-rf" : "-f", ...paths], options);
  const copy = (from, to, options) => platform === "windows" ? ps(`Copy-Item -LiteralPath ${psQuote(from)} -Destination ${psQuote(to)} -Force`, options) : run("cp", ["-f", from, to], options);
  const move = (from, to, options) => platform === "windows" ? ps(`Move-Item -LiteralPath ${psQuote(from)} -Destination ${psQuote(to)} -Force`, options) : run("mv", ["-f", from, to], options);
  const test = async (path, kind = "file", options) => {
    const r = platform === "windows"
      ? await ps(`if (${kind === "nonempty" ? `(Test-Path -LiteralPath ${psQuote(path)} -PathType Leaf) -and (Get-Item -LiteralPath ${psQuote(path)}).Length -gt 0` : `Test-Path -LiteralPath ${psQuote(path)}${kind === "directory" ? " -PathType Container" : kind === "file" ? " -PathType Leaf" : ""}`}) { exit 0 } else { exit 1 }`, options)
      : await run("test", [kind === "directory" ? "-d" : kind === "nonempty" ? "-s" : kind === "file" ? "-f" : "-e", path], options);
    if (r.code !== 0 && (r.code !== 1 || platform === "windows" && r.stderr?.trim())) checked(r);
    return r.code === 0;
  };
  const directory = async (path, options) => {
    if (platform === "windows") return jsonRows(checked(await ps(`@(Get-ChildItem -LiteralPath ${psQuote(path)} -Force | Where-Object { $_.Name -ne '.git' } | Select-Object -First 501 | ForEach-Object { @{name=$_.Name;dir=($_.PSIsContainer -and -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint))} }) | ConvertTo-Json -Compress`, options)).stdout);
  // -H follows only the folder itself (a link to a folder should open); entries are not followed.
  const fast = await run("find", ["-H", ".", "-mindepth", "1", "-maxdepth", "1", "!", "-name", ".git",
    "(", "-type", "d", "-print0", "-print0", "-o", "-print0", ")"], { ...options, cwd: path }).catch(() => null);
  if (fast?.code === 0) return pairEntries(fast.stdout.split("\0").slice(0, -1));
  // Fallback when find is missing or its output would pass exec's limit; one extra entry detects truncation.
  const script = `
n=0
find -H "$1" -mindepth 1 -maxdepth 1 ! -name .git -print0 2>/dev/null |
while IFS= read -r -d '' p; do
  name=\${p##*/}
  if [ -d "$p" ] && [ ! -L "$p" ]; then kind=d; else kind=f; fi
  printf '%s\\0%s\\0' "$kind" "$name"
  n=$((n+1))
  [ "$n" -ge ${500 + 1} ] && break
done
test -d "$1"`;
  const r = await run("bash", ["-c", script, "files", path], options);
  if (r.code !== 0) throw new Error(r.stderr || "Cannot list this folder");
  const fields = r.stdout.split("\0");
  return Array.from({ length: Math.floor(fields.length / 2) }, (_, k) => ({ name: fields[2 * k + 1], dir: fields[2 * k] === "d" }));
  };
  const existing = async (paths, kind = "file", options) => {
    if (!paths.length) return [];
    if (platform === "windows") return jsonRows(checked(await ps(`@(@(${paths.map(psQuote).join(",")}) | Where-Object { Test-Path -LiteralPath $_${kind === "directory" ? " -PathType Container" : kind === "file" ? " -PathType Leaf" : ""} }) | ConvertTo-Json -Compress`, options)).stdout);
    const flag = kind === "directory" ? "-d" : kind === "file" ? "-f" : "-e";
    const r = checked(await run("sh", ["-c", `for f; do [ ${flag} "$f" ] && printf "%s\\n" "$f"; done; true`, "sh", ...paths], options));
    return r.stdout.split("\n").filter(Boolean);
  };
  const legacyStatus = async (file) => {
    if (platform === "windows") return checked(await ps(`if (Test-Path -LiteralPath ${psQuote(file)} -PathType Leaf) { 'file' } elseif (Test-Path -LiteralPath ${psQuote(file)}) { 'other' } else { 'none' }`)).stdout.trim();
    return (await run("sh", ["-c", 'if [ -f "$1" ]; then echo file; elif out=$(LC_ALL=C ls -d "$1" 2>&1); then echo other; else case "$out" in *": No such file or directory") echo none;; *) echo "error: $out";; esac; fi', "sh", file])).stdout?.trim() ?? "";
  };
  const drain = async (dir) => {
    if (platform === "windows") return checked(await ps(`if (Test-Path -LiteralPath ${psQuote(dir)}) { Get-ChildItem -LiteralPath ${psQuote(dir)} -Filter '*.path' -File | ForEach-Object { [Console]::Write([IO.File]::ReadAllText($_.FullName)+[char]0); Remove-Item -LiteralPath $_.FullName -Force } }`));
    return run("sh", ["-c", 'for f in "$1"/*.path; do [ -f "$f" ] || continue; cat "$f"; printf "\\0"; rm -f "$f"; done', "sh", dir]);
  };
  const read = async (path, limit = 1048576, options) => platform === "windows"
    ? checked(await ps(`$s=[IO.File]::Open(${psQuote(path)},'Open','Read','ReadWrite'); try { $b=New-Object byte[] ([Math]::Min($s.Length,${Number(limit)})); $n=$s.Read($b,0,$b.Length); [Console]::Write([Text.Encoding]::UTF8.GetString($b,0,$n)) } finally { $s.Dispose() }`, options)).stdout
    : checked(await run("head", ["-c", String(limit), path], options)).stdout;
  const tree = async (root, rels = [], options) => {
    const folders = rels.length ? rels : [""];
    const r = platform === "windows" ? await ps(winTree(root, folders), options) : await run("sh", ["-c", unixTree(platform), "tree", root, ...folders], options);
    if (r.code !== 0 || r.truncated || /truncat/i.test(`${r.stdout ?? ""}${r.stderr ?? ""}`)) throw new Error(r.stderr || "Cannot list this folder");
    return r.stdout;
  };
  const walk = async (roots, { depth = 4, names = [], skip = ["node_modules", ".venv", "venv", "target", "dist", "build", ".next", ".turbo", ".cache", "vendor", "Pods", "DerivedData", "coverage", "__pycache__", ".Trash", "Library"], newer = null } = {}) => {
    if (!roots.length) return [];
    if (platform === "windows") return jsonRows(checked(await ps(`$skip=@(${skip.map(psQuote).join(",")}); $names=@(${names.map(psQuote).join(",")}); function walk($dir,$level) { if ($level -gt ${Number(depth)}) { return }; foreach ($f in Get-ChildItem -LiteralPath $dir -Force -ErrorAction Stop) { if (($f.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $skip -contains $f.Name) { continue }; if (($names.Count -eq 0 -or $names -contains $f.Name)${newer == null ? "" : ` -and $f.LastWriteTimeUtc -gt [DateTimeOffset]::FromUnixTimeMilliseconds(${Number(newer)}).UtcDateTime`}) { $f.FullName }; if ($f.PSIsContainer -and $skip -notcontains $f.Name -and $names -notcontains $f.Name) { walk $f.FullName ($level+1) } } }; @(foreach ($root in @(${roots.map(psQuote).join(",")})) { if (Test-Path -LiteralPath $root -PathType Container) { walk $root 1 } }) | ConvertTo-Json -Compress`)).stdout);
    const args = [...roots, "-maxdepth", String(depth), ...(skip.length ? ["(", ...skip.flatMap((name, i) => [...(i ? ["-o"] : []), "-name", name]), ")", "-prune", "-o"] : []), ...(names.length ? ["(", ...names.flatMap((name, i) => [...(i ? ["-o"] : []), "-name", name]), ")"] : []), ...(newer == null ? [] : ["-mmin", `-${Math.max(1, Math.ceil((Date.now() - newer) / 60000))}`]), "-print0"];
    const result = await run("find", args);
    if (result.code !== 0 && !result.stdout) checked(result);
    return result.stdout.split("\0").filter(Boolean);
  };
  const size = async (path) => platform === "windows"
    ? Number(checked(await ps(`$bytes=(Get-ChildItem -LiteralPath ${psQuote(path)} -Recurse -Force -File | Where-Object { -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) } | Measure-Object -Property Length -Sum).Sum; [Math]::Ceiling($bytes/1024)`)).stdout.trim())
    : Number(checked(await run("du", ["-sk", path])).stdout.trim().split(/\s+/)[0]);
  const stat = async (path, options) => {
    const r = platform === "windows"
      ? checked(await ps(`$i=Get-Item -LiteralPath ${psQuote(path)}; '{0} {1}' -f $i.Length, ([DateTimeOffset]$i.LastWriteTimeUtc).ToUnixTimeSeconds()`, options))
      : checked(await run(bin(platform, "stat"), platform === "macos" ? ["-L", "-f", "%z %m", path] : ["-L", "-c", "%s %Y", path], options));
    const [size, mtime] = r.stdout.trim().split(/\s+/).map(Number);
    return { size, mtime };
  };
  const encode = (path, range, options) => {
    const whole = !range || (range.offset === 0 && range.length == null);
    if (platform === "windows") return whole
      ? ps(`[Convert]::ToBase64String([IO.File]::ReadAllBytes(${psQuote(path)}))`, options)
      : ps(`$s=[IO.File]::OpenRead(${psQuote(path)}); try { [void]$s.Seek(${Number(range.offset)}, 'Begin'); $b=New-Object byte[] ${Number(range.length)}; $n=$s.Read($b,0,$b.Length); [Convert]::ToBase64String($b,0,$n) } finally { $s.Dispose() }`, options);
    const b64 = bin(platform, "base64");
    if (!whole) return run("sh", ["-c", `tail -c +"$2" "$1" | head -c "$3" | ${b64}`, "slice", path, String(Number(range.offset) + 1), String(Number(range.length))], options);
    return platform === "macos" ? run(b64, ["-i", path], options) : run(b64, [path], options);
  };
  const decodeBase64File = async (from, to, options = {}) => {
    const { append: extra, ...rest } = options;
    if (extra) {
      const appended = platform === "windows"
        ? await ps(`[IO.File]::AppendAllText(${psQuote(from)}, [IO.File]::ReadAllText(${psQuote(extra)}))`, rest)
        : await run("sh", ["-c", "cat \"$1\" >> \"$2\"", "cat", extra, from], rest);
      checked(appended);
    }
    if (to == null) return;
    const decoded = platform === "windows"
      ? await ps(`[IO.File]::WriteAllBytes(${psQuote(to)}, [Convert]::FromBase64String(([IO.File]::ReadAllText(${psQuote(from)}) -replace '\\s','')))`, rest)
      : platform === "macos"
        ? await run(bin(platform, "base64"), ["-D", "-i", from, "-o", to], rest)
        : await run("sh", ["-c", "base64 -d \"$1\" > \"$2\"", "b64", from, to], rest);
    checked(decoded);
  };
  const touch = async (paths) => {
    if (platform === "windows") return ps(`foreach ($file in @(${paths.map(psQuote).join(",")})) { [IO.File]::WriteAllText($file,'') }`);
    if (!paths.length) return { code: 0, stdout: "" };
    return run("touch", paths);
  };
  const recent = async (paths, since) => {
    if (!paths.length) return false;
    if (platform === "windows") return jsonRows(checked(await ps(`@(@(${paths.map(psQuote).join(",")}) | Where-Object { (Test-Path -LiteralPath $_) -and (Get-Item -LiteralPath $_ -Force).LastWriteTimeUtc -gt [DateTimeOffset]::FromUnixTimeMilliseconds(${Number(since)}).UtcDateTime }) | ConvertTo-Json -Compress`)).stdout).length > 0;
    const result = await run("find", [...paths, "-maxdepth", "0", "-mmin", `-${Math.max(1, Math.ceil((Date.now() - since) / 60000))}`, "-print0"]);
    if (result.code !== 0 && !result.stdout) checked(result);
    return Boolean(result.stdout);
  };
  const write = async (path, text, expected, options) => {
    const outcome = await writeSteps(platform, path, text, expected).reduce(async (done, step) => {
      const prev = await done;
      if (prev.error) return prev;
      const result = await (step.script ? powershell(run, step.script(prev.dir), options) : run(step.cmd, step.args(prev.dir), options)).catch((error) => ({ thrown: error }));
      if (result.thrown) return { dir: prev.dir, error: result.thrown, wipe: Boolean(prev.dir) };
      if (result.code === 3) return { dir: "", error: new SaveConflict(), wipe: false };
      if (result.code !== 0) return { dir: prev.dir, error: new Error(String(result.stderr || `Command failed (${result.code})`).trim()), wipe: Boolean(prev.dir) };
      return { dir: step.keeps ? String(result.stdout ?? "").trim() : "", error: null, wipe: false };
    }, Promise.resolve({ dir: "", error: null, wipe: false }));
    if (outcome.wipe && outcome.dir) await remove([outcome.dir], { recursive: true, ...options }).catch(() => {});
    if (outcome.error) throw outcome.error;
  };
  const migrate = (from, to) => platform === "windows"
    ? ps(`$from=${psQuote(from)}; $to=${psQuote(to)}; if (-not (Test-Path -LiteralPath (Join-Path $to 'store.json')) -and (Test-Path -LiteralPath $from -PathType Container)) { [IO.Directory]::CreateDirectory($to) | Out-Null; Get-ChildItem -LiteralPath $from -Force | Copy-Item -Destination $to -Recurse -Force; Get-ChildItem -LiteralPath $to -Filter '*.lock' -Force | Remove-Item -Force -Recurse }`)
    : run("sh", ["-c", 'if [ ! -e "$2/store.json" ] && [ -d "$1" ]; then mkdir -p "$2" && cp -R "$1/." "$2/" && rm -rf "$2"/*.lock; fi', "sh", from, to]);
  return { recent, migrate, mkdir, remove, copy, move, test, directory, existing, legacyStatus, drain, read, walk, size, touch, stat, encode, tree, decodeBase64File, write };
}
