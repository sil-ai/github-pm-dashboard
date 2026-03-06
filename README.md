# sil-ai PM Dashboard

A FastAPI dashboard for project management reporting across the [sil-ai](https://github.com/sil-ai) GitHub org.

## Tabs

- **Weekly Summary** -- commits, issues opened/closed, PRs merged (navigate between weeks)
- **Overdue** -- aging P0/P1 issues, stale issues (30+ days), past-due milestones
- **Priorities** -- all open P0-critical and P1-high issues across the org
- **PR Status** -- open PRs with review status and requested reviewers
- **Repo Status** -- card overview of all active repos, click for detailed modal
- **My Tasks** -- assigned issues and open PRs for a team member

## Prerequisites

- Python 3.10+
- [GitHub CLI](https://cli.github.com/) (`gh`) installed and authenticated with access to the sil-ai org

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
