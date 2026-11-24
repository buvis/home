import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

// These UI modules use milliseconds for both notifications and command timeouts.
// A seconds-sized literal makes a notification unreadable before it disappears.
for (const file of [
  "my-menu/main.js", "on-screen/main.js",
  "ship-it/data.js", "ship-it-prs/data.js", "ship-it-issues/data.js", "ship-it-review/data.js",
  "ship-it-prs/main.js", "ship-it-issues/main.js", "ship-it-review/main.js",
]) {
  test(`${file}: explicit timeouts allow at least one second`, () => {
    const source = readFileSync(new URL(`../mods/${file}`, import.meta.url), "utf8");
    const durations = [...source.matchAll(/\btimeout:\s*(\d+)\b/g)].map(match => Number(match[1]));
    assert.ok(durations.length > 0, "expected explicit timeout coverage");
    assert.deepEqual(durations.filter(ms => ms < 1000), [], "timeout uses milliseconds, not seconds");
  });
}
