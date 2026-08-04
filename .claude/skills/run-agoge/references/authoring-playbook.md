# Authoring playbook

For the **master**, not a specialist. Every specialist is pinned to read-and-run
on purpose: a prober that can edit the thing it probes invalidates its own
result, and the run's whole ledger rests on the target being byte-identical after
the lanes finish. So the orchestrator authors, once, after the lanes report.

A specialist asked to author puts its test in the finding's `fix` field and
nothing on disk.

## When to author

All three must hold:

- the profile's **Authoring assignments** section names a surface and a runner,
- at least one finding survived the status audit as `verified`, and
- the target's working tree is clean.

Otherwise say in the report that nothing was authored, and why. Authoring on a
dirty tree would sweep someone else's work onto the branch.

## The branch

```bash
git -C <target> rev-parse --abbrev-ref HEAD        # remember where you were
git -C <target> switch -c agoge/authored-tests-<YYYY-MM-DD>
# ... write tests, run them ...
git -C <target> add <test paths only>
git -C <target> commit -m "test: cover <what> found by an agoge run"
git -C <target> switch -                            # back where you started
```

Never commit to the working branch. Never push. Never stage a file that is not a
test or its scaffolding (a config, a `conftest.py`, a fixtures directory). Prove
it: `git -C <target> status --porcelain` is empty when you are done, and the
branch you started on is the branch you end on.

## What the suite contains

Two kinds of test, and the mix is the point:

- **A defect test per verified finding**, marked expected-to-fail
  (`test.fail()`, `pytest.mark.xfail(strict=True)`, or the runner's equivalent).
  It fails today because the defect is real, so the suite still passes — and the
  day someone fixes the defect the annotation goes stale and the suite turns red,
  telling the fixer to delete it. That is a durable, executable record of the
  finding rather than a paragraph in a report nobody re-reads.
- **A characterization test per journey that works**, plain. It pins behaviour a
  future change would otherwise break silently.

A strict expected-failure is the fail-first requirement satisfied by
construction: the runner asserts the test *does* fail against the code as it
stands, so a test that passes for the wrong reason cannot slip through.

## Writing doctrine

- Name each test for the rule it enforces (`rejects_empty_title`), never for the
  function it calls (`test_validate`).
- Assert on outputs, returned values, persisted state and errors. Never on
  whether a mock was called.
- For each test ask: **what wrong implementation would still pass this?** If that
  is easy to answer, the test is too loose.
- Use real code paths. Mock only what leaves the machine.
- Follow the project's existing test conventions — its runner, its layout, its
  import style. If it has none, create the smallest scaffolding that makes the
  runner find the tests, and say in the report what you added.
- Do not add test-only hooks to production code. Do not touch non-test files.
- Cover only what the findings and the journeys establish. Six tests that bind to
  observed behaviour beat twenty that pad the count.

## Running before committing

Run the suite with the exact command the profile names, from the target, and
paste the summary line into the report. A suite that was not run is not a
deliverable. If it cannot run at all, commit nothing and report the lane
`unverified` with the failure.

## Reporting

The report names the branch, the runner command, the test count, and which
findings have a durable test. A finding with no test says so.
