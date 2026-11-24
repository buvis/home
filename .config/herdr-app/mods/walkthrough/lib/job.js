// One generation is one agent run in the background (`claude -p` or `pi -p`),
// in a folder of its own: the prompt goes in as files, the answer comes out as
// a file. Nothing ties it to the window that asked, so closing the walkthrough
// (or Herdr) doesn't throw away a minute of paid work; the next look finds the
// answer.

import { parseJson } from "./walkthrough.js";

// Who writes the walkthrough. Claude Code is the default: its structured output
// (--json-schema) is far more reliable than a schema in the prompt. pi has no
// structured output, so its answer is parsed from text.
export const BACKENDS = [
  { key: "claude", name: "Claude Code", program: "claude", writer: "Claude", about: "Written by `claude -p`, with structured output" },
  { key: "pi", name: "pi", program: "pi", writer: "pi", about: "Written by `pi -p`, with any model pi is set up for" },
];
export const DEFAULT_BACKEND = "claude";
export const backendOf = (key) => BACKENDS.find((b) => b.key === key) ?? BACKENDS[0];

// Model keys are unique across backends: a walkthrough's cache key names its model, and so its backend.
// An empty `model` runs the backend's own default model.
export const MODELS = {
  claude: [
    { key: "haiku", model: "haiku", name: "Haiku", about: "Fast and cheap; fine for most changes" },
    { key: "sonnet", model: "sonnet", name: "Sonnet", about: "Better grouping on large or subtle changes" },
    { key: "opus", model: "opus", name: "Opus", about: "The most careful reading, the highest cost" },
  ],
  pi: [
    { key: "pi-default", model: "", name: "pi's default", about: "The model pi is set up to use" },
    { key: "deepseek/deepseek-flash", model: "deepseek/deepseek-flash", name: "deepseek-flash", about: "Fast and cheap; 1M context, fine for most changes" },
    { key: "deepseek/deepseek-v4-pro", model: "deepseek/deepseek-v4-pro", name: "deepseek-v4-pro", about: "More careful on large or subtle changes" },
    { key: "deepseek/deepseek-chat", model: "deepseek/deepseek-chat", name: "deepseek-chat", about: "64K context: small changes only" },
  ],
};
const ALL_MODELS = Object.entries(MODELS).flatMap(([backend, list]) => list.map((m) => ({ ...m, backend })));
export const DEFAULT_MODEL = { claude: "haiku", pi: "pi-default" };
// Written without a click only by the cheapest model a backend has.
export const AUTO_MODEL = { claude: "haiku", pi: "pi-default" };

export const modelsOf = (backend) => MODELS[backendOf(backend).key];
/** A model by its key, whichever backend has it; an unknown key is Claude's default. */
export const modelOf = (key) => ALL_MODELS.find((m) => m.key === key) ?? ALL_MODELS[0];
/** The model a backend uses: `key` when it is one of its own, else its default. */
export const modelFor = (backend, key) => {
  const b = backendOf(backend).key;
  return MODELS[b].some((m) => m.key === key) ? key : DEFAULT_MODEL[b];
};

// No tools, no MCP servers, no settings, hooks or skills: the model reads the
// prompt and answers. Each of those would otherwise ride along on every call
// (a full Claude Code setup can be hundreds of thousands of tokens).
export const CLAUDE_FLAGS = [
  "-p", "--output-format", "json", "--tools", "", "--no-session-persistence",
  "--strict-mcp-config", "--setting-sources", "", "--disable-slash-commands",
];
export const PI_FLAGS = ["-p", "--mode", "json", "--no-tools", "--no-extensions", "--no-mcp", "--no-skills", "--no-context-files", "--no-session"];

/** Whether a process's command line is a walkthrough run (its pid file may outlive it, and pids are reused). */
// Matched by the flags the run alone passes together: the program itself can show as claude, a
// versioned binary or node, depending on how it was installed. pi rewrites its process title, so
// for pi the start time run.sh records is what counts (engine.js runPid); this is the fallback.
export const isRunCommand = (command) =>
  ["--json-schema", "--no-session-persistence", "--strict-mcp-config", "--disable-slash-commands"].every((flag) => String(command).includes(flag))
  || ["--mode", "--no-extensions", "--no-skills", "--no-session"].every((flag) => String(command).includes(flag));

const shellQuote = (s) => `'${String(s).replace(/'/g, `'\\''`)}'`;

/** The command line of a run, in run.sh: $1 the program, $2 the model ("" for the default). */
function command(backend) {
  if (backendOf(backend).key === "pi") {
    return `"$1" ${PI_FLAGS.map(shellQuote).join(" ")} \${2:+--model "$2"} --system-prompt "$(cat system.txt)" < prompt.txt > out.json 2> err.txt &`;
  }
  return `"$1" ${CLAUDE_FLAGS.map(shellQuote).join(" ")} \${2:+--model "$2"} --json-schema "$(cat schema.json)" --system-prompt "$(cat system.txt)" < prompt.txt > out.json 2> err.txt &`;
}

/**
 * The script a job folder runs: `sh run.sh <program> <model> <seconds>`. A
 * watchdog stops the run after <seconds>, so a hung run ends even when no
 * window is open to notice; it checks every few seconds and leaves with it.
 * The run's start time is recorded beside its pid: pi rewrites its process
 * title, so the pid alone can't tell it from a process that reused the number.
 */
export function jobScript(backend = DEFAULT_BACKEND) {
  return `#!/bin/sh
# One walkthrough generation. Written by the walkthrough mod for Herdr.
cd "$(dirname "$0")" || exit 1
${command(backend)}
pid=$!
echo $pid > pid
ps -o lstart= -p "$pid" > started.tmp 2>/dev/null && mv -f started.tmp started
( waited=0
  while kill -0 $pid 2>/dev/null; do
    if [ $waited -ge "\${3:-900}" ]; then echo "Stopped after $3 seconds without an answer." >> err.txt; kill $pid; exit 0; fi
    sleep 3; waited=$((waited + 3))
  done ) &
wait $pid
echo $? > code.tmp && mv code.tmp code
`;
}

const loginLike = /api key|credential|log ?in|auth/i;
const firstLine = (t) => String(t ?? "").split("\n").map((l) => l.trim()).find(Boolean) ?? "";
const fromErr = (err, code, program) => String(err ?? "").trim().split("\n").filter(Boolean).slice(-3).join(" ") || `${program} exited with ${String(code ?? "?").trim()}`;

/**
 * What a finished job left: the walkthrough's raw object and its cost, or an
 * error with a message a person can act on.
 * @param {{ backend?: string, out: string|null, err: string|null, code: string|null }} files
 * @returns {{ raw: any, cost: number|null }}
 */
export function readOutcome({ backend = DEFAULT_BACKEND, out, err, code }) {
  return backendOf(backend).key === "pi" ? piOutcome({ out, err, code }) : claudeOutcome({ out, err, code });
}

function claudeOutcome({ out, err, code }) {
  let answer = null;
  try { answer = out ? JSON.parse(out) : null; } catch { answer = null; }
  if (!answer) throw Object.assign(new Error(fromErr(err, code, "claude")), { code: "failed" });
  if (answer.is_error || (answer.subtype && answer.subtype !== "success")) {
    const why = typeof answer.result === "string" && answer.result.trim() ? answer.result.trim() : answer.subtype ?? "claude reported an error";
    throw Object.assign(new Error(why), { code: /log ?in/i.test(why) ? "login" : "failed" });
  }
  const raw = answer.structured_output ?? parseJson(answer.result);
  return { raw, cost: typeof answer.total_cost_usd === "number" ? answer.total_cost_usd : null };
}

/** pi prints one JSON event per line; the answer is the text of the last `turn_end`. */
function piOutcome({ out, err, code }) {
  let end = null, failed = null;
  for (const line of String(out ?? "").split("\n")) {
    if (!line.startsWith("{")) continue;
    let o;
    try { o = JSON.parse(line); } catch { continue; }
    if (o?.type === "turn_end" && o.message) end = o;
    else if (o?.type === "error") failed = o;
  }
  if (failed) {
    const why = firstLine(failed.message ?? failed.error ?? JSON.stringify(failed)) || "pi reported an error";
    throw Object.assign(new Error(why), { code: loginLike.test(why) ? "login" : "failed" });
  }
  if (!end) {
    const why = fromErr(err, code, "pi");
    throw Object.assign(new Error(why), { code: loginLike.test(why) ? "login" : "failed" });
  }
  const parts = Array.isArray(end.message.content) ? end.message.content : [];
  const answer = parts.filter((p) => p?.type === "text").map((p) => p.text ?? "").join("\n").trim();
  let raw = null;
  try { raw = answer ? parseJson(answer) : null; } catch { raw = null; }
  // A refusal or a question comes back as prose: it is the reason.
  if (!raw) throw Object.assign(new Error(firstLine(answer) || "pi gave no walkthrough that could be read"), { code: "failed" });
  const cost = end.message.usage?.cost?.total;
  return { raw, cost: typeof cost === "number" ? cost : null };
}
