// Files a tool wrote rather than a person: lockfiles, bundles, codegen,
// snapshots. They are kept out of what the model reads (a lockfile can outweigh
// the whole change and says nothing about its intent) but never out of what the
// reader sees: they show at the end, with everything no step covered.
//
// Matched by name only, and conservatively. Leaving real code out of a
// walkthrough without saying so is the one failure this mod must not have, so
// `src/lock.ts` and `codegen.py` stay in.

const LOCKFILES = new Set([
  "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lock", "bun.lockb",
  "deno.lock", "composer.lock", "Gemfile.lock", "Pipfile.lock", "poetry.lock", "uv.lock", "pdm.lock",
  "Cargo.lock", "go.sum", "mix.lock", "pubspec.lock", "Podfile.lock", "Package.resolved", "flake.lock",
  "gradle.lockfile", "packages.lock.json", "paket.lock",
]);

const PATTERNS = [
  /\.min\.(js|mjs|css)$/i,
  /\.(js|mjs|css)\.map$/i,
  /\.(generated|gen|g)\.[a-z0-9]+$/i,
  /(^|\/)(__generated__|generated)\//i,
  /\.pb\.(go|cc|h|ts|js)$/i,
  /_pb2(_grpc)?\.pyi?$/i,
  /(^|\/)__snapshots__\//,
  /\.snap$/i,
];

export function isGenerated(path) {
  if (typeof path !== "string" || !path) return false;
  if (LOCKFILES.has(path.split("/").pop())) return true;
  return PATTERNS.some((p) => p.test(path));
}
