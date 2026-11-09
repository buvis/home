# iPhone/iPad apps that leverage herdr-core: Research Report

Date: 2026-11-07. Yardstick: herdr-core 0.1.18 (`hc schema`, OpenRPC, protocol generation 1), Herdr desktop app 0.1.13, both installed on this machine.

## Executive summary

No iPhone or iPad app fully leverages herdr-core today. Nine iOS clients touch it, at very different depths, and the only one that covers most of the API (attach stream, events, templates, `terminal.put`, status kind/progress, sub-agents) is **Heeler 0.1.18**, which on 2026-11-07 was a TestFlight pre-release; the App Store build, 0.1.17, still only speaks to the old herdr TUI socket ([Heeler releases](https://github.com/ZingerLittleBee/Heeler/releases), [issue #649](https://github.com/ZingerLittleBee/Heeler/issues/649)). Two build-from-source projects, **herdr-ios** and its fork **herdr-pocket**, are the only ones that also *write* the desktop app's layout document (`doc.set` with version check) and run Herdr mods on the phone, but they need iOS 26 and were last tested against hc 0.1.14 ([herdr-ios](https://github.com/zzulanas/herdr-ios), [herdr-pocket](https://github.com/YosukeIida/herdr-pocket)). **Herdcats** (TestFlight, GPLv3) speaks framed `hc connect` with events, read, send, keys, interrupt, put and `doc.get`, but polls `terminal.read` instead of attaching and ignores blocked state and sub-agents ([PR #143](https://github.com/zhiyao/herdcats/pull/143)). **hc-ios** is a plain-mode JSON-RPC poller with ntfy push ([hc-ios](https://github.com/nguyenhuy158/hc-ios)).

The App Store apps that advertise herdr-core are shallow or opaque: **TermRover 1.4** draws the Herdr app's spaces, tabs and panes natively and syncs layout edits both ways, but documents no mechanism and is closed source ([TermRover blog, 2026-11-06](https://termrover.sh/blog/herdr-app-on-mobile/)); **Moshi 4.2.5/4.3.0** lists cores in its session picker and opens hc agents in their own terminal, mechanism undocumented ([App Store](https://apps.apple.com/us/app/id6757859949), [Moshi article, 2026-11-04](https://getmoshi.app/articles/herdr-core-vs-tui)); **Herdy 1.3.0** reattaches `hc` terminals over SSH/Mosh and has one review calling it laggy ([App Store](https://apps.apple.com/app/id6807917079)). **herdrup**, the app most often named as "the Herdr iOS app", does not use herdr-core at all: it needs the author's fork of the old TUI daemon ([herdrup README](https://raw.githubusercontent.com/jerryfane/herdrup/main/README.md)). The Herdr project ships no mobile app and names none on a roadmap; herdr.dev only says the core API is "open to other clients, such as a phone app" ([herdr.dev/core](https://herdr.dev/core/)). Parts of the API no client uses yet: `terminal.wait`, `terminal.send` with `force`/`if`, `file.read`/`file.edit`, `machine.list`/`machine.add`, `server.restart`.

## The yardstick: herdr-core 0.1.18's surface

From `hc schema` on this machine (info: "JSON-RPC 2.0, one message per line on the hc socket (or framed after `hello`). Protocol generation 1."). Remote clients run `ssh box hc connect` and speak the same protocol on stdin/stdout.

| Group | Methods and facts a mobile client can use |
|---|---|
| Handshake | `hello {generation, framed, features}` returns `version`, `methods`, `features`. Framed mode is required for `terminal.attach`. |
| Terminals | `terminal.list/get/run/kill/rm/keep/label`, `terminal.read` (screen plus `lines` of history), `terminal.attach {cols, rows, display, history, observe, resumed, resize_notifications}` returning a stream channel with DATA/RESIZE/FOCUS/FACTS/CREDIT/CLOSE frames. |
| Talking to agents | `terminal.send {text, force, if, wait}`, `terminal.keys`, `terminal.interrupt`, `terminal.wait`, `terminal.put` (a file beside the terminal, e.g. a photo). |
| Status | OSC 7501 record on each terminal: `state` idle/working/done/blocked/error, `kind` permission/question/auth, `msg`, `progress` 0..100, `app`, `title`; plus `turn`, `title`, `foreground`, `first_message`, `parent` (sub-agents), `labels` (`herdr.space`, `herdr.tab`), `template`. |
| Live data | `events.subscribe {terminal, children_of, labels}`: snapshot then created/lost/restarted/keep/finished/removed/status/turn/title/labels/size/doc events, heartbeat 15 s, `missed` with fresh snapshot. |
| Desktop app layout | `doc.get`/`doc.set` (versioned opaque JSON; the Herdr app keeps spaces, tabs and panes in the `herdr-app` doc, so a phone can read and edit the window). |
| Machines | `machine.add/list/connect/rename/rm`; terminals on other machines appear as `name/tN`; `on` on run/exec/file/doc. |
| Files and commands | `machine.exec` (base64 output), `file.read/write/edit` here or on a machine. |
| Roles | `templates.list`; `terminal.run` with a template name as `argv[0]` plus the task. |
| Core | `server.status/stop/restart`, `rpc.discover`. |

Stability: herdr-core calls the API "preview (protocol generation 1, version 0.x)", grows-only with a CI check against removals ([schema/README](https://github.com/herdrdev/herdr-core/blob/master/schema/README.md), via agent fetch).

## Landscape

| App | Where | herdr-core depth | Transport | Price, license | Floor |
|---|---|---|---|---|---|
| Heeler for herdr 0.1.18 (ZingerLittleBee) | TestFlight pre-release 2026-11-06; App Store has 0.1.17 (TUI only) | Deep: framed attach, events, templates, put, status kind/progress, sub-agents, `doc.get`, Chat, Blocked cards, Host Helper push and Live Activity | libssh2, direct-streamlocal to the core socket on Unix, `herdr-core connect` exec on Windows; libghostty renderer | Free, Apache-2.0, 797 stars | iOS 18+ (0.1.17 listing) |
| herdr-ios (zzulanas) | Source only | Deep: framed attach, events, `doc.get`/`doc.set` with CAS, `terminal.run` with `herdr.space`/`herdr.tab` labels, keep, label, kill, sub-agents, `machine.exec`, mods in JavaScriptCore | Citadel SSH exec of `herdr-core connect`; SwiftTerm | Apache-2.0, 4 stars, 12 commits | iOS 26; min hc 0.1.11, tested 0.1.14 |
| herdr-pocket (YosukeIida) | Source only | Same as herdr-ios plus Codex chat, Files and Changes views through `machine.exec`, QR pairing with a restricted `command=` key | Same | Apache-2.0, 44 commits | iOS 26; min hc 0.1.11 |
| Herdcats (zhiyao) | TestFlight; App Store publish being prepared (commit 2026-11-03) | Medium: framed hello, events, `terminal.read` snapshots, send, keys, interrupt, put, `doc.get` with `on`; no attach, no blocked handling, no sub-agents, no templates | Citadel SSH exec; text snapshots, no emulator on the core path | GPLv3 with App Store permission, 162 commits | iOS 17 |
| hc-ios (nguyenhuy158) | Source or SideStore IPA | Light: plain-mode JSON-RPC, `terminal.list`, `terminal.read` every 1.5 s, send, keys; `events.subscribe` only as a refresh tick; ntfy push script | Citadel SSH exec of `hc connect` | Apache-2.0, 22 commits | iOS 17 |
| TermRover 1.4.0 (Anh Trinh) | App Store, 2026-11-06 | Advertised deep (native panes, two-way layout and zoom sync, agent fleet with status, start herdr-core from the picker); mechanism undocumented | SSH only, no Mosh for app tabs; closed source | Free tier; Pro $24.99 and $79.99 tiers listed | iOS 17 |
| Moshi 4.2.5 and 4.3.0 | App Store | Shallow: session picker lists named cores, Inbox opens hc agents in their own terminal; docs still TUI-only | SSH/Mosh terminal; "no scrollback over Mosh for herdr-core terminals" | Free tier; Pro $7.99/mo or $69.99/yr | iOS 17 |
| Herdy 1.3.0 (WEM Creative Studio) | App Store | Shallow: lists core terminals and parent/worker trees, reattaches over SSH or Mosh; not an API client | SSH/Mosh | $2.99, one rating (2.0, "laggy") | iPadOS 15 |
| herdrup 1.2.0 (Jerry Fanelli) | App Store | None: needs the jerryfane/herdr fork of the TUI daemon (`herdr api-bridge`, `agent.list`, `pane.*`) | SSH | Free with tips, Apache-2.0 | iOS 17 |

Not iOS but relevant: **herdr-mobile-relay 0.25.0** (PWA, AGPL) added an hc relay tested on core 0.1.18 on 2026-11-06 ([pkg.go.dev](https://pkg.go.dev/github.com/0cv/herdr-mobile-relay)); **Collie** (PWA, MIT) has an experimental `COLLIE_MUX=herdr-core` mode ([GitHub](https://github.com/AltanS/collie)). **Herdr Mobile** on Android (`dev.herdr.mobile`) is a community TUI client by tuan3w, not an official app, and has no iOS build ([GitHub](https://github.com/tuan3w/herdr-mobile)). Sherpr (Android) and herdr-phone (PWA) are TUI only.

## Coverage matrix, verified in source

"Yes" cells were found as the literal method string in the repo's Swift sources (snapshot 2026-11-07, `main`); "No" means the string was searched for and not found in the files read. TermRover and Moshi are closed, so they are absent here.

| hc feature | Heeler (core path) | herdr-ios | herdr-pocket | Herdcats | hc-ios |
|---|---|---|---|---|---|
| `hello` framed | Yes | Yes (`HerdrClient.swift:101`) | Yes | Yes (`CoreRPCClient.swift`) | No (plain mode) |
| `terminal.attach` + RESIZE/FOCUS/FACTS | Yes, all three frames (`HerdrCoreAttach.swift`) | Yes; RESIZE and FOCUS sent, FACTS defined but unused | Yes | No (frame kinds parsed, attach never called) | No |
| `terminal.read` | Yes (`lines: 0`) | Yes | Yes | Yes (`lines: 0`, one request per read) | Yes (`lines: 200`, 1.5 s poll) |
| `events.subscribe` and event kinds | Yes, all kinds | Yes, all kinds (`EventLines.swift`) | Yes | Yes, all kinds (`CoreSnapshot.swift`) | Tick only, then refetch list |
| `terminal.run` plain | Yes | Yes, with `herdr.space`/`herdr.tab` labels, `keep`, `env` | Yes | No | No |
| `terminal.run` with template, `templates.list` | Yes (`HerdrCoreTransport.swift:202,584`) | No | No | No | No |
| `terminal.send` | No; typing goes through the attach stream (ADR 0035) | Yes | Yes | Yes | Yes |
| `terminal.send` with `force` or `if` | No; Composer refuses to send while Blocked | No | No | No | No |
| `terminal.keys` | No (attach stream) | Yes | Yes | Yes (live typing, ASCII only) | Yes |
| `terminal.interrupt` | Yes | Yes | Yes | Yes | No (sends ctrl+c) |
| `terminal.wait` | No | No | No | No | No |
| `terminal.kill` / `rm` / `label` / `keep` | kill, label; keep via run param | kill, label, keep | kill, label, keep | No | No |
| `terminal.put` (attachments) | Yes (`:566`) | No | No | Yes | No |
| `machine.exec` | No | Yes (chat transcript, push token) | Yes (plus Files, Changes via python/git) | No | No |
| `file.read` / `write` / `edit` | write only (installs its Windows extension) | No | No | No | No |
| `doc.get` / `doc.set` (`herdr-app` layout) | get only; renames go through the desktop app | get and set with conflict retry (`AppStore.swift:744`) | get and set | get, with `on` per machine | No |
| `machine.list` / `add` | No | No (probe tool only) | required-list only | No (parses `name/tN`) | No (parses prefix) |
| `server.status` keepalive | Yes | Yes | Yes | No | No |
| Sub-agents via `parent` | Yes | Yes (`Contracts.swift:73`) | Yes | No | No |
| `status.kind` / `progress` decoded | Yes (`HerdrCoreEvent.swift:7-30`) | No (state and app only) | No | No | msg only |
| Push path | Host Helper (Node service, E2E relay, Live Activity, needs macOS/Linux with systemd) | `herdr-notify.py` on the box runs `hc events --json`, posts to APNs with the user's own key | Same, plus install script | None found | `hc-notify.py` runs `hc connect` + `events.subscribe`, pushes via ntfy.sh |

Heeler's own limits on herdr-core hosts, from its guide (checked against hc 0.1.18 on 2026-11-06): agents cannot be renamed; workspace rename, worktrees, Changes and Host Helper need macOS or Linux with the desktop app running; native Windows gets workspaces, statuses, terminals, Send, Stop, attachments and Chat only ([guide](https://github.com/ZingerLittleBee/Heeler/blob/main/docs/guides/herdr-core.md)). One commenter on Hacker News and issue #649 confirm that 0.1.17 on the App Store does not detect herdr-core.

## Per-app notes

**Heeler.** Independent of the Herdr project. On Unix it opens an SSH direct-streamlocal channel to the core's socket rather than exec'ing `hc connect`, so the core need not be on `PATH`; on Windows it runs `herdr-core connect`. Its `hello` requires features framed, attach, events and status. Chat binds to Claude Code, Codex (`--no-daemon`), Grok Build, Pi and Oh My Pi conversations and answers Blocked cards for those; raw sends are refused while an agent is blocked, which matches `hc send`'s own rule. The Host Helper gives encrypted push, banners, Live Activity and Usage without a vendor account. 5.0 from 17 ratings on the App Store, 5k+ downloads per a third-party counter.

**herdr-ios and herdr-pocket.** The closest to "a phone edition of the Herdr app": they read the `herdr-app` doc for spaces and tabs, write it back with compare-and-set, start terminals with the same `herdr.space`/`herdr.tab` labels the desktop uses, keep lost terminals as shells, show sub-agents nested under parents, and run Herdr mods in JavaScriptCore. Costs: iOS 26 only, push needs a paid Apple Developer APNs key plus a box-side Python service, `hc machine add` machines are not browsable, and neither README claims a test against 0.1.18 (herdr-ios last commit 2026-11-06, herdr-pocket 2026-11-01).

**Herdcats.** Auto mode probes a host for both the TUI and `hc`, keeps one entry per runtime, and checks `hello.methods` for `terminal.list/read/send/keys/interrupt` and `events.subscribe`. Core panes are read, type and compose only; layout edits, native Timelines and structured approvals exist only on its TUI path. Non-ASCII typing is refused ("use Compose"). A 2026-11-06 security-hardening commit and 2026-11-04 docs commits show active core work. PR #143 itself said the core path was "not yet tested end to end on device".

**hc-ios.** Deliberately minimal: no terminal emulator, text screens polled at 1.5 s, OSC 7501 status with non-reporting programs shown as Idle, QR pairing script, push through ntfy.sh. Free Apple ID builds expire after 7 days (SideStore).

**TermRover 1.4.** The blog post describes native pane layout, resize, rearrange and zoom with the Mac window following phone edits and zoom shared both ways, a sidebar of spaces and tabs, a fleet view with status from both Herdr generations, a `tui | app` toggle per host, and "Call My Agent" voice reaching app panes. That behaviour implies `doc.get`/`doc.set` and per-terminal streams, but nothing on termrover.sh or the App Store names a method, frame protocol, status source or push path, and the only public repo is a feedback tracker. Mosh is not supported for app tabs.

**Moshi.** Verified only by App Store release notes: 4.2.5 "herdr-core support", "Inbox opens herdr-core agents on their own terminal"; 4.3.0 "Session picker lists named herdr-core cores" (relative dates, roughly 2026-11-02 and 2026-11-04). Its docs pages (`/docs/herdr`, `/docs/multiplexer`, `/docs/hooks`) still describe `herdr session list --json` and `$HERDR_ENV`, which are TUI. Its article says the "driver polls the Herdr window every 500ms" and that herdr-core terminals have no scrollback over Mosh. Approval push is through `moshi-hook`, which installs the agents' own hooks, not hc's status.

**Herdy.** 1.3.0 notes: "Herdr Core support ... requires hc on your SSH host", lists core terminals and parent/worker trees. Reattach model, not an API client.

**herdrup.** Transport is SSH plus `herdr api-bridge` per command; methods `agent.list`, `agent.read`, `agent.transcript`, `events_v2`, `pane.input.stream`, `pane.send_text`; "You need the fork that adds the gram / push / live-terminal APIs". herdr.dev states the app and the TUI "don't share agents", so herdrup cannot see a herdr-core agent. Its "agent:herdr-app" issue label is a CI tag, not an integration.

## What "fully leveraging" would add

Gaps no shipping client fills, each a concrete hc 0.1.18 feature:

1. **Approvals as first-class.** Decode `status.kind` (permission, question, auth), `msg` and `progress` into a Live Activity or lock-screen card (only Heeler decodes them; only its Chat answers them, for five agents). Answer with `terminal.keys` and confirm with `terminal.wait`, which nobody calls, instead of re-reading screens.
2. **Guarded sends.** `terminal.send {if: "idle"}` prevents typing into a working agent; `force` is the explicit override for a blocked one. No client passes either.
3. **Roles from the phone.** `templates.list` plus `terminal.run [template, task]` gives a "New reviewer on repo X" button; only Heeler has it.
4. **Machines.** `machine.list` and `machine.add` exist; every client either ignores `hc machine` machines or only splits the `name/tN` prefix.
5. **Files without Python.** `file.read`/`file.edit` with `on` replace the python and git shell-outs that herdr-pocket and Heeler use for Files and Changes.
6. **Layout as the shared truth.** `doc.set` with version check on `herdr-app` lets the phone rearrange the desktop window (herdr-ios does this; TermRover appears to; Heeler and Herdcats read only).
7. **Resume after suspend.** iOS kills background sockets; `terminal.attach {resumed: true}` and `events.subscribe`'s `missed` snapshot exist for exactly that reconnect, and `hc events` is what every push helper tails. All three open-source push paths need a box-side service plus either an Apple key (herdr-notify), a public ntfy topic (hc-notify) or the vendor relay (Heeler); hc itself has no push.
8. **Images.** `terminal.put` then paste the path: Heeler and Herdcats do it, the herdr-ios family does not.

## Recommendation

- To use herdr-core from an iPhone or iPad now: **Heeler 0.1.18 TestFlight**, then Heeler on the App Store once 0.1.18 ships. Free, Apache-2.0, deepest coverage, works with the desktop app on this Mac over Remote Login.
- To read and edit the desktop layout from the phone with open code: **herdr-ios** or **herdr-pocket**, built with Xcode, on an iOS 26 device, after a test against 0.1.18.
- **Herdcats** if a lighter GPLv3 client with a TUI/core auto-probe is enough and attach-quality terminals are not needed.
- **TermRover 1.4** if a polished closed App Store app with native panes is preferred over knowing the mechanism.
- Skip **herdrup** for herdr-core; it is a TUI-fork client.

## Information gaps

- Nothing was run against a live core; every coverage cell is static source reading on 2026-11-07, limited to the transport, client, store, notifier and docs files of each repo. A method used only in an unread view could be missed.
- Heeler 0.1.18 release notes were truncated in the fetch; the App Store date for it is not known. Its iOS floor for 0.1.18 was not checked.
- TermRover's and Moshi's mechanisms (connect vs attach, status source, push) are undocumented; only their binaries or the makers could answer.
- Moshi's 4.2.5 and 4.3.0 dates are relative ("5d ago", "3d ago") on the store page.
- Herdcats' App Store release and price were not found; TestFlight only.
- Heeler's push relay internals were not read. The Play Store page for Herdr Mobile did not render; its maker is inferred from a search snippet.
- WebFetch summaries come from a small model; quotes marked as verbatim were re-checked only where the agent downloaded the raw file (Heeler, herdr-ios, herdr-pocket, hc-ios).

## Sources

1. `hc schema` and `hc --skill` on this machine (herdr-core 0.1.18, herdr-app 0.1.13)
2. https://herdr.dev/core/ and https://github.com/herdrdev/herdr-core/blob/master/schema/README.md
3. https://github.com/ZingerLittleBee/Heeler (releases, issues/649, `Sources/Heeler/Transport/HerdrCore/*.swift`, `docs/guides/herdr-core.md`, `docs/adr/0031`, `0033`, `0035`)
4. https://apps.apple.com/app/id6797263135 and https://heeler.bybee.dev
5. https://github.com/zzulanas/herdr-ios (`Packages/HerdrKit/Sources/HerdrKit/*.swift`, `App/Sources/Store/AppStore.swift`, `App/Resources/Notify/herdr-notify.py`)
6. https://github.com/YosukeIida/herdr-pocket
7. https://github.com/zhiyao/herdcats and https://github.com/zhiyao/herdcats/pull/143 (`ios/Herdcats/Networking/*.swift`, `Models/CoreSnapshot.swift`, `CoreHierarchy.swift`)
8. https://github.com/nguyenhuy158/hc-ios (`HcIOS/Client/SSHHcClient.swift`, `Views/TerminalDetailView.swift`, `integrations/notify/hc-notify.py`)
9. https://termrover.sh/blog/herdr-app-on-mobile/ and https://apps.apple.com/us/app/id6775775553
10. https://apps.apple.com/us/app/id6757859949 (Moshi), https://getmoshi.app/articles/herdr-core-vs-tui, https://getmoshi.app/docs/herdr
11. https://apps.apple.com/app/id6807917079 (Herdy)
12. https://github.com/jerryfane/herdrup, its raw README, https://github.com/jerryfane/herdr, https://apps.apple.com/us/app/herdrup-agents-in-your-pocket/id6798087089
13. https://github.com/0cv/herdr-mobile-relay, https://github.com/AltanS/collie, https://github.com/tuan3w/herdr-mobile
14. https://www.bitdoze.com/md/best-herdr-clients.md (2026-10-08), https://flaviocopes.com/herdr-phone/ (2026-08-25)
15. https://news.ycombinator.com/item?id=50298436 (desktop app release thread)
16. https://dev.classmethod.jp/articles/reona-herdr-app-herdr-core/ (2026-11-04)
17. Comparison set, not herdr: https://code.claude.com/docs/en/remote-control.md, https://happy.engineering/docs/how-it-works, Forge Remote, CodeVibe, Punk Code App Store listings

## Methodology

Five research agents ran on 2026-11-07: herdrup; Heeler and other herdr clients plus the official position; comparable agent-remote iOS apps and iOS constraints; Moshi verification; source-level API mapping of herdr-ios, herdr-pocket, hc-ios and Heeler; plus one for Herdcats and TermRover. About 70 web searches and 150 fetches in total; GitHub code search was unavailable (login wall), so raw files and the GitHub tree API were used. The local hc 0.1.18 schema was the feature yardstick. Key cells (framed hello, attach, version floor, templates, put, the Heeler guide date) were re-grepped by the main session in the downloaded sources. Blind spots: Discord, X and Reddit were not searched directly; search was US-only; App Store dates are relative.
