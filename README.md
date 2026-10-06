# sil-ai PM Dashboard

A FastAPI dashboard for project management reporting across the [sil-ai](https://github.com/sil-ai) GitHub org, plus the repos outside it that the team works in (`EXTRA_REPOS` in `dashboard.py`).

## Tabs

- **Weekly Summary** -- commits, issues opened/closed, PRs merged (navigate between weeks)
- **Maps** -- wayfinder maps across the team's repos: destination, frontier, claimed and blocked tickets, decisions so far
- **Overdue** -- aging P0/P1 issues, stale issues (30+ days), past-due milestones
- **Priorities** -- all open P0-critical and P1-high issues across the org
- **PR Status** -- open PRs with review status and requested reviewers
- **Repo Status** -- card overview of all active repos, click for detailed modal
- **My Tasks** -- assigned issues and open PRs for a team member. The member list is the sil-ai org, so someone who only works in an `EXTRA_REPOS` repo can't be picked; an org member's items there do show

## Maps

A map is a `wayfinder:map`-labelled issue created by the `/wayfinder` skill,
with its tickets as GitHub sub-issues. The Maps tab gathers open maps (and those
closed in the last 14 days) from across the team's repos and sorts each map's tickets
into frontier, claimed, blocked and closed, using the sub-issues' assignees and
native issue dependencies. It is read-only: tickets are claimed and resolved by
`/wayfinder` sessions, not from the dashboard. See [GLOSSARY.md](GLOSSARY.md)
for the vocabulary.

## Prerequisites

- Python 3.10+
- [GitHub CLI](https://cli.github.com/) (`gh`) installed and authenticated with access to the sil-ai org, plus read access to the repos in `EXTRA_REPOS` (`dashboard.py`) — currently `paranext/paratext-assistant` and `sillsdev/paratext-assistant-server`, both private

## Configuration

Set in `.env`:

| Variable | Purpose |
| -------- | ------- |
| `DASHBOARD_PASSWORD` | Shared login password. Unset means no auth. |
| `SESSION_SECRET` | HMAC key for the session cookie. |
| `OPENAI_API_KEY` | Commit summarisation. Unset disables it (503). |

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn jinja2
```

## Run

```bash
source .venv/bin/activate
uvicorn dashboard:app --reload --port 8050
```

Then open http://localhost:8050
