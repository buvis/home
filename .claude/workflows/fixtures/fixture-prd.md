# PRD 00099: notify module

## Problem

Callers need to send one message to many recipients without hand-rolling a loop
and a length check every time.

## Requirements

1. `fanout(recipients, message)` delivers the message to **every** recipient and
   returns exactly one delivery record per recipient, in the order given. An
   empty recipient list returns an empty array.
2. `deliver(recipient, message)` returns `{ to, body, at }`, where `body` is the
   trimmed message.
3. `trimBody(message)` returns the message unchanged when it is at most 240
   characters, and otherwise a 240-character string ending in a single ellipsis.
4. `probeNotifier(done)` runs the notifier binary once with `--version` and calls
   back with `'ok'` or `'missing'`. The command is fixed; no caller input may
   reach the shell.

## Out of scope

- Retries, batching, and async delivery.
- Any notifier other than `notify-send`.

## Tests

Unit tests cover `trimBody` at and past the limit, and `fanout` over an empty
list, a single recipient, and several recipients.
