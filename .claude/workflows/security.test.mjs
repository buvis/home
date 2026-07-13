// Tests for the security-dimension trigger and vocabulary (securityTriggered)
// in review-fanout.workflow.js.
//
// Run the whole suite: node --test /Users/bob/.claude/workflows/*.test.mjs

import test from "node:test";
import assert from "node:assert/strict";
import { pure } from "./_harness.mjs";
test("a security word counts when it lands on an added line, a removed line, or a changed path", () => {
  const p = pure();

  assert.equal(
    p.securityTriggered("@@ -1,2 +1,3 @@\n const a = 1;\n+  child_process.exec(cmd);\n", []),
    true,
    "an added line introducing exec triggers the security dimension",
  );

  assert.equal(
    p.securityTriggered("@@ -1,2 +1,2 @@\n child_process.exec(cmd);\n+  const a = 1;\n", []),
    false,
    "an unchanged context line must not trigger",
  );

  assert.equal(
    p.securityTriggered("@@ -1,2 +1,1 @@\n-  child_process.exec(cmd);\n+  const a = 1;\n", []),
    true,
    "a removed line carrying a security word triggers too: deleting it is at least as strong a signal as adding it",
  );

  assert.equal(
    p.securityTriggered("--- a/src/exec.js\n+++ b/src/exec.js\n const a = 1;\n", []),
    false,
    "the ---/+++ file headers are not content lines",
  );

  assert.equal(
    p.securityTriggered("@@ -1 +1 @@\n+  execute(query);\n", []),
    false,
    "'execute' must not match the 'exec' term",
  );

  assert.equal(
    p.securityTriggered("@@ -1 +1 @@\n+  const hashmap = new Map();\n", []),
    false,
    "'hashmap' must not match the 'hash' term",
  );

  assert.equal(
    p.securityTriggered("@@ -1 +1 @@\n+  const a = 1;\n", ["scripts/exec.sh"]),
    true,
    "a security-ish changed path triggers on its own",
  );
});

test("a diff whose only change is removing a line containing an auth guard arms the security dimension", () => {
  const p = pure();

  assert.equal(
    p.securityTriggered(
      "@@ -1,2 +1,1 @@\n-  if (!auth.isValid(req)) return res.status(403).end();\n   next();\n",
      [],
    ),
    true,
    "a review engine that skips security review when a guard is deleted fails open: the deleted " +
      "auth check must arm the security dimension even though nothing was added",
  );
});

test("the security vocabulary covers the whole threat surface, not one or two words", () => {
  const p = pure();
  const added = (code) => `@@ -1 +1 @@\n+${code}\n`;

  // Every term actually in SECURITY_RE, hardcoded independently of the regex source:
  // an adversarial edit that deletes a term from SECURITY_RE must fail the matching
  // assertion below, not silently shrink the list of terms under test.
  const terms = [
    ["exec", "  child_process.exec(cmd);"],
    ["eval", "  eval(source);"],
    ["auth", "  router.use(auth);"],
    ["token", "  const token = req.headers.x;"],
    ["password", "  const password = body.pw;"],
    ["secret", "  const secret = load();"],
    ["sql", "  const sql = build(q);"],
    ["crypto", "  const crypto = require('node:crypto');"],
    ["hash", "  const hash = digest(x);"],
    ["credential", "  const credential = load();"],
    ["session", "  const session = req.session;"],
    ["cookie", "  const cookie = req.headers.cookie;"],
    ["csrf", "  const csrf = mintToken();"],
    ["xss", "  const xss = check(input);"],
    ["jwt", "  const jwt = sign(payload);"],
    ["sanitize", "  sanitize(input);"],
    ["injection", "  const injection = detect(input);"],
    ["privilege", "  const privilege = checkRole();"],
  ];

  for (const [term, code] of terms) {
    assert.equal(
      p.securityTriggered(added(code), []),
      true,
      `an added line containing '${term}' must arm the security dimension`,
    );
  }
});

test("an ordinary changed path does not arm the security dimension", () => {
  const p = pure();
  const benign = "@@ -1 +1 @@\n+  const a = 1;\n";

  assert.equal(
    p.securityTriggered(benign, ["README.md"]),
    false,
    "a docs-only path must not arm security",
  );
  assert.equal(
    p.securityTriggered(benign, ["src/list.js"]),
    false,
    "an ordinary source path must not arm security",
  );
  assert.equal(
    p.securityTriggered(benign, ["src/list.js", "docs/guide.md", "test/list.test.js"]),
    false,
    "a pile of ordinary paths is still not a security change",
  );
  assert.equal(
    p.securityTriggered(benign, ["src/auth/login.js"]),
    true,
    "a security-ish path among ordinary ones still arms security",
  );
});

test("the security gate scans every changed path, not just the first one", () => {
  const p = pure();
  const benign = "@@ -1 +1 @@\n+  const a = 1;\n";

  assert.equal(
    p.securityTriggered(benign, ["README.md", "src/auth/login.js"]),
    true,
    "a benign first path must not mask a security-ish second path",
  );
  assert.equal(
    p.securityTriggered(benign, [
      "README.md",
      "docs/guide.md",
      "src/list.js",
      "test/list.test.js",
      "config/secrets.yml",
    ]),
    true,
    "a security-ish path in last position still arms security",
  );
  assert.equal(
    p.securityTriggered(benign, ["README.md", "docs/guide.md", "src/list.js"]),
    false,
    "scanning every path must not turn a pile of ordinary paths into a security change",
  );
});

test("the security gate scans every added line, not just the first one", () => {
  const p = pure();

  assert.equal(
    p.securityTriggered("@@ -1 +2 @@\n+const a = 1;\n+eval(userInput);\n", []),
    true,
    "a benign first added line must not mask a dangerous second one",
  );
  assert.equal(
    p.securityTriggered(
      "@@ -1,4 +1,8 @@\n const ctx = {};\n+const a = 1;\n+const b = 2;\n-const gone = 3;\n+const c = 4;\n+const d = 5;\n+const token = req.headers.x;\n",
      [],
    ),
    true,
    "a dangerous added line deep in the hunk still arms security",
  );
  assert.equal(
    p.securityTriggered(
      "@@ -1,3 +1,4 @@\n const ctx = {};\n+const a = 1;\n+const b = 2;\n+const c = 3;\n",
      [],
    ),
    false,
    "scanning every added line must not arm security on an entirely benign hunk",
  );
});

test("the security vocabulary matches regardless of case", () => {
  const p = pure();

  assert.equal(
    p.securityTriggered("@@ -1 +1 @@\n+child_process.EXEC(cmd);\n", []),
    true,
    "an uppercase EXEC is the same threat as a lowercase one",
  );
  assert.equal(
    p.securityTriggered("@@ -1 +1 @@\n+const PASSWORD = body.pw;\n", []),
    true,
    "an uppercase PASSWORD on an added line arms security",
  );
  assert.equal(
    p.securityTriggered("@@ -1 +1 @@\n+const Secret = load();\n", []),
    true,
    "a mixed-case Secret arms security",
  );
  assert.equal(
    p.securityTriggered("@@ -1 +2 @@\n+const a = 1;\n+const authToken = mint();\n", []),
    true,
    "case-insensitivity and multi-line scanning hold together",
  );
});
