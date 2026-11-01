# Discovery: Check the Moshi Daemon for Sandbox Escapes

## Classification

Depth: standard | Date: 2026-10-18 | Status: specified as PRD 00179
(backlog, 2026-10-19); live deployment remains separate
Seeded from discovery 00168's side finding; user instruction 2026-10-18: 'all
of them must be recorded as discovery documents that I will go through'.
Written from a sandboxed session. Nothing was sent to the daemon except
Moshi's own documented read-only probe (`moshi-hook probe --json`). No
gateway route was called, and no pane was touched. Facts come from the
launchd plist, the daemon's logs, its CLI help, symbol and string names in
the `moshi-hook` binary, and `lsof`.

## Premise check

**Gateway reachability is confirmed; an escape through its action routes is
suspected, not demonstrated.** Authentication and retained-socket authority
must be qualified before claiming that a mitigation closes Moshi escapes.

- **What Moshi is.** `moshi-hook` 0.4.23 (`/Users/bob/.local/bin/moshi-hook`,
  Go, arm64, from `github.com/rjyo/moshi/app-hook`) is the host side of the
  Moshi phone app. Its help says it "installs AI agent hooks, serves a local
  Unix socket bridge, and maintains a WebSocket to Moshi for approval
  round-trips". The binary sits in `~/.local/bin`, which agents cannot write
  since 2026-10-17, so it cannot be swapped.
- **How it runs.** launchd agent `app.getmoshi.moshi-hook`
  (`~/Library/LaunchAgents/app.getmoshi.moshi-hook.plist`) runs `moshi-hook
  serve` with RunAtLoad and KeepAlive, outside the sandbox (pid 36528).
- **Two listeners** (from `service.log` and `lsof -p 36528 -i`):
  - the unix socket `~/Library/Application Support/Moshi/moshi-hook.sock`
    (mode 0600, owner bob). The Claude and Codex hooks write events here.
  - the HTTP gateway on `127.0.0.1:24543`. `--listen` (default
    `127.0.0.1:24544`) is the separate local web client, which reverse-proxies
    to the gateway (`webserver` uses `NewSingleHostReverseProxy`). It does not
    run now.
- **Not paired.** Every start logs `paired=false` and "no HostID, running
  socket-only (no remote approvals)". The cloud WebSocket is off. The user
  still uses the gateway: `service.log` shows "gateway prompt: text
  submitted", "gateway approvals: answer submitted ... decision=approve" and
  many "gateway questions: answers submitted" into herdr panes on 2026-10-10
  and 2026-10-17. The likely path is the phone over SSH (Easy Pair) or the
  local web client. Which one is not proven.
- **What the gateway can do.** Its routes and log messages include
  `/v1/workspaces/launch|create|close|panes`, `/v1/approvals/answer`,
  `/v1/questions/answer`, keys ("gateway keys: keys submitted"), prompt
  ("text submitted"), paste, pty ("gateway pty: herdr pane controlled",
  "tmux control attached"), `/v1/files/download`, `/v1/hosts/forward`,
  `/v1/integrations/install`, `/v1/update/*`, and git stage, discard and
  checkout. The daemon drives herdr through its own CLI (`MOSHI_HERDR_PATH`)
  as an unsandboxed process, so the herdr socket deny in `ai-agents.sb` does
  not apply to it.
- **No caller check found.** The gateway's handler symbols are named
  `loopback*` (`loopbackWorkspacesLaunch`, `loopbackWorkspacePanes`, and
  others), and the only listen check is "gateway listen must be
  localhost-only". No symbol or string names a token, Authorization check or
  peer-credential check on the gateway. `~/.config/moshi/config.toml`
  (0644, agent-readable) holds only a `[gateway]` table with four feature
  flags, no key. This is inference from names, not a tested refusal.
- **Reachable from the sandbox.** `moshi-hook probe --json`, run inside this
  sandboxed session with no token, returned
  `{"installed":true,"running":true,"gateway":true,"version":"0.4.23"}`. The
  profile has `(allow network*)`, and the 2026-10-18 herdr deny covers only
  unix sockets under `~/.config/herdr/`.

So a sandboxed agent can likely get an interactive pty on, type into, or
launch commands in any herdr pane, which are the user's unsandboxed shells.
That is the PRD 00160 Q2 escape again, through a second door. It may also be
able to approve its own Claude permission prompts (`/v1/approvals/answer`).
And it may be able to read files the profile denies (`/v1/files/download`
runs as the unsandboxed daemon: `~/.ssh` keys, `~/.config/warrant`). Whether
`files/download` limits paths is unknown; the string "refusing to rename the
home directory" shows some path guards exist elsewhere.

## Problem

Since 2026-10-18, sandboxed agents reach herdr only through `herdr-relay`,
which forwards three display-only methods. The Moshi gateway gives the same
agents a second potentially wider path to the same panes; whether action
routes require a credential remains unverified. The user installed Moshi to answer
agent questions and approvals from the phone, and per their 00160 Q2 rule
("either we find a solution that is still usable or we have to live with the
risk") that feature must keep working.

## Requirements (proposed)

### Must have

1. **Agents cannot reach the configured TCP gateway or web proxy.**
   `ai-agents.sb` denies
   network-outbound to `127.0.0.1:24543` and to the web client's
   `127.0.0.1:24544`, next to the herdr deny, with a comment naming Moshi
   and this discovery. Form to validate first: `(deny network-outbound
   (remote ip "localhost:24543"))`. The SBPL syntax is unverified, so compile
   it with `sandbox-exec` on the host, as for the herdr deny.
   Qualify actual configured listeners and address families, including IPv6
   when enabled; fixed IPv4 tests alone do not establish endpoint isolation.
   Include a configuration-drift check that fails if a live gateway/proxy
   address changes beyond the tested deny. The upstream CLI permits a
   configurable gateway bind, so this is part of the TCP mitigation's scope.
2. **The hook socket stays open.** Sandboxed Claude, Codex, Copilot, pi and
   Gemini sessions keep writing events to `moshi-hook.sock`, so the inbox,
   notifications and phone answers keep working. The user's own callers
   (sshd sessions from the phone, the `moshi` web client run by the user) are
   unsandboxed and unaffected.
3. **Proof after install, from a new run-agent session:** `moshi-hook probe
   --json` shows `"gateway":false` with `"running":true`. A question asked by
   that session still appears in the Moshi app and can be answered from it.
   A raw TCP connect to `127.0.0.1:24543` fails with EPERM.
4. **warrant still reads the profile the same way.** `load_profile` gives the
   same write roots (it ignores deny forms), checked as in the herdr install.
5. **State the remaining authority boundary.** Before claiming phone features
   are preserved or all Moshi escapes are closed, inspect the hook paths and
   retained Unix-socket protocol using source or equivalent read-only evidence.
   Establish whether sandbox callers can invoke pane control, approvals or
   protected-file reads through that socket. If unavailable, label the socket
   unverified and the change a TCP-only mitigation; do not silently deny it or
   certify it display-only. No action-route probe is authorized by this doc.

### Nice to have

- Ask upstream (rjyo/moshi) for a gateway credential kept outside agent reach
  (Keychain, or a 0600 file under a dir agents cannot read), or a gateway on
  a unix socket with a peer-uid and process check.
- A one-line `ai-agents.sb` comment that lists every unsandboxed local
  control API reviewed so far (herdr, Moshi), so the next one is checked the
  same way.

### Out of scope

- The other loopback listeners (`lsof -iTCP -sTCP:LISTEN`, 2026-10-18):
  syncthing GUI/API `127.0.0.1:8384` (API key in its config, agent-readable
  unless denied), Lens kube proxy `127.0.0.1:63835` (kube API with the user's
  credentials, although `~/.kube` reads are denied), Proton Bridge IMAP and
  SMTP `1143`/`1025`, Dropbox `17600`/`17603`, CleanMyMac `54321`, Kiro
  helper, Adobe, several `ddb` and `llama-server` ports. Same question per
  service, not checked here. They belong in one sweep discovery of their own.
- Changing what the unix socket accepts beyond hook events. Qualification of
  its existing authority is a prerequisite to broader claims, not permission
  to redesign or block it in this change. Symbols show an approval
  bridge that waits for answers (`approvalWaitFor`,
  `LocalApprovalBridge.AnswerApproval`) and plan prompts for Codex
  (`openCodexPlanPrompt`). A sandboxed agent can at least send fake events,
  for example a fake approval card on the phone. Whether a socket message
  can type into a pane is unknown and needs the source.
- Pairing Moshi to the cloud. Once paired, the WebSocket brings remote
  approvals. That is the user's choice and does not change the local gateway
  question.

## Constraints

- Nested `sandbox-exec` fails inside a session, so the profile change is
  validated and installed on the host through warrant, as for the herdr
  relay (`validate_relay.sh`, `install_relay.sh` in session 523838c3).
- Profile changes are a security-boundary change. The user approves them,
  and only sessions started after the install pick them up.
- Do not exercise the gateway's action routes to "prove" the escape. Reading
  the source is the safe proof. The source is not on disk; it would be
  `github.com/rjyo/moshi` if public.

## Codebase Context

- **Relevant files**: `~/Library/LaunchAgents/app.getmoshi.moshi-hook.plist`;
  `~/Library/Application Support/Moshi/{service.log,hook.log,moshi-hook.sock}`;
  `~/.config/moshi/config.toml`; hook wiring in `~/.claude/settings.json`
  (11 `moshi-hook claude-hook` entries, `PermissionRequest` synchronous) and
  `~/.codex/hooks.json` (`moshi-hook codex-hook`).
- **Pattern to reuse**: the herdr fix (buvis `082c8778`): a deny next to
  `(allow network*)` in `~/.config/seatbelt/ai-agents.sb`, host validation
  inside the candidate profile, then one warrant install that tests,
  compiles, verifies and commits.
- **Similar implementation**: `~/bin/herdr-relay`. It is not needed here:
  no in-session caller is currently known to need the gateway, so a TCP deny
  is the proposed narrow mitigation. Qualify hook transport and retained-socket
  authority before claiming preserved behavior or a closed escape class.

## Success Criteria

- From a run-agent session started after the change, `moshi-hook probe
  --json` reports `"gateway":false`, and a TCP connect to `127.0.0.1:24543`
  fails.
- From the same session, a Claude question (AskUserQuestion) shows in the
  Moshi app and the user's answer reaches the pane.
- The user's phone, or the local web client, still answers questions in
  sessions as before.
- `~/bin/tests` stay green on the host; warrant reads identical write roots
  from the new profile.
- Listener fixtures cover changed ports and enabled address families. A
  passing TCP check never certifies the unverified Unix-socket route closed.
- Record source/read-only evidence for hook transport and socket authority,
  or explicitly retain those claims as unverified before PRD acceptance.

## Risks

- **A hook needs the gateway.** If `claude-hook` or `codex-hook` calls
  `127.0.0.1:24543` for some event (the binary's `hook` code paths were not
  traced), that event breaks in sandboxed sessions. Mitigation: check
  `hook.log` and the Moshi app after the install. If something breaks, add
  a relay for the routes the hook needs, as with herdr.
- **The port changes.** `--gateway-listen` and `MOSHI_HOOK_GATEWAY_LISTEN`
  move the gateway. A Moshi update or a setting change would then reopen the
  door. Mitigation: a `~/bin` test, or the sweep discovery above, that reads
  the plist and `service.log` for the gateway address and checks it against
  the profile. This drift check is required by Must-have 1, not optional.
- **Residual after the deny.** Agents can still send fake events on the
  socket. Display only, if the socket cannot type into panes (unknown, see
  Out of scope).
- **SBPL `remote ip` syntax.** If `localhost:24543` does not compile, try
  `(remote tcp "localhost:24543")` or `"*:24543"`, and validate each on the
  host.

## Open Questions

1. Deny the gateway for agents now (recommended), wait for an upstream
   credential, or accept the risk until then? The deny keeps the phone
   features only if the hook-transport qualification confirms no sandboxed
   caller needs the gateway.
2. How do you answer from the phone today: over SSH (Easy Pair) into this
   Mac, or with the local `moshi` web client? Both stay unsandboxed and keep
   working, but the answer decides what to test after the install.
3. Should one sweep discovery cover the other loopback services (syncthing
   API, Lens kube proxy, Proton Bridge and the rest)?
4. Open an upstream issue at rjyo/moshi for gateway auth? That publishes the
   finding outside this machine, so it is your call.
5. **Evidence gate:** do action routes authenticate callers, and what control
   authority does the retained Unix socket expose? Inspect source or equivalent
   read-only evidence; otherwise keep both conclusions explicitly unverified.
6. **TCP qualification:** what gateway/proxy addresses and address families
   does the installed configuration enable, and how is drift detected?

## Discovery Log (2026-10-18)

These seeded answers preserve the original reasoning. Current requirements
and the review below qualify their unverified transport and authority claims.

### Q1: Is the gateway reachable from a sandboxed agent?
**Answer** (verified): yes. Moshi's own read-only probe, run in this
sandboxed session, reported `"gateway":true`. The profile allows `network*`.

### Q2: Does the gateway check who calls it?
**Answer** (inferred from the binary, not tested): no check was found. The
handlers are `loopback*`, the listen check only requires a loopback address,
and the agent-readable config holds no key. Testing an action route would
mean acting on a pane, so it was not done.

### Q3: Relay or deny?
**Answer**: deny. The herdr relay exists because the in-session hooks need
three herdr methods. The Moshi hooks use the unix socket, not the gateway,
so agents lose nothing they use. Relaying the gateway would mean filtering
a wide HTTP API for no in-session caller.

### Q4: Deny the unix socket as well?
**Answer**: no. That would cut the inbox, notifications and phone answers
for every sandboxed session, which gives up the feature the user installed
Moshi for. It stays open, and its residual is recorded under Risks.

## Next step

After your answers, `/create-prd 00173` for one small PRD: the profile deny,
host validation inside the candidate profile, and one warrant install, the
same shape as the herdr relay install.

## Discovery review (2026-10-18)

All five standard-depth lenses ran. F9 (Integrity, Blocking), option 1:
separate observed reachability from inferred control authority, scope the
proposed mitigation to actual TCP listeners, and qualify the retained socket
before broader safety/usability claims. Source unavailability does not prove
the socket safe. Authentication and socket behavior remain unresolved evidence
gates; the port-deny proposal is not deployment authorization.
No gateway action, upstream message, profile edit or service change ran.
The upstream [settings documentation](https://getmoshi.app/docs/hook-settings)
confirms configurable gateway binding; it does not prove installed-version
authentication or socket restrictions.

## PRD coverage check (2026-10-18)

PRD created: yes, [00179](/Users/bob/.claude/docs/dev/project-management/prds/backlog/00179-prepare-moshi-tcp-isolation-and-qualification-v1.md) (backlog), saved 2026-10-19.
The earlier no-match audit was superseded by the requested PRD creation.

### Elicitation refresh

Elicitation remains open on the phone workflow and acceptable mitigation. Live plist starts moshi-hook serve without listener overrides; the profile has the herdr socket deny and no Moshi TCP deny. These file reads do not establish live listeners, gateway authentication or socket authority. Preserve read-only qualification and phone round-trip acceptance gates; no action route, service, profile or upstream issue was touched.

These are code-derived findings and planning defaults, not new user answers
or a new discovery-review pass. Existing Discovery Log answers remain valid.

## PRD creation (2026-10-19)

Specified as [00179](/Users/bob/.claude/docs/dev/project-management/prds/backlog/00179-prepare-moshi-tcp-isolation-and-qualification-v1.md). The user requested creation of the missing PRDs.
The earlier elicitation and review entries remain historical evidence.
The PRD records final authoring defaults, dependency ordering and scope.
Implementation uses an isolated checkout and headless acceptance checks;
live deployment and host-only operational steps remain separate.
Template, guess-density and grounding gates passed before saving.

This slice delivers candidate generation and qualification tooling. It does
not claim live TCP isolation, phone compatibility or verified socket authority.
