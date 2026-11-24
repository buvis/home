import { exec, window, writeTextFile } from "herdr";
import { platformName, powershell, checked } from "./platform-command.js";

export const localName = () => platformName(window()?.platform ?? "macos");
export const localService = (factory) => factory(localName(), exec, writeTextFile);
export const sleepFor = (platform, runner, seconds) => platform === "windows"
  ? powershell(runner, `Start-Sleep -Milliseconds ${Math.max(0, Math.round(Number(seconds) * 1000))}`)
  : runner("sleep", [String(seconds)]);
export const localSleep = (seconds) => sleepFor(localName(), exec, seconds);
export const REMOTE_TIMEOUT = 12000;
class RemoteServices {
  constructor() { this.names = new Map(); }
  async get(factory, on) {
    if (!on) return localService(factory);
    const runner = (program, args, options) => exec(program, args, { timeout: REMOTE_TIMEOUT, ...options, on });
    if (!this.names.has(on)) {
      const probe = await powershell(runner, "[Environment]::OSVersion.Platform.ToString()").catch(() => null);
      const name = probe?.code === 0 && probe.stdout.trim() === "Win32NT" ? "windows" : checked(await runner("uname", ["-s"])).stdout.trim() === "Darwin" ? "macos" : "linux";
      this.names = new Map([...this.names, [on, name]]);
    }
    return factory(this.names.get(on), runner);
  }
}
const remoteServices = new RemoteServices();
export const serviceOn = (factory, on) => remoteServices.get(factory, on);
export const platformOf = (machine) => (machine ? serviceOn((platform) => platform, machine).catch(() => "linux") : Promise.resolve(localName()));
const withTimeout = (run, timeout) => (timeout == null ? run : (cmd, args, options = {}) => run(cmd, args, { timeout, ...options }));
export function serviceFor(factory, machine = null, timeout = null, remote = null) {
  if (!machine) return Promise.resolve(localService((platform, run, write) => factory(platform, withTimeout(run, timeout), write)));
  return (remote ?? serviceOn)((platform, run) => factory(platform, withTimeout(run, timeout)), machine);
}
