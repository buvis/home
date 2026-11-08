// Self-check: `node ~/.config/herdr-app/mods/bim-projects/test.mjs` runs the checks over the
// vault and asserts the rules on a hand-written note. Exits nonzero on a failed assertion.
import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import { homedir } from "node:os";
import { parseNote, check, KINDS, completeNote, parkNote, rescheduleNote } from "./check.js";

const sample = `---
id: 20260101000000
title: Sample
tags: [a, b]
type: project
completed: false
---

# Sample

## Description

One paragraph summarizing the problem statement.

## Log

- [ ] 2026-01-01 10:00 - ctx => Bob will reply | #gtd/wait
- [ ] 2026-01-01 10:00 - no arrow here | #gtd/act/now 📅 2026-01-01
- [ ] 2026-01-01 10:00 - ctx => do thing | #gtd/act/next
    - [ ] sub-step under a tagged action
- [ ] plain checkbox
- [x] 2026-01-01 10:00 - done => thing | #gtd/act/now ✅ 2026-01-02

## Plan

- [ ] untagged plan item is fine

## Solution
`;
const p = parseNote("/x/notes/20260101000000.md", sample);
assert.equal(p.title, "Sample");
assert.deepEqual(p.tags, ["a", "b"]);
assert.deepEqual(Object.keys(p.sections), ["Description", "Log", "Plan", "Solution"]);
const issues = check(p, "2026-03-15"), kinds = issues.map((i) => i.kind).sort();
assert.deepEqual(kinds, ["contact", "format", "overdue", "stale", "template", "undated", "untagged"]);
// Stale is tiered by the project's open lists: now/next/wait after 60 quiet days, later/someday after 120.
assert.ok(!check(p, "2026-03-01").some((i) => i.kind === "stale"), "59 quiet days on now/wait is not stale");
const parked = parseNote("/x/notes/20260101000000.md", sample.replace(/#gtd\/(wait|act\/now|act\/next)/g, "#gtd/act/someday"));
assert.ok(!check(parked, "2026-04-01").some((i) => i.kind === "stale"), "90 quiet days on someday is not stale");
assert.ok(check(parked, "2026-05-11").some((i) => i.kind === "stale"), "130 quiet days on someday is stale");

// Triage rewrites: c completes, s parks.
const done = completeNote(sample, "2026-03-15");
assert.match(done, /^completed: true$/m);
assert.ok(!/- \[ \] /.test(done), "every open checkbox is cancelled");
assert.ok(done.includes("- [-] plain checkbox ❌ 2026-03-15"), "cancelled tasks get the ❌ date");
const park = parkNote(sample, "2026-03-15 10:00");
assert.ok(park.includes("## Log\n\n- [i] 2026-03-15 10:00 - parked during review\n- [ ] 2026-01-01 10:00 - ctx => Bob will reply | #gtd/act/someday\n"), "log line added, wait moved to someday");
assert.ok(park.includes("- [ ] 2026-01-01 10:00 - no arrow here | #gtd/act/someday\n"), "due date dropped from a parked action");
assert.ok(park.includes("- [x] 2026-01-01 10:00 - done => thing | #gtd/act/now ✅ 2026-01-02"), "closed tasks untouched");
assert.ok(!check(parseNote("/x/notes/20260101000000.md", park), "2026-03-15").some((i) => ["stale", "undated"].includes(i.kind)), "a parked note is neither stale nor undated");
const redated = rescheduleNote(sample, "2026-03-15");
assert.ok(redated.includes("- [ ] 2026-01-01 10:00 - no arrow here | #gtd/act/now 📅 2026-03-22\n"), "past due date moved a week out");
assert.ok(redated.includes("| #gtd/act/now ✅ 2026-01-02"), "closed tasks untouched by r");
assert.ok(!check(parseNote("/x/notes/20260101000000.md", redated), "2026-03-15").some((i) => i.kind === "overdue"), "no overdue left after r");
assert.equal(issues.find((i) => i.kind === "format").task.line, 18, "task lines count the frontmatter");
assert.equal(issues.filter((i) => i.kind === "untagged").length, 1, "sub-steps under a tagged action are covered by it");
for (const k of kinds) assert.ok(KINDS[k], `label for ${k}`);

const dir = `${homedir()}/bim/notes`, today = new Date().toISOString().slice(0, 10), totals = {};
let projects = 0;
const ignored = JSON.parse(await readFile(`${homedir()}/bim/.bim-projects-ignored.json`, "utf8").catch(() => "[]"));
for (const name of (await readdir(dir)).filter((n) => n.endsWith(".md"))) {
  const text = await readFile(`${dir}/${name}`, "utf8");
  if (!/^type: project\s*$/m.test(text)) continue;
  projects++;
  for (const i of check(parseNote(`${dir}/${name}`, text), today, ignored)) totals[i.kind] = (totals[i.kind] || 0) + 1;
}
console.log(`${projects} projects`, totals);
