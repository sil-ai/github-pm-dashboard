# sil-ai PM Dashboard

A FastAPI dashboard for project management reporting across the [sil-ai](https://github.com/sil-ai) GitHub org.

## Tabs

- **Weekly Summary** -- commits, issues opened/closed, PRs merged (navigate between weeks)
- **Plans** -- ordered cross-repo checklists (stacked PRs, migrations, deploys) with tick-off
- **Overdue** -- aging P0/P1 issues, stale issues (30+ days), past-due milestones
- **Priorities** -- all open P0-critical and P1-high issues across the org
- **PR Status** -- open PRs with review status and requested reviewers
- **Repo Status** -- card overview of all active repos, click for detailed modal
- **My Tasks** -- assigned issues and open PRs for a team member

## Plans

A Plan is a `plan`-labelled GitHub issue in the repo where most of its work
happens, holding a flat checklist of ordered Steps. The dashboard gathers Plans
from across the org, shows live PR state beside each Step, and lets people tick
Steps off. See [PLAN-FORMAT.md](PLAN-FORMAT.md) for the format agents must
author, [CONTEXT.md](CONTEXT.md) for the vocabulary, and
[docs/adr/](docs/adr/) for why it works this way.

Create one from any repo with `/github-pm plan`.

## Prerequisites

- Python 3.10+
- [GitHub CLI](https://cli.github.com/) (`gh`) installed and authenticated with access to the sil-ai org

## Configuration

Set in `.env`:

| Variable | Purpose |
| -------- | ------- |
| `DASHBOARD_PASSWORD` | Shared login password. Unset means no auth. |
| `SESSION_SECRET` | HMAC key for the session cookie. |
| `OPENAI_API_KEY` | Commit summarisation. Unset disables it (503). |
| `GH_WRITE_TOKEN` | **Required to tick Plan steps.** A fine-grained PAT scoped to the sil-ai org with *Issues: Read and write* and nothing else. Unset makes the Plans tab read-only. |

`GH_WRITE_TOKEN` is deliberately separate from the token the read-only tabs use:
the dashboard has one shared password, so whatever that token can do, anyone who
knows the password can do. Keep it to issues.

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
