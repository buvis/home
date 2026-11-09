// Moshi keeps a phone session running on this Mac after the phone disconnects.
// Its `hc attach` follows focus and resizes each terminal to the phone's size
// on every tab switch (the narrow-then-wide flash). While you are at the laptop
// (the pager mod's presence: not idle 5 min, no screensaver, lid open), this
// ends Moshi `hc attach` sessions the phone has left. Nothing is lost: the
// core keeps the terminals. Lives in an empty floating block, draws nothing.
import { View, div } from "gpui-kit";
import { exec, home, appHome } from "herdr";
import { detachedAttachIds } from "./sweep.js";

export default class Reaper extends View {
  init(_props, cx) {
    this.osewa = `${home()}/.local/bin/osewa`;
    cx.timer.every(5 * 60_000, (cx) => cx.spawn(async () => this.sweep()));
  }

  async sweep() {
    try {
      const ls = JSON.parse((await exec(this.osewa, ["local", "ls"])).stdout);
      const holders = (await exec("/usr/bin/pgrep", ["-lf", "osewa holder"])).stdout;
      const ids = detachedAttachIds(ls.sessions ?? [], holders);
      if (!ids.length) return;
      const probe = await exec("python3", ["-B", `${appHome()}/mods/pager/sender.py`, "--presence"]);
      if (JSON.parse(probe.stdout).channel !== "desktop") return; // away: leave the phone's sessions
      for (const id of ids) await exec(this.osewa, ["local", "kill", id]);
      this.lastError = null;
    } catch (e) {
      // ponytail: log once per distinct error, keep retrying (osewa may be mid-update)
      if (String(e) !== this.lastError) console.log(`reaper: sweep failed: ${e}`);
      this.lastError = String(e);
    }
  }

  render() {
    return div();
  }
}
