# sil-ai PM Dashboard

Project management reporting across the `sil-ai` GitHub org, plus the ordered
cross-repo Plans the team follows when work has to happen in a particular
sequence.

## Language

### Reporting

**Active repo**:
A non-archived `sil-ai` repo updated within the last 90 days. Org-wide reports
cover the active repos, not every repo.
_Avoid_: live repo, current repo

**Priority**:
The single `P0-critical` / `P1-high` / `P2-important` / `P3-strategic` label an
issue carries.
_Avoid_: severity, urgency, importance

### Plans

**Plan**:
An ordered sequence of work that has to happen in a particular order, usually
reaching across more than one repo. A Plan is authored once, followed over hours
or days, and finished.
_Avoid_: scratch, checklist, runbook, rollout, release, ticket

**Plan home**:
The repo whose issues hold a given Plan — the repo where most of its work
happens. There is no single home for all Plans; gathering them into one view is
the dashboard's job, not a repo's.
_Avoid_: registry, owner repo

**Step**:
One item in a Plan, and the unit that gets ticked. A Step says what to do, and
may name the repo it happens in, the PR or issue it concerns, and its Kind.
_Avoid_: task, item, todo, action

**Kind**:
What sort of act a Step is: `merge`, `migrate`, `deploy`, `verify`, or `manual`.
Kind is what says whether a Step's completion is something the dashboard could
ever observe, and `verify` is distinct because it is a gate rather than work.
_Avoid_: type, category

**Done**:
A named person's assertion that a Step has been carried out. Done is never
inferred, and it records who asserted it and when.
_Avoid_: complete, finished, closed, merged

**Live state**:
What GitHub currently reports about the PR or issue a Step references — open,
approved, merged, closed unmerged, CI failing. Live state is observed and moves
on its own; Done is asserted and moves only when a person says so.
_Avoid_: status, state, progress

**Next up**:
The first Step in a Plan that is not Done. It is a recommendation, not a gate:
Steps may be ticked out of order, and that is shown rather than prevented.
_Avoid_: current step, blocked, ready
