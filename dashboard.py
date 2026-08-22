"""GitHub PM Dashboard for sil-ai org."""

import asyncio
import json
import logging
import os
import re
import sqlite3
import subprocess
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from pydantic import BaseModel
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("dashboard")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GH_WRITE_TOKEN = os.getenv("GH_WRITE_TOKEN", "")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")
_SESSION_SECRET = os.getenv("SESSION_SECRET", "")
_SESSION_COOKIE = "pm_session"


def _session_token() -> str:
    import hmac as _hmac
    key = (_SESSION_SECRET or DASHBOARD_PASSWORD).encode()
    return _hmac.new(key, DASHBOARD_PASSWORD.encode(), "sha256").hexdigest()


def _valid_session(request: Request) -> bool:
    if not DASHBOARD_PASSWORD:
        return True
    import hmac as _hmac
    token = request.cookies.get(_SESSION_COOKIE, "")
    return _hmac.compare_digest(token, _session_token())


class _AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in ("/login", "/logout") or path.startswith("/static"):
            return await call_next(request)
        if not _valid_session(request):
            return RedirectResponse(url="/login", status_code=302)
        return await call_next(request)


app = FastAPI()
app.add_middleware(_AuthMiddleware)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def run_gh(args: list[str], timeout: int = 60, stdin: str | None = None, token: str = "") -> str:
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        input=stdin,
        env={**os.environ, "GH_TOKEN": token} if token else None,
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

_LOGIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Login – sil-ai PM Dashboard</title>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {{
      darkMode: 'class',
      theme: {{ extend: {{ colors: {{ surface: '#12131a', panel: '#1a1b26', border: '#2a2b3d', accent: '#818cf8' }},
        fontFamily: {{ sans: ['"DM Sans"', 'system-ui', 'sans-serif'] }} }} }}
    }}
  </script>
</head>
<body class="dark bg-surface min-h-screen flex items-center justify-center font-sans">
  <div class="bg-panel border border-border rounded-2xl p-8 w-full max-w-sm shadow-2xl shadow-black/40">
    <h1 class="text-xl font-bold text-gray-100 mb-1">sil-ai <span class="text-[#818cf8]">PM Dashboard</span></h1>
    <p class="text-sm text-gray-500 mb-6">Sign in to continue</p>
    {error}
    <form method="post" action="/login">
      <label class="block text-sm text-gray-400 mb-1">Password</label>
      <input type="password" name="password" autofocus
        class="w-full bg-surface border border-border text-gray-200 rounded-lg px-4 py-2.5 mb-4 focus:outline-none focus:border-[#818cf8]/60 text-sm">
      <button type="submit"
        class="w-full bg-[#818cf8]/90 hover:bg-[#818cf8] text-white font-medium rounded-lg py-2.5 text-sm transition-colors">
        Sign in
      </button>
    </form>
  </div>
</body>
</html>
"""


@app.get("/login", response_class=HTMLResponse)
async def login_page(error: str = ""):
    err_html = '<p class="text-red-400 text-sm mb-4">Incorrect password.</p>' if error else ""
    return HTMLResponse(_LOGIN_HTML.format(error=err_html))


@app.post("/login")
async def login_submit(request: Request):
    import hmac as _hmac
    form = await request.form()
    password = str(form.get("password", ""))
    if DASHBOARD_PASSWORD and _hmac.compare_digest(password, DASHBOARD_PASSWORD):
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(_SESSION_COOKIE, _session_token(), httponly=True, samesite="lax", max_age=86400 * 5)
        return response
    return RedirectResponse(url="/login?error=1", status_code=302)


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(_SESSION_COOKIE)
    return response


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


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
                "--json", "number,title,labels,url",
                "--limit", "200",
            ], timeout=15)
            prs = run_gh_json([
                "pr", "list", "--repo", f"sil-ai/{repo}", "--state", "open",
                "--json", "number,title,author,url,isDraft",
                "--limit", "50",
            ], timeout=15)

            def priority_rank(issue):
                for l in (issue.get("labels") or []):
                    n = l.get("name", "") or ""
                    if n.startswith("P0"): return 0
                    if n.startswith("P1"): return 1
                    if n.startswith("P2"): return 2
                    if n.startswith("P3"): return 3
                return 9

            p0 = sum(1 for i in issues if priority_rank(i) == 0)
            p1 = sum(1 for i in issues if priority_rank(i) == 1)

            # Top issues: P0/P1 first, then most recent, up to 3
            sorted_issues = sorted(issues, key=priority_rank)
            top_issues = [
                {"number": i["number"], "title": i["title"], "url": i["url"],
                 "labels": [l.get("name", "") for l in (i.get("labels") or [])]}
                for i in sorted_issues[:3]
            ]

            # Top PRs: up to 3
            top_prs = [
                {"number": p["number"], "title": p["title"], "url": p["url"],
                 "author": p.get("author", {}).get("login", "?"),
                 "isDraft": p.get("isDraft", False)}
                for p in prs[:3]
            ]

            # Last commit date + recent commit count (4 weeks, per week)
            fourteen_ago = since_date(14)
            try:
                raw = run_gh([
                    "api", f"repos/sil-ai/{repo}/commits?since={since_date(28)}T00:00:00Z&per_page=100",
                    "-q", ".[].commit.author.date",
                ], timeout=10)
                commit_dates = [line.strip() for line in raw.splitlines() if line.strip()] if raw else []
                last_commit = commit_dates[0] if commit_dates else ""

                # Bucket into 4 weeks (index 0 = most recent)
                now = datetime.now(timezone.utc)
                week_counts = [0, 0, 0, 0]
                for d in commit_dates:
                    age = (now - datetime.fromisoformat(d.replace("Z", "+00:00"))).days
                    week_idx = min(age // 7, 3)
                    week_counts[week_idx] += 1
            except Exception:
                last_commit = ""
                week_counts = [0, 0, 0, 0]

            return {
                "name": repo,
                "issues": len(issues),
                "prs": len(prs),
                "p0": p0,
                "p1": p1,
                "week_commits": week_counts,
                "top_issues": top_issues,
                "top_prs": top_prs,
                "last_commit": last_commit,
            }
        except Exception as e:
            log.warning("  %s: failed (%s)", repo, e)
            return {"name": repo, "issues": 0, "prs": 0, "p0": 0, "p1": 0,
                    "top_issues": [], "top_prs": [], "last_commit": "",
                    "week_commits": [0, 0, 0, 0]}

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


@app.get("/api/display-names")
async def api_display_names():
    names_file = Path(__file__).parent / "display_names.json"
    if names_file.exists():
        return JSONResponse(json.loads(names_file.read_text()))
    return JSONResponse({})


@app.get("/api/weekly")
async def api_weekly(start: str = "", end: str = "", fresh: str = ""):
    cache_url = f"/api/weekly?start={start}&end={end}"
    cached, is_stale = _api_cache_get(cache_url)
    if cached and not fresh:
        if is_stale:
            cached["_stale"] = True
        return JSONResponse(cached)

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

    result = {
        "start": start_str,
        "end": end_str,
        "issues_closed": issues_closed,
        "issues_opened": issues_opened,
        "prs_merged": prs_merged,
        "commits_by_repo": commits_by_repo,
    }
    _api_cache_set(cache_url, result)
    return JSONResponse(result)


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
async def api_repo_status(repo: str, start: str = "", end: str = "", fresh: str = ""):
    cache_url = f"/api/repo-status/{repo}?start={start}&end={end}"
    cached, is_stale = _api_cache_get(cache_url)
    if cached and not fresh:
        if is_stale:
            cached["_stale"] = True
        return JSONResponse(cached)

    issues = run_gh_json([
        "issue", "list", "--repo", f"sil-ai/{repo}", "--state", "open",
        "--json", "number,title,labels,assignees,createdAt,updatedAt,milestone,url",
        "--limit", "100",
    ])

    prs = run_gh_json([
        "pr", "list", "--repo", f"sil-ai/{repo}", "--state", "open",
        "--json", "number,title,author,createdAt,reviewRequests,url,body,headRefName,isDraft",
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

    # Recent commits on main and release branches
    try:
        branches = run_gh_json([
            "api", f"repos/sil-ai/{repo}/branches?per_page=100",
            "--jq", "[.[].name]",
        ], timeout=10)
    except Exception:
        branches = []

    if "main" in branches:
        target_branches = ["main"]
    elif "master" in branches:
        target_branches = ["master"]
    else:
        target_branches = []
    target_branches += sorted(
        [b for b in branches if b.startswith("release") and b not in target_branches]
    )

    commits_since = start if start else since_date(7)
    commits_until = f"{end}T23:59:59Z" if end else ""
    until_param = f"&until={commits_until}" if commits_until else ""
    branch_commits: dict[str, list] = {}
    for branch in target_branches:
        try:
            raw = run_gh([
                "api", f"repos/sil-ai/{repo}/commits?sha={branch}&since={commits_since}T00:00:00Z{until_param}&per_page=100",
                "-q", '.[] | {sha: .sha[:7], date: .commit.author.date, author: (.author.login // .commit.author.name), message: (.commit.message | split("\n")[0])}',
            ], timeout=10)
            if raw:
                commits = [json.loads(line) for line in raw.splitlines() if line.strip()]
                if commits:
                    branch_commits[branch] = commits
        except Exception:
            pass

    result = {
        "repo": repo,
        "issues": issues,
        "prs": prs,
        "milestones": milestones,
        "recent_closed": recent_closed,
        "branch_commits": branch_commits,
    }
    _api_cache_set(cache_url, result)
    return JSONResponse(result)


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


@app.get("/api/actions")
async def api_actions():
    repos = get_active_repos()
    log.info("Fetching actions for %d repos in parallel...", len(repos))

    def fetch_runs(repo):
        try:
            runs = run_gh_json([
                "api", f"repos/sil-ai/{repo}/actions/runs?per_page=5",
                "--jq", "[.workflow_runs[] | {id, name, head_branch, status, conclusion, created_at, updated_at, html_url, run_number, event}]",
            ], timeout=15)
            if runs:
                return {"repo": repo, "runs": runs}
        except Exception as e:
            log.warning("  %s actions: failed (%s)", repo, e)
        return None

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = await asyncio.gather(
            *[loop.run_in_executor(pool, fetch_runs, repo) for repo in repos]
        )
    # Only include repos that have workflow runs
    data = [r for r in results if r and r["runs"]]
    return JSONResponse(data)


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


# --- Commit summarization (SQLite-backed cache) ---

_db_path = Path(__file__).parent / "data" / "cache.db"
_db_path.parent.mkdir(exist_ok=True)


def _init_cache_db():
    conn = sqlite3.connect(_db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS summaries "
        "(hash TEXT PRIMARY KEY, summary TEXT, created_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS api_cache "
        "(url TEXT PRIMARY KEY, data TEXT, created_at REAL)"
    )
    conn.commit()
    conn.close()


_init_cache_db()


API_CACHE_FRESH = 5 * 60       # 5 min: serve without revalidation
API_CACHE_MAX_AGE = 24 * 3600  # 24h: serve stale while revalidating


def _api_cache_get(url: str) -> tuple[dict | None, bool]:
    """Return (data, is_stale). Returns None data if nothing cached or expired beyond max age."""
    conn = sqlite3.connect(_db_path)
    row = conn.execute("SELECT data, created_at FROM api_cache WHERE url = ?", (url,)).fetchone()
    conn.close()
    if not row:
        return None, True
    age = time.time() - row[1]
    if age > API_CACHE_MAX_AGE:
        return None, True
    return json.loads(row[0]), age > API_CACHE_FRESH


def _api_cache_set(url: str, data: dict):
    conn = sqlite3.connect(_db_path)
    conn.execute(
        "INSERT OR REPLACE INTO api_cache (url, data, created_at) VALUES (?, ?, ?)",
        (url, json.dumps(data), time.time()),
    )
    conn.commit()
    conn.close()


def _api_cache_clear(url: str):
    conn = sqlite3.connect(_db_path)
    conn.execute("DELETE FROM api_cache WHERE url = ?", (url,))
    conn.commit()
    conn.close()


def _cache_get(key: str) -> str | None:
    conn = sqlite3.connect(_db_path)
    row = conn.execute("SELECT summary FROM summaries WHERE hash = ?", (key,)).fetchone()
    conn.close()
    return row[0] if row else None


def _cache_set(key: str, summary: str):
    conn = sqlite3.connect(_db_path)
    conn.execute(
        "INSERT OR REPLACE INTO summaries (hash, summary, created_at) VALUES (?, ?, ?)",
        (key, summary, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def _call_openai(prompt: str) -> str:
    """Call OpenAI Responses API with gpt-5-mini."""
    if not OPENAI_API_KEY:
        return ""
    body = json.dumps({"model": "gpt-5-mini", "input": prompt}).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=body,
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        # Responses API returns output[].content[].text
        for item in data.get("output", []):
            if item.get("type") == "message":
                for part in item.get("content", []):
                    if part.get("type") == "output_text":
                        return part["text"]
        return ""
    except Exception as e:
        log.warning("OpenAI call failed: %s", e)
        return ""


def _build_summary_prompt(repo: str, commits: list[dict], merged_prs: list[dict]) -> str:
    lines = [f"Summarize the development work done on the '{repo}' repository this week."]
    if merged_prs:
        lines.append("\nMerged PRs:")
        for pr in merged_prs:
            lines.append(f"  - {pr.get('title', '?')} (by @{pr.get('author', '?')})")
    if commits:
        lines.append("\nCommits:")
        for c in commits:
            lines.append(f"  - {c.get('message', '?')} ({c.get('author', '?')})")
    lines.append(
        "\nWrite a nested bullet list summarizing what was accomplished. "
        "Use top-level bullets for major themes (e.g. 'API improvements', 'Bug fixes', 'Infrastructure'). "
        "Use indented sub-bullets (with '  -') for specific changes under each theme. "
        "Group related commits together. Use plain language a project manager would understand. "
        "Don't mention commit hashes or PR numbers. Keep it brief. "
        "Example format:\n"
        "- API improvements\n"
        "  - Added retry logic to scoring endpoint\n"
        "  - Fixed CORS headers for production\n"
        "- Infrastructure\n"
        "  - Updated dependencies"
    )
    return "\n".join(lines)


@app.post("/api/summarize-commits")
async def api_summarize_commits(request: Request):
    if not OPENAI_API_KEY:
        return JSONResponse({"error": "OPENAI_API_KEY not configured"}, status_code=503)

    body = await request.json()
    repos_data = body.get("repos", [])
    results = {}

    loop = asyncio.get_event_loop()

    def summarize_one(repo_entry):
        repo = repo_entry["repo"]
        commits = repo_entry.get("commits", [])
        merged_prs = repo_entry.get("merged_prs", [])

        # Cache key based on content
        cache_key = sha256(json.dumps(
            {"repo": repo, "commits": commits, "prs": merged_prs},
            sort_keys=True,
        ).encode()).hexdigest()[:16]

        cached = _cache_get(cache_key)
        if cached:
            return repo, cached

        prompt = _build_summary_prompt(repo, commits, merged_prs)
        summary = _call_openai(prompt)
        if summary:
            _cache_set(cache_key, summary)
        return repo, summary

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            loop.run_in_executor(pool, summarize_one, entry)
            for entry in repos_data
        ]
        for coro in asyncio.as_completed(futures):
            repo, summary = await coro
            if summary:
                results[repo] = summary

    return JSONResponse({"summaries": results})


# --- Plans (ordered cross-repo checklists, stored as `plan`-labelled issues) ---

PLAN_LABEL = "plan"
PLAN_COMPLETED_DAYS = 14
_PLANS_CACHE_URL = "/api/plans/list"
# Bullet is captured so a rewrite preserves whatever the author used.
_STEP_RE = re.compile(r"^(\s*)([-*+]) \[([ xX])\] ?(.*)$")
# Anchored, and angle brackets excluded, so a literal <!-- in a Step's own text
# cannot shadow the real trailing metadata.
_META_RE = re.compile(r"<!--([^<>]*)-->\s*$")
_ACTOR_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")

# One lock per Plan issue, so a read-verify-write cycle cannot interleave with
# another. Sufficient because the app runs a single uvicorn worker; a second
# worker would need a shared lock.
_plan_locks: dict[tuple[str, int], asyncio.Lock] = {}


def _plan_lock(repo: str, number: int) -> asyncio.Lock:
    return _plan_locks.setdefault((repo, number), asyncio.Lock())


class StepTick(BaseModel):
    done: bool
    by: str
    expect: str


def _parse_meta(comment: str) -> dict:
    meta = {}
    for token in comment.split():
        key, sep, value = token.partition(":")
        if sep and key:
            meta[key] = value
    return meta


def _fmt_meta(meta: dict) -> str:
    return " ".join(f"{k}:{meta[k]}" for k in ("repo", "ref", "kind", "by", "at") if meta.get(k))


def parse_plan_body(body: str) -> tuple[list[dict], str]:
    """Split an issue body into ordered Steps and the surrounding context prose.

    Flat list only: indented checklist items are treated as Steps at the same
    level, so nesting cannot make "next up" ambiguous.
    """
    steps, context = [], []
    for lineno, line in enumerate(body.splitlines()):
        m = _STEP_RE.match(line)
        if not m:
            context.append(line)
            continue
        comment = _META_RE.search(m.group(4))
        meta = _parse_meta(comment.group(1)) if comment else {}
        ref = meta.get("ref", "")
        steps.append({
            "index": len(steps),
            "line": lineno,
            "raw": line,
            "text": _META_RE.sub("", m.group(4)).strip(),
            "done": m.group(3).lower() == "x",
            "badRef": "" if not ref or ref.isdigit() else ref,
            "repo": meta.get("repo", "") if "/" not in meta.get("repo", "") else "",
            "ref": int(ref) if ref.isdigit() else 0,
            "kind": meta.get("kind", ""),
            "by": meta.get("by", ""),
            "at": meta.get("at", ""),
        })
    return steps, re.sub(r"\n{3,}", "\n\n", "\n".join(context).strip())


def fetch_step_state(repo: str, ref: int) -> dict:
    """Live state of the PR or issue a Step references. Never inferred as Done."""
    try:
        pr = run_gh_json([
            "pr", "view", str(ref), "--repo", f"sil-ai/{repo}",
            "--json", "state,isDraft,mergedAt,mergeable,reviewDecision,title,url",
        ], timeout=10)
        if pr["state"] == "MERGED":
            state = "merged"
        elif pr["state"] == "CLOSED":
            state = "closed_unmerged"
        elif pr["isDraft"]:
            state = "draft"
        else:
            state = "open"
        return {
            "type": "pr",
            "state": state,
            "mergedAt": pr.get("mergedAt"),
            "mergeable": pr.get("mergeable"),
            "reviewDecision": pr.get("reviewDecision"),
            "title": pr.get("title"),
            "url": pr.get("url"),
        }
    except Exception:
        pass
    try:
        issue = run_gh_json([
            "issue", "view", str(ref), "--repo", f"sil-ai/{repo}",
            "--json", "state,title,url",
        ], timeout=10)
        return {
            "type": "issue",
            "state": issue["state"].lower(),
            "title": issue.get("title"),
            "url": issue.get("url"),
        }
    except Exception as e:
        log.warning("  %s#%s: ref unresolvable (%s)", repo, ref, e)
        return {"type": "unknown", "state": "not_found"}


def search_plans() -> list[dict]:
    fields = "repository,number,title,url,state,createdAt,updatedAt"
    open_plans = run_gh_json([
        "search", "issues", "--owner", "sil-ai", "--label", PLAN_LABEL,
        "--state", "open", "--json", fields, "--limit", "50",
    ], timeout=20)
    closed_plans = run_gh_json([
        "search", "issues", "--owner", "sil-ai", "--label", PLAN_LABEL,
        "--state", "closed", "--json", fields, "--limit", "50",
        "--", f"closed:>{since_date(PLAN_COMPLETED_DAYS)}",
    ], timeout=20)
    return [*open_plans, *closed_plans]


def fetch_plan(listed: dict) -> dict | None:
    repo = listed["repository"]["name"]
    number = listed["number"]
    try:
        issue = run_gh_json([
            "issue", "view", str(number), "--repo", f"sil-ai/{repo}",
            "--json", "number,title,url,body,state,closedAt,updatedAt",
        ], timeout=15)
    except Exception as e:
        log.warning("  %s#%s: plan body fetch failed (%s)", repo, number, e)
        return None
    steps, context = parse_plan_body(issue.get("body") or "")
    return {
        "repo": repo,
        "number": number,
        "title": issue["title"],
        "url": issue["url"],
        "state": issue["state"].lower(),
        "closedAt": issue.get("closedAt"),
        "updatedAt": issue.get("updatedAt"),
        "context": context,
        "steps": steps,
        "repos": sorted({s["repo"] for s in steps if s["repo"]}),
        "doneCount": sum(1 for s in steps if s["done"]),
        "total": len(steps),
        "nextUp": next((s["index"] for s in steps if not s["done"]), None),
    }


@app.get("/api/plans")
async def api_plans(fresh: str = ""):
    cached, list_stale = (None, False) if fresh else _api_cache_get(_PLANS_CACHE_URL)

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=8) as pool:
        if cached:
            listed = cached["plans"]
        else:
            try:
                listed = await loop.run_in_executor(pool, search_plans)
                _api_cache_set(_PLANS_CACHE_URL, {"plans": listed})
                list_stale = False
            except Exception as e:
                # The search API budget is 30/min and `fresh=1` lets anyone spend
                # it. Serve the last known list rather than failing the tab.
                log.warning("plan search failed (%s); falling back to cache", e)
                stale, _ = _api_cache_get(_PLANS_CACHE_URL)
                listed = stale["plans"] if stale else []
                list_stale = True

        # Bodies are never cached: a stale checklist can get a migration run twice.
        log.info("Fetching %d plan bodies in parallel...", len(listed))
        plans = await asyncio.gather(
            *[loop.run_in_executor(pool, fetch_plan, p) for p in listed]
        )
        plans = [p for p in plans if p]

        refs = [(p, s) for p in plans for s in p["steps"] if s["repo"] and s["ref"]]
        states = await asyncio.gather(
            *[loop.run_in_executor(pool, fetch_step_state, s["repo"], s["ref"]) for _, s in refs]
        )

    for (_, step), state in zip(refs, states):
        step["live"] = state

    plans.sort(key=lambda p: p["updatedAt"] or "", reverse=True)
    result = {"plans": plans, "canWrite": bool(GH_WRITE_TOKEN)}
    if list_stale:
        result["_stale"] = True
    return JSONResponse(result)


def _write_step(repo: str, number: int, index: int, done: bool, by: str, expect: str) -> tuple[int, dict]:
    """Re-read the body, verify the target line, then rewrite it. Refuses to clobber."""
    issue = run_gh_json([
        "issue", "view", str(number), "--repo", f"sil-ai/{repo}",
        "--json", "body,labels",
    ], timeout=15)
    if PLAN_LABEL not in [l["name"] for l in issue.get("labels", [])]:
        return 404, {"error": f"sil-ai/{repo}#{number} is not a Plan."}

    body = issue.get("body") or ""
    steps, _ = parse_plan_body(body)

    if index < 0 or index >= len(steps):
        return 409, {"error": "That step no longer exists — the plan changed. Refresh."}
    step = steps[index]
    if step["raw"] != expect:
        return 409, {"error": "That step changed since you loaded the plan. Refresh and try again."}

    m = _STEP_RE.match(step["raw"])
    comment = _META_RE.search(m.group(4))
    meta = _parse_meta(comment.group(1)) if comment else {}
    if done:
        meta["by"] = by
        meta["at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        meta.pop("by", None)
        meta.pop("at", None)

    rendered = _fmt_meta(meta)
    text = _META_RE.sub("", m.group(4)).strip()
    line = f"{m.group(1)}{m.group(2)} [{'x' if done else ' '}] {text}"
    if rendered:
        line += f" <!-- {rendered} -->"
    # Rewrite in place, keeping this line's own terminator, so every other byte
    # of the body — including mixed or non-LF line endings — is untouched.
    kept = body.splitlines(keepends=True)
    original = kept[step["line"]]
    kept[step["line"]] = line + original[len(original.rstrip("\r\n")):]
    new_body = "".join(kept)

    run_gh(
        ["issue", "edit", str(number), "--repo", f"sil-ai/{repo}", "--body-file", "-"],
        timeout=20, stdin=new_body, token=GH_WRITE_TOKEN,
    )
    return 200, {"raw": line, "by": meta.get("by", ""), "at": meta.get("at", "")}


@app.post("/api/plans/{repo}/{number}/steps/{index}")
async def api_plan_step(repo: str, number: int, index: int, tick: StepTick):
    if not GH_WRITE_TOKEN:
        return JSONResponse(
            {"error": "Ticking needs GH_WRITE_TOKEN (fine-grained, Issues: Read+Write)."},
            status_code=503,
        )
    by = tick.by.strip()
    if not _ACTOR_RE.match(by):
        return JSONResponse({"error": "Not a valid GitHub username."}, status_code=400)

    loop = asyncio.get_event_loop()
    async with _plan_lock(repo, number):
        try:
            status, result = await loop.run_in_executor(
                None, _write_step, repo, number, index, tick.done, by, tick.expect,
            )
        except Exception as e:
            log.warning("tick %s#%s step %s failed: %s", repo, number, index, e)
            return JSONResponse({"error": "GitHub write failed. Try again."}, status_code=502)
    return JSONResponse(result, status_code=status)


@app.post("/api/plans/{repo}/{number}/close")
async def api_plan_close(repo: str, number: int):
    if not GH_WRITE_TOKEN:
        return JSONResponse(
            {"error": "Closing needs GH_WRITE_TOKEN (fine-grained, Issues: Read+Write)."},
            status_code=503,
        )
    loop = asyncio.get_event_loop()
    async with _plan_lock(repo, number):
        try:
            status, result = await loop.run_in_executor(None, _close_plan, repo, number)
        except Exception as e:
            log.warning("close %s#%s failed: %s", repo, number, e)
            return JSONResponse({"error": "GitHub write failed. Try again."}, status_code=502)
    if status == 200:
        _api_cache_clear(_PLANS_CACHE_URL)
    return JSONResponse(result, status_code=status)


def _close_plan(repo: str, number: int) -> tuple[int, dict]:
    """Close a Plan, but only a Plan, and only once every Step is Done."""
    issue = run_gh_json([
        "issue", "view", str(number), "--repo", f"sil-ai/{repo}",
        "--json", "body,labels",
    ], timeout=15)
    if PLAN_LABEL not in [l["name"] for l in issue.get("labels", [])]:
        return 404, {"error": f"sil-ai/{repo}#{number} is not a Plan."}

    steps, _ = parse_plan_body(issue.get("body") or "")
    if not steps or any(not s["done"] for s in steps):
        return 409, {"error": "Not every step is done yet."}

    run_gh(
        ["issue", "close", str(number), "--repo", f"sil-ai/{repo}"],
        timeout=20, token=GH_WRITE_TOKEN,
    )
    return 200, {"closed": True}
