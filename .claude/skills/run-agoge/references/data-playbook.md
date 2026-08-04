# Data playbook

For **heidi**. Every place this product talks to something else: a service, a
database, a queue, a file store, another component of itself.

## Live first, mocked second, never invented

Three outcomes, and the label is the finding's status:

| Situation | What you do | Status |
|---|---|---|
| The other side is reachable | Make the real call, read the real answer | `verified` |
| It is not reachable | Apply the profile's mocking strategy | `mocked` |
| You could not do either | Say what you tried and how far you got | `unverified` |

A mocked probe encodes what the author *believed* the dependency does. That
belief is exactly what breaks in production, so it never reports `verified`. And
never invent a credential to promote a probe from mocked to live.

## Standing up the project's own infrastructure

Only what the project ships: its compose file, its sqlite file, its dev server,
its seed script. Bring it up, use it, take it down **inside the same shell
invocation**, so nothing survives the call:

```bash
docker compose up -d db && trap "docker compose down -v" EXIT && <probe>
```

A background shell is not an option: a headless session kills it shortly after
the final result, so a service parked there dies mid-lane or leaks. Before you
finish, prove the containers, ports and temp databases you created are gone.

Never point a probe at a host that is not clearly the operator's own. If in
doubt, mock it and say so.

## Mocking: patch the seam, not the network

Patch the name **where the code uses it**, not where it is defined — the module
under test holds its own reference and a definition-site patch misses it:

```python
with patch("<package>.<module>.<client>.<call>", fake):
    ...
```

Then assert on what the product actually built: the URL, the headers, the body.
That is how a configured-but-ignored setting is caught, and it is invisible to a
mock that only returns a canned answer.

A local stub server is the weaker tool and sometimes a trap: if the product
resolves its target wrongly, the stub is never reached and its silence looks like
success. Check where the request *went* before trusting where it landed.

## What to probe, in order of value

1. **The error path.** Force it: unreachable host, bad credentials, malformed
   response, timeout. An error swallowed into a success-shaped answer is the
   highest-value defect in this lane, because nothing downstream can see it. A
   `200` carrying an empty list where the failure should have surfaced is the
   canonical shape.
2. **Configuration that is read and then ignored.** If the product prints or
   accepts a setting, prove the setting reaches the request. Printing it is not
   using it.
3. **Two consumers of one source disagreeing.** The page lists three rows and the
   API for the same data answers empty. Compare them directly; that contradiction
   is the finding, and it needs no reading of the code.
4. **Database behaviour, not schema.** Constraints that do not hold, migrations
   that do not round-trip, queries that silently return empty, a write that
   clobbers a concurrent one.
5. **Persistence across runs.** Corrupt input read as empty, a partial write, a
   missing parent directory, the second run meeting the first run's leftovers.

## Evidence

One line per contract probed: what you called, live or mocked, what came back.

```
GET http://127.0.0.1:4173/api/books -> 200 []   (live)
the catalogue page at / lists 3 books           (live)
```

Quote the call and the answer. A description of the contract is not a probe of
it. And do not modify the product to make a probe work — capture the request
instead of repointing the code.
