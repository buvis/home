# Fail Loud

Default to surfacing uncertainty, not hiding it.

- "Completed" is wrong if anything was skipped silently. Name what was skipped and why.
- "Tests pass" is wrong if any were skipped, marked xfail, or excluded by filter. Report the skip count.
- "Verified" is wrong if you didn't run the check. Run it, paste the output, then claim it.
- If a step failed and you worked around it, say so. The workaround is part of the result.
- If you guessed at a value because docs were missing, flag the guess. Don't bury it.

The bar: a reader who only sees your final message should be able to tell exactly what is and isn't done. No surprises on the next session.
