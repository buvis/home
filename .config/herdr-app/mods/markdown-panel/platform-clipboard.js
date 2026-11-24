import { psQuote, powershell } from "./platform-command.js";

const WINDOWS_INPUT = String.raw`using System;
using System.Runtime.InteropServices;
public static class KansoPaste {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [StructLayout(LayoutKind.Sequential)] public struct Keyboard { public ushort key,scan; public uint flags,time; public UIntPtr extra; }
  [StructLayout(LayoutKind.Sequential)] public struct Mouse { public int x,y; public uint data,flags,time; public UIntPtr extra; }
  [StructLayout(LayoutKind.Explicit)] public struct Data { [FieldOffset(0)] public Keyboard keyboard; [FieldOffset(0)] public Mouse mouse; }
  [StructLayout(LayoutKind.Sequential)] public struct Input { public uint type; public Data data; }
  [DllImport("user32.dll",SetLastError=true)] static extern uint SendInput(uint count, Input[] inputs, int size);
  public static bool Paste(long target) {
    if (GetForegroundWindow().ToInt64()!=target) return false;
    var inputs=new Input[4];
    for (int i=0;i<4;i++) { inputs[i].type=1; inputs[i].data.keyboard.key=(ushort)(i==0||i==3?17:86); inputs[i].data.keyboard.flags=(uint)(i>1?2:0); }
    return SendInput(4,inputs,Marshal.SizeOf(typeof(Input)))==4;
  }
}`;

export function clipboardApi(platform, run) {
  const image = async (file) => {
    if (platform === "windows") {
      const script = `Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; $image=[System.Drawing.Image]::FromFile(${psQuote(file)}); try { [System.Windows.Forms.Clipboard]::SetImage($image) } finally { $image.Dispose() }`;
      const r = await run("powershell", ["-NoProfile", "-NonInteractive", "-STA", "-Command", "$ErrorActionPreference='Stop'; " + script]);
      return r.code === 0;
    }
    if (platform === "macos") return (await run("osascript", ["-e", `set the clipboard to (read (POSIX file "${String(file).replace(/\\/g, "\\\\").replace(/"/g, '\\"')}") as «class PNGf»)`])).code === 0;
    const r = await run("sh", ["-c", 'wl-copy --type image/png < "$1"', "sh", file]).catch(() => null);
    return r?.code === 0 || (await run("xclip", ["-selection", "clipboard", "-t", "image/png", "-i", file])).code === 0;
  };
  const frontApp = async () => {
    if (platform === "windows") {
      const r = await powershell(run, `Add-Type -TypeDefinition ${psQuote(WINDOWS_INPUT.replace(/\n/g, " "))}; [KansoPaste]::GetForegroundWindow().ToInt64()`);
      return r.code === 0 && /^\d+$/.test(r.stdout.trim()) ? r.stdout.trim() : null;
    }
    if (platform !== "macos") return null;
    const r = await run("osascript", ["-l", "JavaScript", "-e", 'ObjC.import("AppKit"); var a = $.NSWorkspace.sharedWorkspace.frontmostApplication; a ? ObjC.unwrap(a.bundleIdentifier) : ""']);
    return r.code === 0 && r.stdout.trim() ? r.stdout.trim() : null;
  };
  const paste = async (target) => {
    if (platform === "windows") {
      if (!/^\d+$/.test(String(target ?? ""))) return { state: "error" };
      const r = await powershell(run, `Add-Type -TypeDefinition ${psQuote(WINDOWS_INPUT.replace(/\n/g, " "))}; if (-not [KansoPaste]::Paste([long]${psQuote(target)})) { exit 1 }`);
      return { state: r.code === 0 ? "ok" : "error" };
    }
    const commands = platform === "macos" ? [["osascript", ["-e", 'tell application "System Events" to keystroke "v" using command down']]] : [["wtype", ["-M", "ctrl", "-k", "v", "-m", "ctrl"]], ["xdotool", ["key", "--clearmodifiers", "ctrl+v"]]];
    for (const [program, args] of commands) if ((await run(program, args).catch(() => null))?.code === 0) return { state: "ok" };
    return { state: "error" };
  };
  return { image, frontApp, paste, observesFrontApp: platform !== "linux", pasteKey: platform === "macos" ? "Cmd-V" : "Ctrl-V", permissionNote: platform === "macos" ? " To have it pasted for you, allow Herdr in System Settings > Privacy & Security > Accessibility." : "", write: (cx, text) => cx.write_to_clipboard(String(text)), read: (cx) => cx.read_from_clipboard() };
}
