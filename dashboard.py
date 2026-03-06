"""GitHub PM Dashboard for sil-ai org."""

import asyncio
import json
import logging
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("dashboard")

app = FastAPI()
templates = Jinja2Templates(directory="templates")


def run_gh(args: list[str], timeout: int = 60) -> str:
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh command failed: {result.stderr}")
    return result.stdout.strip()


def run_gh_json(args: list[str], timeout: int = 60) -> list | dict:
    out = run_gh(args, timeout)
    if not out:
        return []
    return json.loads(out)


def get_active_repos() -> list[str]:
    repos = run_gh_json([
        "repo", "list", "sil-ai", "--limit", "100",
        "--json", "name,updatedAt,isArchived",
    ])
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    return sorted([
        r["name"] for r in repos
        if not r.get("isArchived") and r["updatedAt"] >= cutoff
    ])


def days_ago(date_str: str) -> int:
    if not date_str:
        return 0
    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - dt).days


def fmt_date(date_str: str) -> str:
    if not date_str:
        return "N/A"
    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    return dt.strftime("%b %d, %Y")


def since_date(days: int = 7) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/active-repos")
async def api_active_repos():
    repos = get_active_repos()
    return JSONResponse(repos)


@app.get("/api/repo-summaries")
async def api_repo_summaries():
    repos = get_active_repos()
    log.info("Fetching summaries for %d repos in parallel...", len(repos))

    def fetch_summary(repo):
        try:
            issues = run_gh_json([
                "issue", "list", "--repo", f"sil-ai/{repo}", "--state", "open",
                "--json", "number,labels",
                "--limit", "200",
            ], timeout=15)
            prs = run_gh_json([
                "pr", "list", "--repo", f"sil-ai/{repo}", "--state", "open",
                "--json", "number",
                "--limit", "50",
            ], timeout=15)
            p0 = sum(1 for i in issues if any(
                (l.get("name", "") or "").startswith("P0") for l in (i.get("labels") or [])
            ))
            p1 = sum(1 for i in issues if any(
                (l.get("name", "") or "").startswith("P1") for l in (i.get("labels") or [])
            ))
            return {
                "name": repo,
                "issues": len(issues),
                "prs": len(prs),
                "p0": p0,
                "p1": p1,
            }
        except Exception as e:
            log.warning("  %s: failed (%s)", repo, e)
            return {"name": repo, "issues": 0, "prs": 0, "p0": 0, "p1": 0}

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = await asyncio.gather(
            *[loop.run_in_executor(pool, fetch_summary, repo) for repo in repos]
        )
    return JSONResponse(list(results))


@app.get("/api/org-members")
async def api_org_members():
    members = run_gh_json(["api", "orgs/sil-ai/members", "--jq", "[.[].login]"])
    return JSONResponse(sorted(members))


@app.get("/api/weekly")
async def api_weekly(start: str = "", end: str = ""):
    # Default: last 7 days ending today
    if end:
        end_dt = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        end_dt = datetime.now(timezone.utc)
    if start:
        start_dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        start_dt = end_dt - timedelta(days=7)

    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = end_dt.strftime("%Y-%m-%d")

    issues_closed = run_gh_json([
        "search", "issues", "--owner", "sil-ai", "--state", "closed",
        "--json", "repository,title,closedAt,assignees",
        "--limit", "200",
        "--", f"closed:{start_str}..{end_str}",
    ])

    issues_opened = run_gh_json([
        "search", "issues", "--owner", "sil-ai",
        "--json", "repository,title,createdAt,assignees,labels",
        "--limit", "200",
        "--", f"created:{start_str}..{end_str}",
    ])

    prs_merged = run_gh_json([
        "search", "prs", "--owner", "sil-ai", "--merged",
        "--json", "repository,title,updatedAt,author",
        "--limit", "200",
        "--", f"merged:{start_str}..{end_str}",
    ])

    # Commit activity per active repo (parallel)
    repos = get_active_repos()
    log.info("Fetching commits for %d repos (%s to %s)...", len(repos), start_str, end_str)

    def fetch_commits(repo):
        try:
            raw = run_gh([
                "api", f"repos/sil-ai/{repo}/commits?since={start_str}T00:00:00Z&until={end_str}T23:59:59Z&per_page=100",
                "-q", '.[] | {sha: .sha[:7], date: .commit.author.date, author: (.author.login // .commit.author.name), message: (.commit.message | split("\n")[0])}',
            ], timeout=15)
            if raw:
                commits = [json.loads(line) for line in raw.splitlines() if line.strip()]
                if commits:
                    log.info("  %s: %d commits", repo, len(commits))
                    return repo, commits
        except Exception as e:
            log.warning("  %s: failed (%s)", repo, e)
        return repo, None

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = await asyncio.gather(
            *[loop.run_in_executor(pool, fetch_commits, repo) for repo in repos]
        )
    commits_by_repo = {repo: commits for repo, commits in results if commits}

    return JSONResponse({
        "start": start_str,
        "end": end_str,
        "issues_closed": issues_closed,
        "issues_opened": issues_opened,
        "prs_merged": prs_merged,
        "commits_by_repo": commits_by_repo,
    })


@app.get("/api/overdue")
async def api_overdue():
    seven_days_ago = since_date(7)
    thirty_days_ago = since_date(30)

    aging_p0 = run_gh_json([
        "search", "issues", "--owner", "sil-ai", "--state", "open",
        "--label", "P0-critical",
        "--json", "repository,title,assignees,createdAt,updatedAt,url",
        "--limit", "100",
        "--", f"created:<{seven_days_ago}",
    ])

    aging_p1 = run_gh_json([
        "search", "issues", "--owner", "sil-ai", "--state", "open",
        "--label", "P1-high",
        "--json", "repository,title,assignees,createdAt,updatedAt,url",
        "--limit", "100",
        "--", f"created:<{seven_days_ago}",
    ])

    stale = run_gh_json([
        "search", "issues", "--owner", "sil-ai", "--state", "open",
        "--json", "repository,title,assignees,updatedAt,url",
        "--limit", "100",
        "--", f"updated:<{thirty_days_ago}",
    ])

    return JSONResponse({
        "aging_p0": aging_p0,
        "aging_p1": aging_p1,
        "stale": stale,
    })


@app.get("/api/priorities")
async def api_priorities():
    p0 = run_gh_json([
        "search", "issues", "--owner", "sil-ai", "--state", "open",
        "--label", "P0-critical",
        "--json", "repository,title,assignees,createdAt,updatedAt,url",
        "--limit", "100",
    ])

    p1 = run_gh_json([
        "search", "issues", "--owner", "sil-ai", "--state", "open",
        "--label", "P1-high",
        "--json", "repository,title,assignees,createdAt,updatedAt,url",
        "--limit", "100",
    ])

    return JSONResponse({"p0": p0, "p1": p1})


@app.get("/api/repo-status/{repo}")
async def api_repo_status(repo: str):
    issues = run_gh_json([
        "issue", "list", "--repo", f"sil-ai/{repo}", "--state", "open",
        "--json", "number,title,labels,assignees,createdAt,updatedAt,milestone,url",
        "--limit", "100",
    ])

    prs = run_gh_json([
        "pr", "list", "--repo", f"sil-ai/{repo}", "--state", "open",
        "--json", "number,title,author,createdAt,reviewRequests,url,body,headRefName",
        "--limit", "50",
    ])

    try:
        milestones = run_gh_json([
            "api", f"repos/sil-ai/{repo}/milestones",
            "--jq", "[.[] | {title, due_on, open_issues, closed_issues, state}]",
        ])
    except Exception:
        milestones = []

    fourteen_days_ago = since_date(14)
    recent_closed = run_gh_json([
        "search", "issues", "--repo", f"sil-ai/{repo}", "--state", "closed",
        "--json", "title,closedAt,assignees,url",
        "--limit", "50",
        "--", f"closed:>{fourteen_days_ago}",
    ])

    # Build issue-to-PR mapping from PR titles, bodies, and branch names
    issue_prs: dict[int, list[dict]] = {}
    for pr in prs:
        text = f"{pr.get('title', '')} {pr.get('body', '')} {pr.get('headRefName', '')}"
        refs = set(int(m) for m in re.findall(r'#(\d+)', text))
        # Also match "123" in branch names like "fix-123" or "issue-123"
        refs |= set(int(m) for m in re.findall(r'(?:^|[-_/])(\d+)(?:[-_/]|$)', pr.get('headRefName', '')))
        for num in refs:
            issue_prs.setdefault(num, []).append({
                "number": pr["number"],
                "title": pr["title"],
                "url": pr["url"],
            })

    for issue in issues:
        issue["linked_prs"] = issue_prs.get(issue["number"], [])

    # Strip body from PR response to keep payload small
    for pr in prs:
        pr.pop("body", None)
        pr.pop("headRefName", None)

    return JSONResponse({
        "repo": repo,
        "issues": issues,
        "prs": prs,
        "milestones": milestones,
        "recent_closed": recent_closed,
    })


@app.get("/api/pr-status")
async def api_pr_status():
    prs = run_gh_json([
        "search", "prs", "--owner", "sil-ai", "--state", "open",
        "--json", "repository,title,author,createdAt,updatedAt,url,isDraft",
        "--limit", "200",
    ])

    log.info("Fetching review info for %d PRs in parallel...", len(prs))

    def fetch_reviews(pr):
        repo = pr["repository"]["name"]
        # Extract PR number from URL
        pr_number = pr["url"].rstrip("/").split("/")[-1]
        try:
            reviews = run_gh_json([
                "api", f"repos/sil-ai/{repo}/pulls/{pr_number}/reviews",
                "--jq", "[.[] | {user: .user.login, state: .state}]",
            ], timeout=10)
        except Exception:
            reviews = []
        try:
            requested = run_gh_json([
                "api", f"repos/sil-ai/{repo}/pulls/{pr_number}/requested_reviewers",
                "--jq", "{users: [.users[].login], teams: [.teams[].slug]}",
            ], timeout=10)
        except Exception:
            requested = {"users": [], "teams": []}

        # Deduplicate reviews: keep the latest state per user
        seen = {}
        for r in reviews:
            user = r["user"]
            if user.endswith("[bot]"):
                continue
            seen[user] = r["state"]

        pr["reviews"] = [{"user": u, "state": s} for u, s in seen.items()]
        pr["requested_reviewers"] = requested.get("users", []) + requested.get("teams", [])
        return pr

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=8) as pool:
        prs = await asyncio.gather(
            *[loop.run_in_executor(pool, fetch_reviews, pr) for pr in prs]
        )

    return JSONResponse({"prs": list(prs)})


@app.get("/api/my-tasks/{username}")
async def api_my_tasks(username: str):
    issues = run_gh_json([
        "search", "issues", "--owner", "sil-ai", "--state", "open",
        "--assignee", username,
        "--json", "repository,title,labels,createdAt,updatedAt,url",
        "--limit", "100",
    ])

    prs = run_gh_json([
        "search", "prs", "--owner", "sil-ai", "--state", "open",
        "--author", username,
        "--json", "repository,title,createdAt,url",
        "--limit", "50",
    ])

    return JSONResponse({"issues": issues, "prs": prs})
