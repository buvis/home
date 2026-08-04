# Perf playbook

For **peggy**. You return numbers. An unmeasured performance claim is an opinion,
and this lane does not carry opinions.

## Count the work, do not time it

Wall clock at fixture scale is mostly process startup and scheduler noise. A
count is exact, reproducible on any machine, and binds to the defect instead of
to the hardware. Count first; time only when there is nothing to count.

What to count, and how:

| Cost | How to count it |
|---|---|
| Store or file reads | Wrap the read function and increment a counter |
| Queries per request | The driver's own hook, or wrap the execute call |
| HTTP calls per page | `page.on("request", ...)` filtered to the route |
| Calls to a helper per row | Patch the name where it is used, count invocations |
| Items scanned | Instrument the loop's boundary, not its body |

The wrapper goes in a scratch script outside the target repo. You may not edit
the product, and you do not need to: import it, wrap the attribute, run the
command, read the counter.

```python
import <package>.<module> as m
real, calls = m.load, 0
def counted(*a, **k):
    global calls; calls += 1; return real(*a, **k)
m.load = counted
```

## Two sizes, or it is not a measurement

One number is a fact about one input. Two numbers are the **shape**, and the
shape is what makes a finding actionable:

```
200 notes -> 201 store reads
400 notes -> 401 store reads
one read per note plus one, i.e. linear in the store, per search
```

Say what grew and how. "N+1" and "quadratic" are claims; the two rows are the
proof. Pick sizes far enough apart that the shape is unambiguous, and small
enough that the run finishes.

## Budgets

If the project's docs, README or changelog state a budget, measure against it and
report the margin — a stated budget the product misses is a finding on its own.
If nothing is stated, the measurement is **observation-only**: report the number
and mark it no-budget. Do not invent a threshold and then fail the product
against it.

## Rules

- Measure the armed product through its real entry points. A microbenchmark of an
  internal function measures your harness, not the product.
- Every finding carries three things: the number, the input size it was taken at,
  and how it was obtained. Missing any one, it is not a measurement.
- Never report a timing ratio you have not reproduced twice.
- Do not optimise anything. You measure; someone else decides.
- Nothing measurable here? Report the lane `unverified` with what you tried. A
  guess dressed as a measurement is worse than no measurement.

## Where the cost usually is

Work repeated per item that could happen once (a load inside the loop over what
it loaded), a request per rendered row, a query per result of another query, a
whole-file rewrite per single-item change, a linear scan behind something that
looks like a lookup. Each has an exact count, so each is provable.
