# sil-ai PM Dashboard

Project management reporting across the `sil-ai` GitHub org, plus a view of the
wayfinder maps the team uses to plan efforts too big for one agent session.

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

### Maps

These terms come from the `/wayfinder` skill (mattpocock-skills), which is the
canonical definition. The dashboard only reads them.

**Map**:
A `wayfinder:map`-labelled issue charting an effort too big for one agent
session. Its body holds the Destination, Notes, Decisions so far, Not yet
specified and Out of scope; its tickets are its GitHub sub-issues.
_Avoid_: plan, epic, roadmap

**Destination**:
What reaching the end of a Map looks like — a spec, a decision, or a change.
It fixes the Map's scope.

**Ticket**:
A sub-issue of a Map, labelled `wayfinder:<type>` (`grilling`, `prototype`,
`research` or `task`). A ticket asks a question; resolving it records a
decision. It is not a slice of implementation.
_Avoid_: step, task (except as the type)

**Frontier**:
A Map's open tickets that are neither blocked (by an open native GitHub
dependency) nor claimed (assigned). The first frontier ticket in sub-issue order
is shown as "next up".
_Avoid_: backlog, ready

**Claimed**:
An open ticket with an assignee. The assignee is the claim, so other sessions
skip it.

**Fog**:
The Map's "Not yet specified" section: decisions that can be seen coming but not
yet phrased sharply enough to ticket.
