# Done is asserted by a person, never inferred from GitHub

The dashboard can see that a Step's PR was merged, and it is tempting to tick
that Step automatically. We do not. A merged PR is shown as Live state next to a
Step that stays unticked until a person ticks it.

The Steps that make a Plan dangerous — running a migration, deploying, verifying
an endpoint actually recovered — leave no trace the dashboard can observe. If
merge Steps ticked themselves and those did not, "ticked" would mean *observed*
on some Steps and *asserted* on others, and nobody reading the list could tell
which. A Plan is followed precisely because someone has to be accountable for
each Step, so every tick is one person's claim, stamped with who and when.

## Consequences

- Live state must distinguish merged from closed-unmerged, which the existing
  `/api/pr-status` cannot do (it searches `--state open`), so Step refs are
  fetched individually.
- An unresolvable ref and a closed-unmerged PR are shown as explicit warnings,
  never as blank space, so bad data can never read as progress.
- Ordering is advisory: "next up" is highlighted, out-of-order ticks are allowed
  and flagged. A gate the dashboard cannot verify would only be worked around.
