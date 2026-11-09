// node mods/reaper/check.mjs
import assert from "node:assert/strict";
import { detachedAttachIds } from "./sweep.js";

const holders = [
  "11931 /Users/bob/.local/bin/osewa holder --id aaa1 --cols 51 -- sh -lc 'exec moshi-hook hc attach'",
  "11940 /Users/bob/.local/bin/osewa holder --id bbb2 --cols 80 -- sh -lc 'exec bash -l'",
  "11932 moshi-hook hc attach",
].join("\n");

// picks an hc-attach session the phone has left
assert.deepEqual(detachedAttachIds([{ id: "aaa1", attached: 0 }], holders), ["aaa1"]);

// leaves a session the phone is viewing
assert.deepEqual(detachedAttachIds([{ id: "aaa1", attached: 1 }], holders), []);

// never picks a Moshi session running anything other than hc attach
assert.deepEqual(detachedAttachIds([{ id: "bbb2", attached: 0 }], holders), []);

console.log("reaper: ok");
